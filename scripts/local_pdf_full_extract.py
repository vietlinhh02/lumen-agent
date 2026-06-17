"""Fast local full-text PDF extraction and chunking benchmark."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class PageText:
    """Extracted text for one PDF page."""

    page_number: int
    char_count: int
    text: str


@dataclass(frozen=True)
class TextChunk:
    """Chunk of extracted full text ready for embedding."""

    chunk_index: int
    page_start: int
    page_end: int
    char_count: int
    text: str


@dataclass(frozen=True)
class PaperExtract:
    """Extraction result for one PDF file."""

    source_file: str
    pages: int
    chars: int
    chunks: int
    seconds: float
    error: str | None
    page_texts: list[PageText]
    text_chunks: list[TextChunk]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Extract full PDF text locally and chunk it.")
    parser.add_argument("pdfs", nargs="+", help="PDF files or directories containing PDFs.")
    parser.add_argument(
        "--engine",
        choices=("pymupdf", "pdf_oxide"),
        default="pymupdf",
        help="PDF text extraction engine.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Only process first N PDFs.")
    parser.add_argument("--workers", type=int, default=8, help="Parallel worker processes.")
    parser.add_argument("--chunk-size", type=int, default=1800, help="Target chunk chars.")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Overlap chars.")
    parser.add_argument(
        "--show-engine-warnings",
        action="store_true",
        help="Show low-level PDF parser warnings from extraction engines.",
    )
    parser.add_argument(
        "--include-page-text",
        action="store_true",
        help="Include full page text in JSON output. Off keeps output smaller.",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Batch embed all chunks after extraction.",
    )
    parser.add_argument(
        "--include-vectors",
        action="store_true",
        help="Write embedding vectors to JSON. Large output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to data/local_pdf_full_extract/<timestamp>.json.",
    )
    return parser.parse_args()


def collect_pdfs(inputs: list[str]) -> list[Path]:
    """Collect PDF files from files or directories."""
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


def extract_one_pdf(
    path: str,
    chunk_size: int,
    chunk_overlap: int,
    engine: str,
    show_engine_warnings: bool,
) -> PaperExtract:
    """Extract one PDF using the selected engine in a worker process."""
    extractors = {
        "pymupdf": extract_pymupdf,
        "pdf_oxide": extract_pdf_oxide,
    }
    if engine not in extractors:
        raise ValueError(f"Unsupported PDF extraction engine: {engine}")

    started = time.perf_counter()
    page_texts: list[PageText] = []
    try:
        page_texts = extract_with_optional_warning_suppression(
            extractor=extractors[engine],
            path=path,
            show_warnings=show_engine_warnings,
        )
        chunks = chunk_pages(page_texts, chunk_size=chunk_size, overlap=chunk_overlap)
        chars = sum(page.char_count for page in page_texts)
        return PaperExtract(
            source_file=Path(path).name,
            pages=len(page_texts),
            chars=chars,
            chunks=len(chunks),
            seconds=round(time.perf_counter() - started, 3),
            error=None,
            page_texts=page_texts,
            text_chunks=chunks,
        )
    except Exception as exc:
        return PaperExtract(
            source_file=Path(path).name,
            pages=len(page_texts),
            chars=sum(page.char_count for page in page_texts),
            chunks=0,
            seconds=round(time.perf_counter() - started, 3),
            error=f"{type(exc).__name__}: {exc}",
            page_texts=page_texts,
            text_chunks=[],
        )


def extract_with_optional_warning_suppression(
    extractor: Any,
    path: str,
    show_warnings: bool,
) -> list[PageText]:
    """Run an extractor while optionally suppressing native stderr warnings."""
    if show_warnings:
        return extractor(path)

    import os

    stderr_fd = sys.stderr.fileno()
    saved_stderr = os.dup(stderr_fd)
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            os.dup2(devnull.fileno(), stderr_fd)
            return extractor(path)
    finally:
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stderr)


def extract_pymupdf(path: str) -> list[PageText]:
    """Extract page text using PyMuPDF."""
    import fitz

    page_texts: list[PageText] = []
    with fitz.open(path) as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text", sort=True)
            text = normalize_text(text)
            page_texts.append(PageText(page_number=page_index, char_count=len(text), text=text))
    return page_texts


def extract_pdf_oxide(path: str) -> list[PageText]:
    """Extract page text using pdf_oxide."""
    from pdf_oxide import PdfDocument

    doc = PdfDocument(path)
    page_texts: list[PageText] = []
    for page_index in range(doc.page_count()):
        text = doc.extract_text(page_index)
        text = normalize_text(text)
        page_texts.append(PageText(page_number=page_index + 1, char_count=len(text), text=text))
    return page_texts


def normalize_text(text: str) -> str:
    """Normalize extracted text without summarizing or dropping content intentionally."""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return "\n".join(compact).strip()


def chunk_pages(page_texts: list[PageText], chunk_size: int, overlap: int) -> list[TextChunk]:
    """Chunk all page text while preserving source page spans."""
    chunks: list[TextChunk] = []
    current_parts: list[str] = []
    current_start: int | None = None
    current_end: int | None = None

    def flush() -> None:
        nonlocal current_parts, current_start, current_end
        text = "\n\n".join(part for part in current_parts if part).strip()
        if not text:
            current_parts = []
            current_start = None
            current_end = None
            return
        chunks.append(
            TextChunk(
                chunk_index=len(chunks) + 1,
                page_start=current_start or 1,
                page_end=current_end or current_start or 1,
                char_count=len(text),
                text=text,
            )
        )
        tail = text[-overlap:].strip() if overlap > 0 else ""
        current_parts = [tail] if tail else []
        current_start = current_end if tail else None

    for page in page_texts:
        paragraphs = split_paragraphs(page.text)
        for paragraph in paragraphs:
            if len(paragraph) > chunk_size:
                for part in split_long_text(paragraph, chunk_size, overlap):
                    if current_parts:
                        flush()
                    chunks.append(
                        TextChunk(
                            chunk_index=len(chunks) + 1,
                            page_start=page.page_number,
                            page_end=page.page_number,
                            char_count=len(part),
                            text=part,
                        )
                    )
                continue

            candidate_len = sum(len(part) for part in current_parts) + len(paragraph)
            if current_parts and candidate_len > chunk_size:
                flush()
            if current_start is None:
                current_start = page.page_number
            current_end = page.page_number
            current_parts.append(paragraph)

    if current_parts:
        flush()
    return chunks


def split_paragraphs(text: str) -> list[str]:
    """Split text into paragraph-like units."""
    parts = re.split(r"\n\s*\n", text)
    return [part.strip() for part in parts if part.strip()]


def split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split a long paragraph with sentence preference."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(split_by_chars(sentence, chunk_size, overlap))
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        tail = current[-overlap:].strip() if overlap > 0 and current else ""
        current = f"{tail} {sentence}".strip() if tail else sentence
    if current:
        chunks.append(current)
    return chunks


def split_by_chars(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Last-resort character splitter."""
    step = max(chunk_size - overlap, 1)
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        parts.append(text[start:end].strip())
        if end == len(text):
            break
        start += step
    return [part for part in parts if part]


async def embed_chunks(papers: list[PaperExtract], include_vectors: bool) -> dict[str, Any]:
    """Embed all extracted chunks in one batched service call."""
    from app.core.embeddings import encode_batch, get_embedding_dimension, get_embedding_model_name

    chunk_refs: list[tuple[PaperExtract, TextChunk]] = []
    texts: list[str] = []
    for paper in papers:
        for chunk in paper.text_chunks:
            chunk_refs.append((paper, chunk))
            texts.append(
                f"Paper: {paper.source_file}\n"
                f"Pages: {chunk.page_start}-{chunk.page_end}\n"
                f"{chunk.text}"
            )

    started = time.perf_counter()
    vectors = await encode_batch(texts)
    vector_count = len(vectors)
    return {
        "seconds": round(time.perf_counter() - started, 3),
        "model": get_embedding_model_name(),
        "dimension": get_embedding_dimension(),
        "count": vector_count,
    }


def default_output_path() -> Path:
    """Return a timestamped output path."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("data/local_pdf_full_extract") / f"{stamp}.json"


def paper_to_json(paper: PaperExtract, include_page_text: bool) -> dict[str, Any]:
    """Serialize one paper extraction result."""
    data = asdict(paper)
    if not include_page_text:
        data["page_texts"] = [
            {
                "page_number": page.page_number,
                "char_count": page.char_count,
            }
            for page in paper.page_texts
        ]
    return data


async def run() -> None:
    """Run local PDF extraction benchmark."""
    args = parse_args()
    pdfs = collect_pdfs(args.pdfs)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]
    output = args.output or default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    papers_by_path: dict[Path, PaperExtract] = {}
    with ProcessPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        futures = {
            executor.submit(
                extract_one_pdf,
                str(path),
                args.chunk_size,
                args.chunk_overlap,
                args.engine,
                args.show_engine_warnings,
            ): path
            for path in pdfs
        }
        for future in as_completed(futures):
            path = futures[future]
            result = future.result()
            papers_by_path[path] = result
            status = "failed" if result.error else "ok"
            print(
                f"{status} {path.name}: pages={result.pages} chars={result.chars} "
                f"chunks={result.chunks} seconds={result.seconds}",
                flush=True,
            )

    papers = [papers_by_path[path] for path in pdfs]
    total_seconds = round(time.perf_counter() - started, 3)
    successful = [paper for paper in papers if not paper.error]
    total_pages = sum(paper.pages for paper in successful)
    total_chars = sum(paper.chars for paper in successful)
    total_chunks = sum(paper.chunks for paper in successful)

    embedding: dict[str, Any] | None = None
    if args.embed and total_chunks:
        embedding = await embed_chunks(successful, include_vectors=args.include_vectors)

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "settings": {
            "limit": args.limit,
            "engine": args.engine,
            "workers": args.workers,
            "chunk_size": args.chunk_size,
            "chunk_overlap": args.chunk_overlap,
            "show_engine_warnings": args.show_engine_warnings,
            "include_page_text": args.include_page_text,
            "embed": args.embed,
        },
        "summary": {
            "pdf_count": len(pdfs),
            "successful": len(successful),
            "failed": len(papers) - len(successful),
            "pages": total_pages,
            "chars": total_chars,
            "chunks": total_chunks,
            "extract_seconds": total_seconds,
            "papers_per_second": round(len(successful) / total_seconds, 3)
            if total_seconds
            else 0.0,
            "pages_per_second": round(total_pages / total_seconds, 3) if total_seconds else 0.0,
        },
        "embedding": embedding,
        "papers": [paper_to_json(paper, args.include_page_text) for paper in papers],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {output}", flush=True)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
