"""End-to-end pipeline throughput test on 20 papers.

Runs the full hot-path pipeline the app uses in production:

    router.extract_with_routing(pdf_path)         # fast tier, fallback if needed
        -> chunk_text(text)                        # section detection + chunking
        -> score_quality(text)                     # 5-signal quality audit
        -> _classify_chunk_text(text)              # content type (narrative/equation/...)

Skips the embedding API call because that's a remote dependency; the
extraction + chunking + scoring cost is what the new architecture
(Phase 4 + Phase 1) actually changes. Latency reported is end-to-end
per paper.

Usage:

    uv run python scripts/benchmark_pipeline_throughput.py
    uv run python scripts/benchmark_pipeline_throughput.py --limit 20 --workers 2
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.pdf_extraction.quality import (  # noqa: E402
    DEFAULT_MIN_SCORE,
    GOOD_SCORE,
)
from app.services.pdf_extraction.router import (  # noqa: E402
    extract_with_routing,
    register_optional_fallback_engines,
)
from app.services.pdf_fulltext import chunk_text  # noqa: E402


@dataclass(frozen=True)
class PipelineTiming:
    """End-to-end timing for one paper."""

    file: str
    bytes: int
    fast_tier_seconds: float
    fallback_seconds: float
    chunk_seconds: float
    total_seconds: float
    engine: str
    fell_back: bool
    score: float
    chars: int
    chunks: int
    chunks_by_type: dict[str, int]
    used_fallback: bool


def run_one(pdf_path: Path) -> PipelineTiming | None:
    """Run the full pipeline on one PDF and return timing metadata."""
    file_size = pdf_path.stat().st_size

    # Stage 1: extraction via router (may invoke Docling fallback).
    extract_start = time.perf_counter()
    result = extract_with_routing(pdf_path)
    text = result.text
    total_extract = time.perf_counter() - extract_start

    # Split timing: fast tier is always run; fallback only when triggered.
    # We approximate fast-tier time by the chunk-of-time before fallback
    # kicks in. Because the router does not surface per-engine timings,
    # we estimate: if a fallback was used, fast tier took some share and
    # fallback the rest. With two engines on the fast tier averaging ~0.5s
    # each, give 1.0s to fast tier and the rest to fallback.
    used_fallback = result.engine not in ("pdf_oxide", "pypdf", "")
    if used_fallback and total_extract > 1.0:
        fast_tier_seconds = 1.0
        fallback_seconds = total_extract - 1.0
    else:
        fast_tier_seconds = total_extract
        fallback_seconds = 0.0

    # Stage 2: chunking.
    chunk_start = time.perf_counter()
    chunks = chunk_text(text or "")
    chunk_seconds = time.perf_counter() - chunk_start

    chunks_by_type: dict[str, int] = {}
    for c in chunks:
        chunks_by_type[c.chunk_type] = chunks_by_type.get(c.chunk_type, 0) + 1

    return PipelineTiming(
        file=pdf_path.name,
        bytes=file_size,
        fast_tier_seconds=round(fast_tier_seconds, 3),
        fallback_seconds=round(fallback_seconds, 3),
        chunk_seconds=round(chunk_seconds, 3),
        total_seconds=round(total_extract + chunk_seconds, 3),
        engine=result.engine,
        fell_back=result.fell_back,
        score=round(result.quality.score, 4),
        chars=result.quality.char_count,
        chunks=len(chunks),
        chunks_by_type=chunks_by_type,
        used_fallback=used_fallback,
    )


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (p / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def summarise(timings: list[PipelineTiming], wall_clock: float, workers: int) -> dict:
    fast_only = [t for t in timings if not t.used_fallback]
    with_fallback = [t for t in timings if t.used_fallback]

    def _stats(values: list[float]) -> dict:
        if not values:
            return {"count": 0}
        return {
            "count": len(values),
            "mean": round(statistics.mean(values), 3),
            "median": round(statistics.median(values), 3),
            "p90": round(percentile(values, 90), 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
        }

    total_secs = [t.total_seconds for t in timings]
    extract_secs = [t.fast_tier_seconds + t.fallback_seconds for t in timings]
    chunk_secs = [t.chunk_seconds for t in timings]
    fast_secs = [t.fast_tier_seconds for t in fast_only]
    fallback_secs = [t.fallback_seconds for t in with_fallback]
    scores = [t.score for t in timings]

    return {
        "papers": len(timings),
        "workers": workers,
        "wall_clock_seconds": round(wall_clock, 3),
        "fast_tier_only": {
            "count": len(fast_only),
            "pct": round(len(fast_only) / max(len(timings), 1) * 100, 1),
            "timing": _stats(fast_secs),
        },
        "with_fallback": {
            "count": len(with_fallback),
            "pct": round(len(with_fallback) / max(len(timings), 1) * 100, 1),
            "timing": _stats(fallback_secs),
        },
        "extraction_stage": _stats(extract_secs),
        "chunking_stage": _stats(chunk_secs),
        "end_to_end": _stats(total_secs),
        "score_distribution": {
            "above_good": sum(1 for s in scores if s >= GOOD_SCORE),
            "below_min": sum(1 for s in scores if s < DEFAULT_MIN_SCORE),
            "mean": round(statistics.mean(scores), 4) if scores else 0.0,
        },
        "throughput": {
            "papers_per_second": round(len(timings) / max(wall_clock, 0.001), 3),
            "effective_seconds_per_paper": round(wall_clock / max(len(timings), 1), 3),
        },
    }


def print_report(timings: list[PipelineTiming], summary: dict) -> None:
    print()
    print("=" * 80)
    print("END-TO-END PIPELINE THROUGHPUT TEST")
    print("=" * 80)
    print(f"Papers: {summary['papers']}  Workers: {summary['workers']}")
    print(f"Wall clock: {summary['wall_clock_seconds']:.2f}s")
    print(f"Throughput: {summary['throughput']['papers_per_second']:.3f} papers/s "
          f"(= {summary['throughput']['effective_seconds_per_paper']:.2f}s/paper wall clock)")
    print()
    print(f"Fast-tier only: {summary['fast_tier_only']['count']} papers "
          f"({summary['fast_tier_only']['pct']}%)")
    f = summary["fast_tier_only"]["timing"]
    if f.get("count"):
        print(f"  per-paper latency: mean={f['mean']:.2f}s  median={f['median']:.2f}s  "
              f"p90={f['p90']:.2f}s  max={f['max']:.2f}s")
    print()
    print(f"With fallback (Docling): {summary['with_fallback']['count']} papers "
          f"({summary['with_fallback']['pct']}%)")
    fb = summary["with_fallback"]["timing"]
    if fb.get("count"):
        print(f"  per-paper latency: mean={fb['mean']:.2f}s  median={fb['median']:.2f}s  "
              f"p90={fb['p90']:.2f}s  max={fb['max']:.2f}s")
    print()
    print("End-to-end per-paper timing (extract + chunk):")
    e = summary["end_to_end"]
    print(f"  mean={e['mean']:.2f}s  median={e['median']:.2f}s  p90={e['p90']:.2f}s  "
          f"max={e['max']:.2f}s")
    print()
    print("Score distribution:")
    sd = summary["score_distribution"]
    print(f"  above GOOD_SCORE: {sd['above_good']}/{summary['papers']}  "
          f"below min: {sd['below_min']}/{summary['papers']}  "
          f"mean: {sd['mean']:.3f}")
    print()
    print("Per-paper table (sorted by total time):")
    print(f"  {'file':<55} {'engine':<10} {'secs':>6} {'score':>6} {'chunks':>7}")
    sorted_t = sorted(timings, key=lambda t: t.total_seconds, reverse=True)
    for t in sorted_t:
        marker = "*" if t.used_fallback else " "
        print(f"  {marker}{t.file:<54} {t.engine:<10} {t.total_seconds:>6.2f} "
              f"{t.score:>6.3f} {t.chunks:>7}")
    print()
    print("Legend: * = used Docling fallback")


def select_papers(pdf_dir: Path, n: int) -> list[Path]:
    """Pick *n* papers stratified across score zones.

    Reads the prior corpus benchmark to find paper names in each zone
    (above_good / between / below_min) so the test exercises both fast
    tier and Docling fallback paths proportionally.
    """
    baseline = Path("data/local_pdf_full_extract/quality-benchmark-full.json")
    if not baseline.exists():
        # Fall back to first N alphabetical
        return sorted(pdf_dir.glob("*.pdf"))[:n]

    data = json.loads(baseline.read_text())
    papers = [p for p in data["papers"] if not p.get("error")]

    above_good = [p for p in papers if p["score"] >= GOOD_SCORE]
    between = [p for p in papers if DEFAULT_MIN_SCORE <= p["score"] < GOOD_SCORE]
    below_min = [p for p in papers if p["score"] < DEFAULT_MIN_SCORE]

    # 70% from above_good, 25% from between, 5% from below_min — matches
    # the production distribution observed in the 244-paper corpus.
    n_above = max(1, int(n * 0.70))
    n_between = max(0, int(n * 0.25))
    n_below = n - n_above - n_between

    # Sort each bucket deterministically.
    above_good.sort(key=lambda p: p["file"])
    between.sort(key=lambda p: p["score"])
    below_min.sort(key=lambda p: p["score"])

    chosen: list[Path] = []
    for p in above_good[:n_above] + between[:n_between] + below_min[:n_below]:
        path = pdf_dir / p["file"]
        if path.exists():
            chosen.append(path)
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end pipeline throughput test.")
    # Register Docling (or any other installed fallback engines) so the
    # router can actually exercise the fallback tier.
    registered = register_optional_fallback_engines()
    if registered:
        print(f"Fallback engines registered: {', '.join(registered)}")
    else:
        print("WARNING: no fallback engines registered — Docling fallback will not run.")
        print("Install with: uv sync --extra docling")
    print()

    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of papers to test (default 20).",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path("data/papers"),
        help="Directory of PDFs.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel workers. Use 0 for ProcessPoolExecutor "
        "(true parallelism via separate processes).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/local_pdf_full_extract/pipeline-throughput.json"),
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    pdfs = select_papers(args.pdf_dir, args.limit)
    if not pdfs:
        raise SystemExit(f"No PDFs found under {args.pdf_dir}")

    print(f"Testing pipeline on {len(pdfs)} papers (workers={args.workers})")
    print(f"PDF dir: {args.pdf_dir}")
    print()

    timings: list[PipelineTiming] = []
    wall_start = time.perf_counter()

    if args.workers == 0:
        # True parallelism via separate processes (sidesteps the GIL).
        # Each worker re-imports docling if it uses it, so the model
        # load cost is paid once per worker. Cap at min(len, cpu_count).
        max_workers = min(len(pdfs), multiprocessing.cpu_count())
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_one, p): p for p in pdfs}
            for future in as_completed(futures):
                t = future.result()
                if t is None:
                    continue
                timings.append(t)
                marker = "*" if t.used_fallback else " "
                print(
                    f"  [{marker}] {t.file:<55} engine={t.engine:<10} "
                    f"secs={t.total_seconds:>6.2f} score={t.score:.3f}",
                    flush=True,
                )
    elif args.workers <= 1:
        for pdf in pdfs:
            t = run_one(pdf)
            if t is None:
                continue
            timings.append(t)
            marker = "*" if t.used_fallback else " "
            print(
                f"  [{marker}] {t.file:<55} engine={t.engine:<10} "
                f"secs={t.total_seconds:>6.2f} score={t.score:.3f}",
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_one, p): p for p in pdfs}
            for future in as_completed(futures):
                t = future.result()
                if t is None:
                    continue
                timings.append(t)
                marker = "*" if t.used_fallback else " "
                print(
                    f"  [{marker}] {t.file:<55} engine={t.engine:<10} "
                    f"secs={t.total_seconds:>6.2f} score={t.score:.3f}",
                    flush=True,
                )

    wall_clock = time.perf_counter() - wall_start
    summary = summarise(timings, wall_clock, args.workers)
    summary["created_at"] = datetime.now(UTC).isoformat()

    print_report(timings, summary)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "summary": summary,
            "papers": [asdict(t) for t in timings],
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()