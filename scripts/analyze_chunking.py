"""Analyze chunking quality across the full PDF corpus.

Runs the same deterministic section detector + chunker that
``app.services.pdf_fulltext`` uses, on every PDF in ``data/papers``,
and prints a quality report.

* % of papers that get section detection (vs. fall back to "Full Text")
* distribution of section labels
* distribution of chunk sizes / chunks-per-paper
* edge cases: empty extract, oversized sections, no sections, etc.

Optional JSON output for further inspection.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _analyze_one(pdf_path: Path) -> dict[str, Any]:
    """Extract + chunk one PDF and return a quality record."""
    from app.services.pdf_fulltext import chunk_text, extract_text

    record: dict[str, Any] = {
        "source_file": pdf_path.name,
        "chars": 0,
        "extract_ok": False,
        "section_count": 0,
        "sections": [],
        "chunk_count": 0,
        "chunks": [],
        "min_chunk_chars": 0,
        "max_chunk_chars": 0,
        "median_chunk_chars": 0,
        "has_oversized": False,
        "has_tiny": False,
        "all_full_text": False,
        "section_labels": [],
        "seconds": 0.0,
        "error": None,
    }

    t0 = time.perf_counter()
    try:
        text = extract_text(pdf_path)
    except Exception as exc:
        record["error"] = f"extract: {exc!r}"
        record["seconds"] = time.perf_counter() - t0
        return record

    if text is None:
        record["error"] = "no text (image-only or empty)"
        record["seconds"] = time.perf_counter() - t0
        return record

    record["extract_ok"] = True
    record["chars"] = len(text)

    try:
        chunks = chunk_text(text)
    except Exception as exc:
        record["error"] = f"chunk: {exc!r}"
        record["seconds"] = time.perf_counter() - t0
        return record

    if not chunks:
        record["error"] = "no chunks"
        record["seconds"] = time.perf_counter() - t0
        return record

    sizes = sorted(len(c.text) for c in chunks)
    record["chunk_count"] = len(chunks)
    record["min_chunk_chars"] = sizes[0]
    record["max_chunk_chars"] = sizes[-1]
    record["median_chunk_chars"] = sizes[len(sizes) // 2]
    record["has_oversized"] = sizes[-1] > 2500
    record["has_tiny"] = sizes[0] < 100

    sections = [c.section_label for c in chunks]
    unique_sections = list(dict.fromkeys(sections))
    record["section_count"] = len(unique_sections)
    record["sections"] = unique_sections
    record["section_labels"] = sections
    record["all_full_text"] = unique_sections == ["Full Text"]

    record["chunks"] = [
        {
            "section_label": c.section_label,
            "char_count": len(c.text),
            "preview": c.text[:200].replace("\n", " "),
        }
        for c in chunks
    ]
    record["seconds"] = time.perf_counter() - t0
    return record


def _worker(pdf_path_str: str) -> dict[str, Any]:
    return _analyze_one(Path(pdf_path_str))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--papers-dir",
        type=Path,
        default=ROOT / "data" / "papers",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "local_pdf_full_extract" / "chunking-analysis.json",
    )
    args = parser.parse_args()

    pdfs = sorted(args.papers_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]

    if not pdfs:
        print(f"No PDFs found in {args.papers_dir}", file=sys.stderr)
        return 1

    print(f"Analyzing {len(pdfs)} PDFs with {args.workers} workers...")

    records: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_worker, str(p)): p for p in pdfs}
        for i, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            records.append(rec)
            if i % 25 == 0 or i == len(pdfs):
                print(f"  {i}/{len(pdfs)} done")
    elapsed = time.perf_counter() - t0

    records.sort(key=lambda r: r["source_file"])

    total = len(records)
    extract_ok = sum(1 for r in records if r["extract_ok"])
    no_text = sum(1 for r in records if r["error"] == "no text (image-only or empty)")
    chunked = sum(1 for r in records if r["chunk_count"] > 0)
    oversized = sum(1 for r in records if r["has_oversized"])
    tiny = sum(1 for r in records if r["has_tiny"])
    all_full_text = sum(1 for r in records if r["all_full_text"])
    multi_section = sum(1 for r in records if r["section_count"] >= 2)
    total_chunks = sum(r["chunk_count"] for r in records)
    total_chars = sum(r["chars"] for r in records)

    section_label_counter: Counter[str] = Counter()
    for r in records:
        for label in r["section_labels"]:
            section_label_counter[label] += 1

    chunk_per_paper_buckets = Counter()
    for r in records:
        n = r["chunk_count"]
        if n == 0:
            chunk_per_paper_buckets["0"] += 1
        elif n == 1:
            chunk_per_paper_buckets["1"] += 1
        elif n <= 5:
            chunk_per_paper_buckets["2-5"] += 1
        elif n <= 20:
            chunk_per_paper_buckets["6-20"] += 1
        elif n <= 50:
            chunk_per_paper_buckets["21-50"] += 1
        else:
            chunk_per_paper_buckets["50+"] += 1

    print()
    print("=" * 72)
    print("CHUNKING QUALITY REPORT")
    print("=" * 72)
    print(f"Papers analyzed      : {total}")
    print(f"Extract succeeded    : {extract_ok} ({extract_ok / total * 100:.1f}%)")
    print(f"Image-only / empty   : {no_text} ({no_text / total * 100:.1f}%)")
    print(f"Has chunks           : {chunked} ({chunked / total * 100:.1f}%)")
    print(f"Total chars          : {total_chars:,}")
    print(f"Total chunks         : {total_chunks:,}")
    print(f"Avg chunks per paper : {total_chunks / max(chunked, 1):.2f}")
    print()
    print("--- Section detection ---")
    print(f"  Multi-section      : {multi_section} ({multi_section / total * 100:.1f}%)")
    print(f"  All 'Full Text'    : {all_full_text} ({all_full_text / total * 100:.1f}%)")
    print()
    print("--- Chunk size anomalies ---")
    print(f"  Oversized (>2500c) : {oversized} ({oversized / total * 100:.1f}%)")
    print(f"  Tiny (<100c)       : {tiny} ({tiny / total * 100:.1f}%)")
    print()
    print("--- Chunks per paper ---")
    for k in ["0", "1", "2-5", "6-20", "21-50", "50+"]:
        n = chunk_per_paper_buckets.get(k, 0)
        print(f"  {k:>5} papers : {n}")
    print()
    print("--- Top section labels ---")
    for label, n in section_label_counter.most_common(30):
        print(f"  {n:>4}  {label!r}")
    print()
    print(f"Elapsed: {elapsed:.1f}s ({elapsed / max(total, 1):.3f}s per paper)")
    print("=" * 72)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "summary": {
                    "total": total,
                    "extract_ok": extract_ok,
                    "no_text": no_text,
                    "chunked": chunked,
                    "multi_section": multi_section,
                    "all_full_text": all_full_text,
                    "oversized": oversized,
                    "tiny": tiny,
                    "total_chunks": total_chunks,
                    "total_chars": total_chars,
                    "elapsed": elapsed,
                },
                "records": records,
            },
            f,
            indent=2,
        )
    print(f"Detailed records saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
