"""Compare the three PDF extraction modes on the same 20-paper corpus.

Modes:
    1. **fast_only** — pdf_oxide + pypdf, no Docling. Baseline.
    2. **docling_fallback** — fast tier as primary, Docling only when
       fast tier falls below the routing threshold. Phase 1 default.
    3. **docling_primary** — Docling first in fast tier, pdf_oxide /
       pypdf as backup. New experiment.

Reports per-mode: per-paper score, engine winner distribution,
extraction latency (mean / median / p90 / max), and percentage of
papers now clearing the GOOD_SCORE bar.

Usage:

    uv run python scripts/benchmark_docling_primary.py
    uv run python scripts/benchmark_docling_primary.py --workers 0
"""

from __future__ import annotations

import argparse
import json
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

from app.services.pdf_extraction.quality import GOOD_SCORE, score_quality  # noqa: E402
from app.services.pdf_extraction.router import (  # noqa: E402
    PdfOxideEngine,
    PyPdfEngine,
    _DEFAULT_ENGINES,
    _FALLBACK_ENGINES,
    extract_with_routing,
)


@dataclass(frozen=True)
class PaperRun:
    """One paper × one mode result."""

    file: str
    engine: str
    score: float
    fell_back: bool
    seconds: float
    chars: int
    error: str | None


def configure_mode(mode: str) -> str:
    """Reset the global engine registry to match *mode*.

    Returns a one-line description of what was configured, for logging.
    """
    # Wipe both tiers so modes don't leak into each other.
    _DEFAULT_ENGINES.clear()
    _FALLBACK_ENGINES.clear()
    _DEFAULT_ENGINES.extend([PdfOxideEngine(), PyPdfEngine()])

    if mode == "fast_only":
        return "fast tier only (pdf_oxide + pypdf), no fallback"

    if mode == "docling_fallback":
        from app.services.pdf_extraction import register_optional_fallback_engines

        names = register_optional_fallback_engines()
        if not names:
            return (
                "fast tier only — Docling not installed. "
                "Install with: uv sync --extra docling"
            )
        return f"fast tier + Docling fallback ({names[0]})"

    if mode == "docling_primary":
        from app.services.pdf_extraction import register_layout_engines_as_primary

        names = register_layout_engines_as_primary()
        if not names:
            return (
                "fast tier only — Docling not installed. "
                "Install with: uv sync --extra docling"
            )
        return f"Docling primary ({names[0]}) + fast tier backup"

    raise ValueError(f"Unknown mode: {mode}")


def run_one(pdf_path: Path, mode: str, min_score: float) -> PaperRun:
    """Run one paper through the configured router."""
    started = time.perf_counter()
    error: str | None = None
    engine = ""
    score = 0.0
    chars = 0
    fell_back = False
    try:
        result = extract_with_routing(pdf_path, min_score=min_score)
        engine = result.engine
        score = result.quality.score
        chars = result.quality.char_count
        fell_back = result.fell_back
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    seconds = time.perf_counter() - started
    return PaperRun(
        file=pdf_path.name,
        engine=engine,
        score=round(score, 4),
        fell_back=fell_back,
        seconds=round(seconds, 3),
        chars=chars,
        error=error,
    )


def _run_for_pool(args_tuple: tuple[Path, str, float]) -> PaperRun:
    """Module-level wrapper so ProcessPoolExecutor can pickle it."""
    pdf_path, mode, min_score = args_tuple
    return run_one(pdf_path, mode, min_score)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (p / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def summarise(runs: list[PaperRun]) -> dict:
    successful = [r for r in runs if not r.error]
    failed = [r for r in runs if r.error]
    secs = [r.seconds for r in successful]
    scores = [r.score for r in successful]
    engines: dict[str, int] = {}
    for r in successful:
        engines[r.engine] = engines.get(r.engine, 0) + 1
    return {
        "papers": len(runs),
        "successful": len(successful),
        "failed": len(failed),
        "above_good_score": sum(1 for s in scores if s >= GOOD_SCORE),
        "score": {
            "mean": round(statistics.mean(scores), 4) if scores else 0.0,
            "median": round(statistics.median(scores), 4) if scores else 0.0,
            "min": round(min(scores), 4) if scores else 0.0,
            "max": round(max(scores), 4) if scores else 0.0,
        },
        "timing_seconds": {
            "mean": round(statistics.mean(secs), 3) if secs else 0.0,
            "median": round(statistics.median(secs), 3) if secs else 0.0,
            "p90": round(percentile(secs, 90), 3) if secs else 0.0,
            "max": round(max(secs), 3) if secs else 0.0,
        },
        "engine_winners": engines,
    }


def print_mode_report(mode: str, runs: list[PaperRun], summary: dict, wall_clock: float) -> None:
    print()
    print("=" * 78)
    print(f"MODE: {mode}")
    print("=" * 78)
    print(f"Papers: {summary['papers']}  Successful: {summary['successful']}  "
          f"Failed: {summary['failed']}")
    print(f"Above GOOD_SCORE ({GOOD_SCORE}): {summary['above_good_score']}/"
          f"{summary['successful']}")
    print(f"Score mean={summary['score']['mean']:.3f}  median={summary['score']['median']:.3f}  "
          f"min={summary['score']['min']:.3f}  max={summary['score']['max']:.3f}")
    print(f"Timing: mean={summary['timing_seconds']['mean']:.2f}s  "
          f"median={summary['timing_seconds']['median']:.2f}s  "
          f"p90={summary['timing_seconds']['p90']:.2f}s  "
          f"max={summary['timing_seconds']['max']:.2f}s")
    print(f"Wall clock total: {wall_clock:.1f}s")
    print("Engine winners:")
    for engine, count in sorted(summary["engine_winners"].items(), key=lambda kv: -kv[1]):
        pct = round(count / max(summary["successful"], 1) * 100, 1)
        print(f"  {engine:12s} {count:4d}  ({pct}%)")


def select_papers(pdf_dir: Path, n: int) -> list[Path]:
    """Same paper-picking strategy as benchmark_pipeline_throughput.py."""
    baseline = Path("data/local_pdf_full_extract/quality-benchmark-full.json")
    if not baseline.exists():
        return sorted(pdf_dir.glob("*.pdf"))[:n]
    data = json.loads(baseline.read_text())
    papers = [p for p in data["papers"] if not p.get("error")]
    above = sorted([p for p in papers if p["score"] >= GOOD_SCORE], key=lambda p: p["file"])
    between = sorted(
        [p for p in papers if 0.45 <= p["score"] < GOOD_SCORE], key=lambda p: p["score"]
    )
    below = sorted([p for p in papers if p["score"] < 0.45], key=lambda p: p["score"])
    n_above = max(1, int(n * 0.70))
    n_between = max(0, int(n * 0.25))
    n_below = n - n_above - n_between
    chosen: list[Path] = []
    for p in above[:n_above] + between[:n_between] + below[:n_below]:
        path = pdf_dir / p["file"]
        if path.exists():
            chosen.append(path)
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare PDF extraction modes (fast / fallback / Docling primary)."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--pdf-dir", type=Path, default=Path("data/papers"))
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="0 = ProcessPoolExecutor (best for batch), 1 = sequential.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.45,
        help="Routing threshold; engines fall back when below this.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/local_pdf_full_extract/mode-comparison.json"),
    )
    args = parser.parse_args()

    pdfs = select_papers(args.pdf_dir, args.limit)
    if not pdfs:
        raise SystemExit(f"No PDFs found under {args.pdf_dir}")

    print(f"Benchmarking {len(pdfs)} papers across 3 modes")

    modes = ["fast_only", "docling_fallback", "docling_primary"]
    all_summaries: dict[str, dict] = {}
    all_runs: dict[str, list[PaperRun]] = {}

    for mode in modes:
        # Warm-up: Docling pays a 1-2 min model-load cost on first call
        # across all modes. We warm it up explicitly here so the
        # per-mode timings are comparable.
        print(f"\n>>> Configuring mode: {mode}")
        description = configure_mode(mode)
        print(f"    {description}")

        # Warm-up only matters when Docling is in play.
        if "docling" in mode:
            warmup_pdf = pdfs[0]
            print(f"    Warming up Docling on {warmup_pdf.name}...")
            warmup_start = time.perf_counter()
            try:
                run_one(warmup_pdf, mode, args.min_score)
            except Exception:
                pass
            print(f"    warmup: {time.perf_counter() - warmup_start:.1f}s")

        wall_start = time.perf_counter()
        runs: list[PaperRun] = []

        if args.workers == 0:
            import multiprocessing
            pool_args = [(p, mode, args.min_score) for p in pdfs]
            with ProcessPoolExecutor(
                max_workers=min(len(pdfs), multiprocessing.cpu_count())
            ) as executor:
                futures = {executor.submit(_run_for_pool, a): a[0] for a in pool_args}
                for future in as_completed(futures):
                    runs.append(future.result())
        elif args.workers <= 1:
            for p in pdfs:
                runs.append(run_one(p, mode, args.min_score))
        else:
            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = {
                    executor.submit(run_one, p, mode, args.min_score): p for p in pdfs
                }
                for future in as_completed(futures):
                    runs.append(future.result())

        wall_clock = time.perf_counter() - wall_start
        runs.sort(key=lambda r: r.file)
        summary = summarise(runs)
        all_summaries[mode] = summary
        all_runs[mode] = runs
        print_mode_report(mode, runs, summary, wall_clock)

    # Side-by-side summary
    print()
    print("=" * 78)
    print("SIDE-BY-SIDE COMPARISON")
    print("=" * 78)
    header = f"{'metric':<24}"
    for mode in modes:
        header += f" {mode:>20}"
    print(header)
    print("-" * 78)
    rows = [
        ("papers", lambda s: s["papers"]),
        ("above_good_score", lambda s: f"{s['above_good_score']}/{s['successful']}"),
        ("score_mean", lambda s: f"{s['score']['mean']:.3f}"),
        ("score_median", lambda s: f"{s['score']['median']:.3f}"),
        ("score_min", lambda s: f"{s['score']['min']:.3f}"),
        ("timing_mean_s", lambda s: f"{s['timing_seconds']['mean']:.2f}"),
        ("timing_median_s", lambda s: f"{s['timing_seconds']['median']:.2f}"),
        ("timing_p90_s", lambda s: f"{s['timing_seconds']['p90']:.2f}"),
        ("timing_max_s", lambda s: f"{s['timing_seconds']['max']:.2f}"),
    ]
    for label, fn in rows:
        row = f"{label:<24}"
        for mode in modes:
            row += f" {fn(all_summaries[mode]):>20}"
        print(row)
    print()
    print("Engine winners:")
    all_engines: set[str] = set()
    for s in all_summaries.values():
        all_engines.update(s["engine_winners"])
    if all_engines:
        header = f"{'engine':<14}"
        for mode in modes:
            header += f" {mode:>20}"
        print(header)
        print("-" * 78)
        for engine in sorted(all_engines):
            row = f"{engine:<14}"
            for mode in modes:
                count = all_summaries[mode]["engine_winners"].get(engine, 0)
                row += f" {count:>20}"
            print(row)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "settings": {
                "limit": args.limit,
                "workers": args.workers,
                "min_score": args.min_score,
            },
            "summaries": all_summaries,
            "papers": {mode: [asdict(r) for r in runs] for mode, runs in all_runs.items()},
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()