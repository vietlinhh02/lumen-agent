"""Benchmark the 5-signal quality scorer on a corpus of real PDFs.

Runs :func:`app.services.pdf_extraction.extract_with_routing` over a
folder of PDFs and prints a distribution report of the composite and
per-signal scores. Useful for two purposes:

1. **Calibration**: see whether the GOOD_SCORE / DEFAULT_MIN_SCORE
   thresholds match real-world extraction quality.
2. **Engine comparison**: see how often pdf_oxide wins vs pypdf and
   where the two engines disagree most strongly.

Usage:

    uv run python scripts/benchmark_extraction_quality.py data/papers/
    uv run python scripts/benchmark_extraction_quality.py data/papers/ --limit 50 --output report.json
"""  # noqa: E501

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    list_registered_engines,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark the 5-signal quality scorer on a PDF corpus."
    )
    parser.add_argument("inputs", nargs="+", help="PDF files or directories.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N PDFs (after sorting).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel worker processes.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the full per-paper report to this JSON path.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help=f"Min score for self-healing fallback (default {DEFAULT_MIN_SCORE}).",
    )
    parser.add_argument(
        "--good-score",
        type=float,
        default=GOOD_SCORE,
        help=f"Good extraction threshold (default {GOOD_SCORE}).",
    )
    return parser.parse_args()


def collect_pdfs(inputs: list[str]) -> list[Path]:
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
    unique = sorted({p.resolve() for p in paths})
    if not unique:
        raise SystemExit("No PDF files found.")
    return unique


def evaluate_one_pdf(pdf_path_str: str, min_score: float) -> dict:
    """Run the router on one PDF and return a flat score dict.

    Lives at module scope so :class:`ProcessPoolExecutor` can pickle it.
    """
    pdf_path = Path(pdf_path_str)
    started = time.perf_counter()
    try:
        result = extract_with_routing(pdf_path, min_score=min_score)
        seconds = time.perf_counter() - started
    except Exception as exc:
        return {
            "file": pdf_path.name,
            "error": f"{type(exc).__name__}: {exc}",
            "seconds": round(time.perf_counter() - started, 3),
        }

    q = result.quality
    return {
        "file": pdf_path.name,
        "engine": result.engine,
        "score": round(q.score, 4),
        "density": round(q.density, 4),
        "alpha_ratio": round(q.alpha_ratio, 4),
        "structure": round(q.structure, 4),
        "mojibake": round(q.mojibake, 4),
        "column_order": round(q.column_order, 4),
        "char_count": q.char_count,
        "weakest_signal": q.weakest_signal,
        "fell_back": result.fell_back,
        "engines_tried": [name for name, _ in result.tried],
        "seconds": round(seconds, 3),
        "error": None,
    }


def percentile(values: list[float], p: float) -> float:
    """Return the *p*-th percentile (0..100) of *values*."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (p / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarise(results: list[dict], min_score: float, good_score: float) -> dict:
    """Aggregate the per-paper results into a distribution summary."""
    successful = [r for r in results if not r.get("error")]
    failed = [r for r in results if r.get("error")]

    def stat(name: str) -> dict:
        values = [r[name] for r in successful]
        if not values:
            return {"count": 0}
        return {
            "count": len(values),
            "mean": round(statistics.mean(values), 4),
            "median": round(statistics.median(values), 4),
            "p10": round(percentile(values, 10), 4),
            "p25": round(percentile(values, 25), 4),
            "p75": round(percentile(values, 75), 4),
            "p90": round(percentile(values, 90), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    # Score distribution buckets — matches the thresholds used in routing.
    above_good = sum(1 for r in successful if r["score"] >= good_score)
    below_min = sum(1 for r in successful if r["score"] < min_score)
    in_between = len(successful) - above_good - below_min

    # Weakest signal distribution — tells us which signal fails most.
    weakest: dict[str, int] = {}
    for r in successful:
        weakest[r["weakest_signal"]] = weakest.get(r["weakest_signal"], 0) + 1

    # Engine winner distribution.
    engines: dict[str, int] = {}
    for r in successful:
        engine = r.get("engine") or "<none>"
        engines[engine] = engines.get(engine, 0) + 1

    seconds = [r.get("seconds", 0.0) for r in results]
    char_counts = [r.get("char_count", 0) for r in successful]

    return {
        "pdf_count": len(results),
        "successful": len(successful),
        "failed": len(failed),
        "thresholds": {"good_score": good_score, "min_score": min_score},
        "score_distribution": {
            "above_good_score": above_good,
            "between_min_and_good": in_between,
            "below_min_score": below_min,
            "above_good_pct": round(above_good / max(len(successful), 1) * 100, 1),
            "below_min_pct": round(below_min / max(len(successful), 1) * 100, 1),
        },
        "weakest_signal_counts": weakest,
        "engine_winner_counts": engines,
        "signals": {
            "score": stat("score"),
            "density": stat("density"),
            "alpha_ratio": stat("alpha_ratio"),
            "structure": stat("structure"),
            "mojibake": stat("mojibake"),
            "column_order": stat("column_order"),
        },
        "char_count": {
            "mean": round(statistics.mean(char_counts), 1) if char_counts else 0,
            "median": round(statistics.median(char_counts), 1) if char_counts else 0,
            "p10": round(percentile(char_counts, 10), 1) if char_counts else 0,
            "p90": round(percentile(char_counts, 90), 1) if char_counts else 0,
        },
        "timing_seconds": {
            "mean": round(statistics.mean(seconds), 3) if seconds else 0,
            "median": round(statistics.median(seconds), 3) if seconds else 0,
            "total": round(sum(seconds), 3),
        },
    }


def print_summary(summary: dict, engines: list[str]) -> None:
    """Pretty-print the summary to stdout."""
    print()
    print("=" * 72)
    print("PDF EXTRACTION QUALITY BENCHMARK")
    print("=" * 72)
    print(f"PDFs processed : {summary['pdf_count']}")
    print(f"  successful   : {summary['successful']}")
    print(f"  failed       : {summary['failed']}")
    print()
    print(f"Engines tried in order: {', '.join(engines)}")
    print()
    print(f"Score thresholds: good >= {summary['thresholds']['good_score']}, "
          f"min >= {summary['thresholds']['min_score']}")
    dist = summary["score_distribution"]
    print(
        f"Score distribution: above_good={dist['above_good_score']} "
        f"({dist['above_good_pct']}%) | "
        f"between={dist['between_min_and_good']} | "
        f"below_min={dist['below_min_score']} ({dist['below_min_pct']}%)"
    )
    print()
    print("Engine winner distribution:")
    for engine, count in sorted(summary["engine_winner_counts"].items(), key=lambda kv: -kv[1]):
        pct = round(count / max(summary["successful"], 1) * 100, 1)
        print(f"  {engine:20s} {count:5d}  ({pct}%)")
    print()
    print("Weakest-signal distribution (most actionable failure indicator):")
    for signal, count in sorted(summary["weakest_signal_counts"].items(), key=lambda kv: -kv[1]):
        pct = round(count / max(summary["successful"], 1) * 100, 1)
        print(f"  {signal:20s} {count:5d}  ({pct}%)")
    print()
    print("Per-signal statistics (0..1 scale):")
    print(f"  {'signal':<14} {'mean':>8} {'p10':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p90':>8}")
    for signal_name, stats in summary["signals"].items():
        if not stats.get("count"):
            continue
        print(
            f"  {signal_name:<14} "
            f"{stats['mean']:>8.3f} {stats['p10']:>8.3f} {stats['p25']:>8.3f} "
            f"{stats['median']:>8.3f} {stats['p75']:>8.3f} {stats['p90']:>8.3f}"
        )
    print()
    print("Char counts:", summary["char_count"])
    print("Timing seconds:", summary["timing_seconds"])


def main() -> None:
    args = parse_args()
    pdfs = collect_pdfs(args.inputs)
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    engines = list_registered_engines()
    print(f"Benchmarking {len(pdfs)} PDFs against engines: {', '.join(engines)}")
    print(f"Thresholds: good={args.good_score}, min={args.min_score}")

    started = time.perf_counter()
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        futures = {
            executor.submit(evaluate_one_pdf, str(p), args.min_score): p for p in pdfs
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "FAIL" if result.get("error") else "OK"
            score = result.get("score")
            score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
            engine = result.get("engine") or "-"
            print(
                f"  [{status}] {result['file']:30s} engine={engine:10s} score={score_str}",
                flush=True,
            )

    total_seconds = time.perf_counter() - started
    summary = summarise(results, args.min_score, args.good_score)
    summary["wall_clock_seconds"] = round(total_seconds, 3)
    summary["engines"] = engines
    summary["created_at"] = datetime.now(UTC).isoformat()

    print_summary(summary, engines)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "summary": summary,
            "papers": results,
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()