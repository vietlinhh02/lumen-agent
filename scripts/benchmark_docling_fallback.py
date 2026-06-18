"""Compare the fast-tier (pdf_oxide + pypdf) against Docling on papers
where the fast tier scored below GOOD_SCORE.

The benchmark reads the prior corpus run from
``data/local_pdf_full_extract/quality-benchmark-full.json`` (produced by
``benchmark_extraction_quality.py``), selects papers in the
``in-between`` zone (``0.45 <= score < 0.85``) plus any that fell
below ``min_score``, runs :class:`DoclingEngine` on each, and reports
the per-paper score lift.

Why this exists:

Before Phase 1 we had no evidence Docling was worth its install cost.
This benchmark answers the question: *for the papers the fast tier
handles poorly, does Docling actually improve the score?* If yes,
register Docling as a fallback in production. If no, the heavy
install is unjustified and Phase 1 should be re-scoped.

Usage:

    uv sync --extra docling
    uv run python scripts/benchmark_docling_fallback.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.pdf_extraction.engines.docling import DoclingEngine  # noqa: E402
from app.services.pdf_extraction.quality import GOOD_SCORE, score_quality  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare fast-tier vs Docling on papers the fast tier scores poorly."
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=Path("data/local_pdf_full_extract/quality-benchmark-full.json"),
        help="JSON output of benchmark_extraction_quality.py",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of papers to test (after filtering).",
    )
    parser.add_argument(
        "--max-score",
        type=float,
        default=GOOD_SCORE,
        help=f"Run Docling on papers whose fast-tier score < this (default {GOOD_SCORE}).",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Skip papers whose fast-tier score is below this floor.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel Docling calls. Docling holds models in memory so "
        "more than 2 rarely helps.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/local_pdf_full_extract/docling-benchmark.json"),
        help="Where to write the comparison report.",
    )
    return parser.parse_args()


def filter_targets(
    baseline: list[dict], *, max_score: float, min_score: float, limit: int | None
) -> list[dict]:
    """Return the papers Docling should be tried on."""
    targets = [
        p
        for p in baseline
        if not p.get("error")
        and p.get("score") is not None
        and min_score <= p["score"] < max_score
    ]
    # Process the lowest-scoring papers first so a partial run still
    # yields useful signal.
    targets.sort(key=lambda p: p["score"])
    if limit is not None:
        targets = targets[:limit]
    return targets


def run_one(
    pdf_path: Path,
    docling: DoclingEngine,
    fast_baseline: dict,
) -> dict:
    """Run Docling on one paper and produce a comparison record."""
    started = time.perf_counter()
    error: str | None = None
    docling_text: str | None = None
    try:
        docling_text = docling.extract(pdf_path)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    q = score_quality(docling_text)
    return {
        "file": pdf_path.name,
        "fast_tier": {
            "engine": fast_baseline.get("engine"),
            "score": fast_baseline.get("score"),
            "chars": fast_baseline.get("char_count"),
        },
        "docling": {
            "score": round(q.score, 4),
            "density": round(q.density, 4),
            "alpha_ratio": round(q.alpha_ratio, 4),
            "structure": round(q.structure, 4),
            "mojibake": round(q.mojibake, 4),
            "column_order": round(q.column_order, 4),
            "chars": q.char_count,
            "weakest_signal": q.weakest_signal,
            "seconds": round(elapsed, 3),
            "error": error,
        },
    }


def score_lift(record: dict) -> float | None:
    """Return the score improvement Docling brings, or None on failure."""
    if record["docling"].get("error"):
        return None
    fast = record["fast_tier"].get("score")
    doc = record["docling"].get("score")
    if fast is None or doc is None:
        return None
    return doc - fast


def passes_good_bar(record: dict) -> bool:
    """True when Docling output clears the GOOD_SCORE bar."""
    return (
        record["docling"].get("score") is not None
        and record["docling"]["score"] >= GOOD_SCORE
    )


def summarise(records: list[dict], workers: int, total_seconds: float) -> dict:
    """Aggregate the per-paper comparison into a summary dict."""
    successful = [r for r in records if not r["docling"].get("error")]
    failed = [r for r in records if r["docling"].get("error")]
    lifts = [score_lift(r) for r in successful]
    lifts = [lift for lift in lifts if lift is not None]

    passes = sum(1 for r in successful if passes_good_bar(r))
    docling_seconds = [r["docling"]["seconds"] for r in successful if r["docling"].get("seconds")]

    # Bucket the score lift to summarise the impact distribution.
    big_win = sum(1 for lift in lifts if lift >= 0.10)
    moderate = sum(1 for lift in lifts if 0.03 <= lift < 0.10)
    tie = sum(1 for lift in lifts if -0.03 < lift < 0.03)
    regression = sum(1 for lift in lifts if lift <= -0.03)

    return {
        "papers_tested": len(records),
        "docling_succeeded": len(successful),
        "docling_failed": len(failed),
        "passes_good_score": passes,
        "score_lift": {
            "mean": round(statistics.mean(lifts), 4) if lifts else 0.0,
            "median": round(statistics.median(lifts), 4) if lifts else 0.0,
            "p10": round(sorted(lifts)[int(len(lifts) * 0.1)], 4) if len(lifts) >= 10 else None,
            "max": round(max(lifts), 4) if lifts else 0.0,
            "min": round(min(lifts), 4) if lifts else 0.0,
        },
        "buckets": {
            "big_win_>=0.10": big_win,
            "moderate_0.03_to_0.10": moderate,
            "tie_within_0.03": tie,
            "regression_<=-0.03": regression,
        },
        "timing_seconds": {
            "mean": round(statistics.mean(docling_seconds), 2) if docling_seconds else 0,
            "median": round(statistics.median(docling_seconds), 2) if docling_seconds else 0,
            "p90": round(sorted(docling_seconds)[int(len(docling_seconds) * 0.9)], 2)
            if len(docling_seconds) >= 10
            else None,
            "wall_clock_total": round(total_seconds, 1),
            "workers": workers,
        },
    }


def print_summary(summary: dict) -> None:
    print()
    print("=" * 78)
    print("DOCLING FALLBACK BENCHMARK")
    print("=" * 78)
    print(f"Papers tested: {summary['papers_tested']}")
    print(f"  Docling succeeded: {summary['docling_succeeded']}")
    print(f"  Docling failed:    {summary['docling_failed']}")
    print()
    print(f"Papers now clearing GOOD_SCORE ({GOOD_SCORE:.2f}): "
          f"{summary['passes_good_score']} / {summary['docling_succeeded']}")
    print()
    print("Score lift (Docling − fast tier):")
    lift = summary["score_lift"]
    print(f"  mean={lift['mean']:+.4f}  median={lift['median']:+.4f}  "
          f"min={lift['min']:+.4f}  max={lift['max']:+.4f}")
    if lift.get("p10") is not None:
        print(f"  p10={lift['p10']:+.4f}")
    print()
    print("Lift distribution:")
    for name, count in summary["buckets"].items():
        pct = round(count / max(summary["docling_succeeded"], 1) * 100, 1)
        print(f"  {name:30s} {count:4d}  ({pct}%)")
    print()
    print("Per-paper Docling latency (seconds):")
    timing = summary["timing_seconds"]
    print(f"  mean={timing['mean']:.2f}  median={timing['median']:.2f}  "
          f"p90={timing.get('p90')}")
    print(f"  wall_clock_total={timing['wall_clock_total']:.1f}s  workers={timing['workers']}")
    print()
    if summary["buckets"]["regression_<=-0.03"] > 0:
        print("WARNING: Docling regressed on some papers. Inspect the per-paper report.")
    elif (
        summary["buckets"]["big_win_>=0.10"] >= summary["docling_succeeded"] // 2
        and summary["buckets"]["regression_<=-0.03"] == 0
    ):
        print("CONCLUSION: Docling fallback is justified for this corpus.")
    else:
        print("CONCLUSION: Mixed results — review per-paper report before enabling.")


def main() -> None:
    args = parse_args()

    if not args.baseline_report.exists():
        raise SystemExit(
            f"Baseline report not found at {args.baseline_report}. "
            "Run scripts/benchmark_extraction_quality.py first."
        )

    baseline_data = json.loads(args.baseline_report.read_text())
    baseline_papers = baseline_data.get("papers", [])
    targets = filter_targets(
        baseline_papers,
        max_score=args.max_score,
        min_score=args.min_score,
        limit=args.limit,
    )

    if not targets:
        print(f"No papers found with score in [{args.min_score}, {args.max_score})")
        return

    print(f"Comparing Docling against fast tier on {len(targets)} papers")
    print(f"Filter: score in [{args.min_score}, {args.max_score})")

    # Warm up Docling once before timing — the first call downloads
    # ~500MB of models and is not representative of per-paper cost.
    print("Warming up Docling (one-time model load)...")
    warmup_start = time.perf_counter()
    docling = DoclingEngine()
    _ = docling.extract(Path("data/papers/2106.15553.pdf"))
    print(f"  warmup: {time.perf_counter() - warmup_start:.1f}s")

    started = time.perf_counter()
    records: list[dict] = []
    pdf_dir = Path("data/papers")

    def _run(target: dict) -> dict:
        pdf_path = pdf_dir / target["file"]
        if not pdf_path.exists():
            return {
                "file": target["file"],
                "fast_tier": {
                    "engine": target.get("engine"),
                    "score": target.get("score"),
                    "chars": target.get("char_count"),
                },
                "docling": {
                    "score": None,
                    "chars": 0,
                    "weakest_signal": None,
                    "seconds": 0.0,
                    "error": "PDF file not found",
                },
            }
        return run_one(pdf_path, docling, target)

    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        futures = {executor.submit(_run, t): t for t in targets}
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            fast_score = record["fast_tier"].get("score") or 0.0
            doc_score = record["docling"].get("score")
            doc_str = f"{doc_score:.3f}" if doc_score is not None else "FAIL"
            lift_str = ""
            if doc_score is not None:
                lift = doc_score - fast_score
                lift_str = f"  lift={lift:+.3f}"
            err = record["docling"].get("error")
            err_str = f"  ERR: {err[:50]}" if err else ""
            print(
                f"  [{doc_str}] {record['file']:60s} fast={fast_score:.3f}{lift_str}{err_str}",
                flush=True,
            )

    total_seconds = time.perf_counter() - started
    summary = summarise(records, args.workers, total_seconds)
    summary["created_at"] = datetime.now(UTC).isoformat()
    summary["filter"] = {"min_score": args.min_score, "max_score": args.max_score}

    print_summary(summary)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {"summary": summary, "papers": records}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()