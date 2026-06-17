"""Test Gemini-native batch PDF extraction outside the database pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "papers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_file": {"type": "string"},
                    "title": {"type": "string"},
                    "abstract": {"type": "string"},
                    "methods": {"type": "array", "items": {"type": "string"}},
                    "datasets": {"type": "array", "items": {"type": "string"}},
                    "key_findings": {"type": "array", "items": {"type": "string"}},
                    "limitations": {"type": "array", "items": {"type": "string"}},
                    "evidence_chunks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "section": {"type": "string"},
                                "content_type": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["section", "content_type", "text"],
                        },
                    },
                },
                "required": [
                    "source_file",
                    "title",
                    "abstract",
                    "methods",
                    "datasets",
                    "key_findings",
                    "limitations",
                    "evidence_chunks",
                ],
            },
        }
    },
    "required": ["papers"],
}

VERBATIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "papers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_file": {"type": "string"},
                    "title": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "section": {"type": "string"},
                                "chunks": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "content_type": {"type": "string"},
                                            "text": {"type": "string"},
                                            "verbatim": {"type": "boolean"},
                                        },
                                        "required": ["content_type", "text", "verbatim"],
                                    },
                                },
                            },
                            "required": ["section", "chunks"],
                        },
                    },
                },
                "required": ["source_file", "title", "sections"],
            },
        }
    },
    "required": ["papers"],
}


@dataclass(frozen=True)
class UploadedPdf:
    """Uploaded Gemini file metadata needed for generation and cleanup."""

    path: str
    name: str
    uri: str
    mime_type: str
    size_bytes: int
    upload_seconds: float


@dataclass(frozen=True)
class InlinePdf:
    """Inline PDF metadata used when sending bytes directly in one request."""

    path: str
    mime_type: str
    size_bytes: int
    load_seconds: float


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Batch-test Gemini PDF extraction, optional embedding, and reranking.",
    )
    parser.add_argument("pdfs", nargs="+", help="PDF files or directories containing PDFs.")
    parser.add_argument("--batch-size", type=int, default=4, help="PDFs per Gemini request.")
    parser.add_argument(
        "--input-method",
        choices=["inline", "files"],
        default="inline",
        help="inline sends PDF bytes in the request; files uses Gemini Files API.",
    )
    parser.add_argument("--upload-workers", type=int, default=4, help="Parallel PDF uploads.")
    parser.add_argument("--model", default="gemini-3.1-flash-lite", help="Gemini model name.")
    parser.add_argument("--limit", type=int, default=None, help="Only test the first N PDFs.")
    parser.add_argument("--max-output-tokens", type=int, default=8000)
    parser.add_argument("--max-chunks-per-paper", type=int, default=8)
    parser.add_argument("--chunk-max-chars", type=int, default=1200)
    parser.add_argument(
        "--extract-mode",
        choices=["evidence", "verbatim"],
        default="evidence",
        help="evidence summarizes fields; verbatim returns copied PDF passages.",
    )
    parser.add_argument("--embed", action="store_true", help="Batch embed extracted chunks.")
    parser.add_argument("--include-vectors", action="store_true", help="Write vectors to JSON.")
    parser.add_argument("--rerank-query", default="", help="Optional query to rerank chunks.")
    parser.add_argument("--top-k", type=int, default=20, help="Rerank top-k output.")
    parser.add_argument("--keep-files", action="store_true", help="Keep Gemini uploaded files.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/gemini_pdf_batch_test/<timestamp>.json.",
    )
    return parser.parse_args()


def collect_pdfs(inputs: list[str]) -> list[Path]:
    """Collect PDF paths from files or directories."""
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.pdf")))
            continue
        if path.is_file() and path.suffix.lower() == ".pdf":
            paths.append(path)
            continue
        raise SystemExit(f"Not a PDF file or directory: {path}")
    unique = sorted({path.resolve() for path in paths})
    if not unique:
        raise SystemExit("No PDF files found.")
    return unique


def get_google_api_key() -> str:
    """Load a Gemini API key from repo settings or environment."""
    from app.core.config import get_settings

    settings = get_settings()
    api_key = settings.google_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Set GOOGLE_API_KEY or GEMINI_API_KEY in .env or shell.")
    return api_key


def upload_one_pdf(path: Path, api_key: str) -> UploadedPdf:
    """Upload one PDF and wait until Gemini marks it active."""
    started = time.perf_counter()
    client = genai.Client(api_key=api_key)
    uploaded = client.files.upload(
        file=path,
        config={"mime_type": "application/pdf", "display_name": path.name},
    )
    uploaded = wait_until_active(client, uploaded)
    return UploadedPdf(
        path=str(path),
        name=uploaded.name or "",
        uri=uploaded.uri or "",
        mime_type=uploaded.mime_type or "application/pdf",
        size_bytes=path.stat().st_size,
        upload_seconds=round(time.perf_counter() - started, 3),
    )


def wait_until_active(client: genai.Client, uploaded: Any, timeout_seconds: int = 180) -> Any:
    """Poll uploaded file state until it is usable."""
    deadline = time.monotonic() + timeout_seconds
    current = uploaded
    while time.monotonic() < deadline:
        state = state_name(current)
        if state in {"", "ACTIVE", "SUCCEEDED"}:
            return current
        if state == "FAILED":
            raise RuntimeError(f"Gemini file processing failed: {current.name}")
        time.sleep(2)
        file_name = getattr(current, "name", None)
        if not file_name:
            raise RuntimeError("Gemini uploaded file is missing a file name.")
        current = client.files.get(name=str(file_name))
    raise TimeoutError(f"Gemini file processing timed out: {uploaded.name}")


def state_name(uploaded: Any) -> str:
    """Return a normalized Gemini file state name."""
    state = getattr(uploaded, "state", None)
    if state is None:
        return ""
    name = getattr(state, "name", None)
    return str(name or state).upper()


def upload_batch(paths: list[Path], api_key: str, workers: int) -> list[UploadedPdf]:
    """Upload PDFs in parallel and preserve input order."""
    by_path: dict[Path, UploadedPdf] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(upload_one_pdf, path, api_key): path for path in paths}
        for future in as_completed(futures):
            path = futures[future]
            by_path[path] = future.result()
            print(f"uploaded {path.name} in {by_path[path].upload_seconds}s", flush=True)
    return [by_path[path] for path in paths]


def load_inline_batch(paths: list[Path]) -> tuple[list[InlinePdf], list[types.Part]]:
    """Load PDF bytes as inline Gemini parts."""
    loaded: list[InlinePdf] = []
    parts: list[types.Part] = []
    for path in paths:
        started = time.perf_counter()
        data = path.read_bytes()
        parts.append(types.Part.from_bytes(data=data, mime_type="application/pdf"))
        loaded.append(
            InlinePdf(
                path=str(path),
                mime_type="application/pdf",
                size_bytes=len(data),
                load_seconds=round(time.perf_counter() - started, 3),
            )
        )
    return loaded, parts


def build_evidence_prompt(paths: list[Path], max_chunks: int, chunk_max_chars: int) -> str:
    """Build the evidence-summary extraction prompt for Gemini."""
    names = "\n".join(f"- {path.name}" for path in paths)
    return f"""
Extract structured literature-review evidence from these PDF papers.

Return JSON only. The top-level object must contain a "papers" array.
Each paper.source_file must exactly match one filename from this list:
{names}

For each paper:
- Extract title and abstract.
- Extract concise methods, datasets, key_findings, and limitations arrays.
- Extract at most {max_chunks} evidence_chunks.
- Each evidence chunk must be citation-ready, factual, and from the PDF.
- Use content_type values: abstract, narrative, method, results, limitation, table,
  or figure_caption.
- Keep each chunk text under {chunk_max_chars} characters.
- Do not invent missing fields; use empty strings or empty arrays when absent.
""".strip()


def build_verbatim_prompt(paths: list[Path], max_chunks: int, chunk_max_chars: int) -> str:
    """Build the near-verbatim extraction prompt for Gemini."""
    names = "\n".join(f"- {path.name}" for path in paths)
    return f"""
Extract near-verbatim source passages from these PDF papers.

Return JSON only. The top-level object must contain a "papers" array.
Each paper.source_file must exactly match one filename from this list:
{names}

For each paper:
- Extract the paper title.
- Do not summarize, paraphrase, or combine claims.
- Copy passages exactly as they appear in the PDF whenever possible.
- Keep equations, symbols, citations, and technical terms intact.
- Select at most {max_chunks} total chunks per paper.
- Prefer useful literature-review sections: abstract, introduction, method,
  experiment/results, limitation, conclusion.
- Keep each chunk under {chunk_max_chars} characters by cutting at sentence
  boundaries when possible.
- Set verbatim=true when the text is copied directly. If OCR/layout forces a
  small cleanup for spacing only, still set verbatim=true.
- Do not invent missing text.
""".strip()


def generate_for_batch(
    client: genai.Client,
    file_parts: list[types.Part],
    paths: list[Path],
    model: str,
    max_chunks: int,
    chunk_max_chars: int,
    max_output_tokens: int,
    extract_mode: str,
) -> dict[str, Any]:
    """Ask Gemini to extract structured evidence for one uploaded batch."""
    started = time.perf_counter()
    if extract_mode == "verbatim":
        prompt = build_verbatim_prompt(paths, max_chunks, chunk_max_chars)
        response_schema = VERBATIM_SCHEMA
    else:
        prompt = build_evidence_prompt(paths, max_chunks, chunk_max_chars)
        response_schema = EXTRACT_SCHEMA
    response = client.models.generate_content(
        model=model,
        contents=[*file_parts, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0,
            max_output_tokens=max_output_tokens,
        ),
    )
    return {
        "generate_seconds": round(time.perf_counter() - started, 3),
        "raw_text": response.text or "",
        "parsed": parse_response_json(response.text or ""),
        "usage_metadata": usage_metadata(response),
    }


def parse_response_json(text: str) -> dict[str, Any]:
    """Parse Gemini JSON response with a clear failure message."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned non-JSON text: {text[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini response JSON is not an object.")
    return parsed


def usage_metadata(response: Any) -> dict[str, Any]:
    """Return JSON-safe usage metadata when the SDK exposes it."""
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return {}
    if hasattr(metadata, "model_dump"):
        return metadata.model_dump(mode="json")
    return {}


def flatten_chunks(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten paper evidence chunks for embedding and reranking."""
    chunks: list[dict[str, Any]] = []
    for paper in extraction.get("papers", []):
        if not isinstance(paper, dict):
            continue
        if "sections" in paper:
            for section in paper.get("sections", []):
                if not isinstance(section, dict):
                    continue
                for chunk in section.get("chunks", []):
                    if not isinstance(chunk, dict):
                        continue
                    text = str(chunk.get("text") or "").strip()
                    if not text:
                        continue
                    chunks.append(
                        {
                            "source_file": paper.get("source_file") or "",
                            "title": paper.get("title") or "",
                            "section": section.get("section") or "",
                            "content_type": chunk.get("content_type") or "",
                            "text": text,
                            "verbatim": bool(chunk.get("verbatim", False)),
                        }
                    )
            continue
        for chunk in paper.get("evidence_chunks", []):
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get("text") or "").strip()
            if not text:
                continue
            chunks.append(
                {
                    "source_file": paper.get("source_file") or "",
                    "title": paper.get("title") or "",
                    "section": chunk.get("section") or "",
                    "content_type": chunk.get("content_type") or "",
                    "text": text,
                }
            )
    return chunks


async def enrich_chunks(
    chunks: list[dict[str, Any]],
    *,
    embed: bool,
    include_vectors: bool,
    rerank_query: str,
    top_k: int,
) -> dict[str, Any]:
    """Optionally run batch embedding and reranking on extracted chunks."""
    result: dict[str, Any] = {"chunk_count": len(chunks), "chunks": chunks}
    if embed:
        started = time.perf_counter()
        from app.core.embeddings import (
            encode_batch,
            get_embedding_dimension,
            get_embedding_model_name,
        )

        texts = [embedding_text(chunk) for chunk in chunks]
        vectors = await encode_batch(texts)
        result["embedding"] = {
            "seconds": round(time.perf_counter() - started, 3),
            "model": get_embedding_model_name(),
            "dimension": get_embedding_dimension(),
            "count": len(vectors),
        }
        if include_vectors:
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk["embedding"] = vector
    if rerank_query:
        started = time.perf_counter()
        from app.services.reranker import close_rerank_client, rerank

        ranked = await rerank(rerank_query, [chunk["text"] for chunk in chunks], top_k=top_k)
        await close_rerank_client()
        result["rerank"] = {
            "seconds": round(time.perf_counter() - started, 3),
            "query": rerank_query,
            "items": [
                {"index": index, "score": score, "chunk": chunks[index]} for index, score in ranked
            ],
        }
    return result


def embedding_text(chunk: dict[str, Any]) -> str:
    """Format chunk text with metadata context before embedding."""
    return "\n".join(
        [
            f"Paper: {chunk['title']}",
            f"Section: {chunk['section']}",
            f"Type: {chunk['content_type']}",
            chunk["text"],
        ]
    )


def default_output_path() -> Path:
    """Return a timestamped output path."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("data/gemini_pdf_batch_test") / f"{stamp}.json"


def chunked(items: list[Path], size: int) -> list[list[Path]]:
    """Split paths into fixed-size batches."""
    if size < 1:
        raise SystemExit("--batch-size must be >= 1")
    return [items[index : index + size] for index in range(0, len(items), size)]


def delete_uploaded_files(client: genai.Client, uploaded: list[UploadedPdf]) -> None:
    """Best-effort cleanup for Gemini uploaded files."""
    for item in uploaded:
        try:
            client.files.delete(name=item.name)
        except Exception as exc:
            print(f"warning: could not delete Gemini file {item.name}: {exc}")


def prepare_file_parts(
    paths: list[Path],
    api_key: str,
    input_method: str,
    upload_workers: int,
) -> tuple[list[types.Part], list[dict[str, Any]], list[UploadedPdf]]:
    """Prepare Gemini file parts using inline bytes or Files API uploads."""
    if input_method == "inline":
        loaded, parts = load_inline_batch(paths)
        return parts, [asdict(item) for item in loaded], []

    uploaded = upload_batch(paths, api_key, upload_workers)
    parts = [types.Part.from_uri(file_uri=item.uri, mime_type=item.mime_type) for item in uploaded]
    return parts, [asdict(item) for item in uploaded], uploaded


async def run() -> None:
    """Run the batch extraction experiment."""
    args = parse_args()
    api_key = get_google_api_key()
    pdfs = collect_pdfs(args.pdfs)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]
    output = args.output or default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    client = genai.Client(api_key=api_key)
    started = time.perf_counter()
    batches: list[dict[str, Any]] = []
    all_chunks: list[dict[str, Any]] = []

    for batch_index, paths in enumerate(chunked(pdfs, args.batch_size), start=1):
        print(
            f"batch {batch_index}: preparing {len(paths)} PDFs via {args.input_method}",
            flush=True,
        )
        file_parts, file_metadata, uploaded = prepare_file_parts(
            paths,
            api_key,
            args.input_method,
            args.upload_workers,
        )
        try:
            generated = generate_for_batch(
                client,
                file_parts,
                paths,
                args.model,
                args.max_chunks_per_paper,
                args.chunk_max_chars,
                args.max_output_tokens,
                args.extract_mode,
            )
            chunks = flatten_chunks(generated["parsed"])
            all_chunks.extend(chunks)
            batches.append(
                {
                    "batch_index": batch_index,
                    "input_paths": [str(path) for path in paths],
                    "input_method": args.input_method,
                    "files": file_metadata,
                    **generated,
                    "chunk_count": len(chunks),
                }
            )
            print(
                f"batch {batch_index}: extracted {len(chunks)} chunks "
                f"in {generated['generate_seconds']}s",
                flush=True,
            )
        finally:
            if not args.keep_files:
                delete_uploaded_files(client, uploaded)

    postprocess = await enrich_chunks(
        all_chunks,
        embed=args.embed,
        include_vectors=args.include_vectors,
        rerank_query=args.rerank_query,
        top_k=args.top_k,
    )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "pdf_count": len(pdfs),
        "total_seconds": round(time.perf_counter() - started, 3),
        "settings": {
            "batch_size": args.batch_size,
            "input_method": args.input_method,
            "upload_workers": args.upload_workers,
            "max_chunks_per_paper": args.max_chunks_per_paper,
            "chunk_max_chars": args.chunk_max_chars,
            "max_output_tokens": args.max_output_tokens,
            "extract_mode": args.extract_mode,
            "embed": args.embed,
            "rerank_query": args.rerank_query,
        },
        "batches": batches,
        "postprocess": postprocess,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}", flush=True)
    print(f"total: {report['total_seconds']}s, chunks: {len(all_chunks)}", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
