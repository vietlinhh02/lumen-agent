"""Download arXiv bulk metadata dump, filter by CS categories, extract text.

This downloads the arXiv dataset from Kaggle (~3.5GB JSON),
filters to computer science papers, and saves as clean JSONL.

arXiv Kaggle dataset: cornell-university/arxiv
- 2.5M+ papers with metadata + abstracts
- Source: https://www.kaggle.com/datasets/Cornell-University/arxiv

Usage:
    python scripts/dump_arxiv.py --categories cs.AI,cs.CL,cs.IR --out data/arxiv_dump
    python scripts/dump_arxiv.py --all-cs --out data/arxiv_dump --max 10000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import kagglehub  # type: ignore[import-untyped]

CS_CATEGORIES = {
    "cs.AI", "cs.AR", "cs.CC", "cs.CE", "cs.CG", "cs.CL", "cs.CR",
    "cs.CV", "cs.CY", "cs.DB", "cs.DC", "cs.DL", "cs.DM", "cs.DS",
    "cs.ET", "cs.FL", "cs.GL", "cs.GR", "cs.GT", "cs.HC", "cs.IR",
    "cs.IT", "cs.LG", "cs.LO", "cs.MA", "cs.MM", "cs.MS", "cs.NA",
    "cs.NE", "cs.NI", "cs.OH", "cs.OS", "cs.PF", "cs.PL", "cs.RO",
    "cs.SC", "cs.SD", "cs.SE", "cs.SI", "cs.SY",
}


def eprint(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)


def download_arxiv_dataset() -> Path:
    """Download the arXiv metadata snapshot from Kaggle. Returns path to JSON file."""
    eprint("[kaggle] downloading arXiv dataset (~3.5GB, one-time)...")
    t0 = time.time()
    path = kagglehub.dataset_download("Cornell-University/arxiv")
    elapsed = time.time() - t0
    eprint(f"[kaggle] downloaded to {path} in {elapsed:.0f}s")
    json_path = Path(path) / "arxiv-metadata-oai-snapshot.json"
    if not json_path.exists():
        for f in Path(path).glob("*.json"):
            json_path = f
            break
    return json_path


def matches_categories(paper_cats: str, target: set[str]) -> bool:
    """Check if paper categories intersect with target categories."""
    cats = {c.strip() for c in paper_cats.split()}
    return bool(cats & target)


def stream_papers(json_path: Path, target_cats: set[str], max_papers: int = 0):
    """Yield papers matching target categories."""
    count = 0
    with open(json_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                paper = json.loads(line)
            except json.JSONDecodeError:
                continue

            cats = paper.get("categories", "")
            if matches_categories(cats, target_cats):
                yield {
                    "id": paper.get("id", ""),
                    "title": paper.get("title", ""),
                    "authors": paper.get("authors_parsed", []) or [],
                    "abstract": paper.get("abstract", "").replace("\n", " "),
                    "categories": paper.get("categories", ""),
                    "year": paper.get("versions", [{}])[0].get("created", "")[:4] if paper.get("versions") else None,
                    "doi": paper.get("doi", ""),
                    "journal_ref": paper.get("journal-ref", ""),
                    "update_date": paper.get("update_date", ""),
                }
                count += 1
                if max_papers and count >= max_papers:
                    return


def main():
    parser = argparse.ArgumentParser(description="Download arXiv bulk data dump, filter by CS categories")
    parser.add_argument(
        "--categories", default="cs.AI,cs.CL,cs.IR,cs.LG,cs.CV",
        help="Comma-separated arXiv categories (default: cs.AI,cs.CL,cs.IR,cs.LG,cs.CV)"
    )
    parser.add_argument(
        "--all-cs", action="store_true",
        help="Include ALL computer science categories (40+)"
    )
    parser.add_argument("--max", type=int, default=0, help="Max papers to save (0 = all)")
    parser.add_argument("--out", default="data/arxiv_dump", help="Output directory")
    parser.add_argument(
        "--download-source", action="store_true",
        help="Also download LaTeX source tarballs for full text (much slower)"
    )

    args = parser.parse_args()

    target_cats = CS_CATEGORIES if args.all_cs else {c.strip() for c in args.categories.split(",")}
    eprint(f"[filter] categories: {sorted(target_cats)}")

    json_path = download_arxiv_dataset()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save all filtered papers as JSONL
    jsonl_path = out_dir / "cs_papers.jsonl"
    eprint(f"[write] saving to {jsonl_path}")

    count = 0
    with open(jsonl_path, "w") as out:
        for paper in stream_papers(json_path, target_cats, args.max):
            out.write(json.dumps(paper, ensure_ascii=False) + "\n")
            count += 1
            if count % 1000 == 0:
                eprint(f"[progress] {count} papers...")

    eprint(f"\n[done] {count} papers saved to {jsonl_path}")
    eprint(f"[size] {(jsonl_path.stat().st_size / 1024 / 1024):.1f} MB")


if __name__ == "__main__":
    main()
