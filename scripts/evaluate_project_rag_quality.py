"""Evaluate chunk, embedding, and RAG quality for a project.

This is a live-project diagnostic script. It reads the database, reports
chunk/embedding coverage, detects math-like chunks that are not classified as
equations, then optionally runs retrieval queries through the real hybrid RAG
path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from uuid import UUID

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import Paper, PaperChunk, Project, ProjectPaper  # noqa: E402
from app.db.session import async_session_factory  # noqa: E402
from app.services.hybrid_retrieval import retrieve_project_evidence  # noqa: E402

_MATH_LIKE_RE = re.compile(
    r"(\\[A-Za-z]+|[A-Za-z0-9_]\s*=\s*[^\n]{1,120}|[∑∏∫∂∇≈≠≤≥±×÷∞πµνρσχψωΩΛ]|"
    r"\barg\s*min\b|\blog\s*\(|\([0-9]{1,3}\)\s*$)"
)

_DEFAULT_QUERIES = [
    "McVittie metric field equations k = 0",
    "wormhole holography Einstein equations",
    "time travel closed timelike curves",
]


@dataclass(frozen=True)
class TopChunk:
    """Small, JSON-safe view of a retrieved chunk."""

    title: str
    content_type: str | None
    section_label: str | None
    score: float
    keyword_score: float
    vector_score: float
    text_preview: str


async def main() -> None:
    args = parse_args()
    report = await evaluate_project(
        args.project_id,
        queries=args.query or _DEFAULT_QUERIES,
        limit=args.limit,
        use_reranker=not args.no_reranker,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print_report(report)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_id", type=UUID)
    parser.add_argument(
        "--query",
        action="append",
        help="Retrieval query to evaluate. Can be passed multiple times.",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--no-reranker",
        action="store_true",
        help="Disable external reranker calls; still uses real query embeddings.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser.parse_args()


async def evaluate_project(
    project_id: UUID,
    *,
    queries: list[str],
    limit: int,
    use_reranker: bool,
) -> dict:
    """Build a quality report for one project."""
    async with async_session_factory() as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        chunk_rows = (
            await db.execute(
                select(Paper.title, PaperChunk)
                .join(ProjectPaper, PaperChunk.project_paper_id == ProjectPaper.id)
                .join(Paper, ProjectPaper.paper_id == Paper.id)
                .where(ProjectPaper.project_id == project_id)
                .where(PaperChunk.chunk_type == "full_text")
                .order_by(Paper.title, PaperChunk.created_at)
            )
        ).all()
        chunk_items = [(title, chunk) for title, chunk in chunk_rows]
        paper_count = await db.scalar(
            select(func.count(ProjectPaper.id)).where(ProjectPaper.project_id == project_id)
        )
        retrieval = await evaluate_retrieval(
            db,
            project_id,
            queries=queries,
            limit=limit,
            use_reranker=use_reranker,
        )

    return {
        "project": {"id": str(project.id), "title": project.title, "paper_count": paper_count},
        "chunks": chunk_quality(chunk_items),
        "retrieval": retrieval,
    }


def chunk_quality(chunk_rows: list[tuple[str, PaperChunk]]) -> dict:
    """Summarize chunk and embedding coverage."""
    chunks = [chunk for _, chunk in chunk_rows]
    math_like = [
        (title, chunk)
        for title, chunk in chunk_rows
        if _MATH_LIKE_RE.search(chunk.chunk_text) and chunk.content_type != "equation"
    ]
    dimensions = sorted(
        {chunk.embedding_dimension for chunk in chunks if chunk.embedding_dimension}
    )
    return {
        "total": len(chunks),
        "embedded": sum(1 for chunk in chunks if chunk.embedding is not None),
        "embedding_dimensions": dimensions,
        "pipeline_versions": count_by(chunks, "pipeline_version"),
        "content_types": count_by(chunks, "content_type"),
        "math_like_not_equation": len(math_like),
        "math_like_not_equation_samples": [
            {
                "title": title,
                "content_type": chunk.content_type,
                "section_label": chunk.section_label,
                "preview": preview(chunk.chunk_text),
            }
            for title, chunk in math_like[:5]
        ],
    }


async def evaluate_retrieval(
    db,
    project_id: UUID,
    *,
    queries: list[str],
    limit: int,
    use_reranker: bool,
) -> list[dict]:
    """Run live hybrid retrieval for each query and capture quality signals."""
    reports: list[dict] = []
    for query in queries:
        try:
            chunks = await retrieve_project_evidence(
                db,
                project_id,
                query,
                limit=limit,
                use_reranker=use_reranker,
            )
        except Exception as exc:
            reports.append({"query": query, "error": str(exc)})
            continue
        reports.append(
            {
                "query": query,
                "total": len(chunks),
                "unique_papers": len({chunk.project_paper_id for chunk in chunks}),
                "avg_score": mean([chunk.score for chunk in chunks]) if chunks else 0.0,
                "top_chunks": [asdict(to_top_chunk(chunk)) for chunk in chunks],
            }
        )
    return reports


def to_top_chunk(chunk) -> TopChunk:
    """Convert a RetrievedChunk to a compact report item."""
    return TopChunk(
        title=chunk.title,
        content_type=chunk.content_type,
        section_label=chunk.section_label,
        score=round(chunk.score, 4),
        keyword_score=round(chunk.keyword_score, 4),
        vector_score=round(chunk.vector_score, 4),
        text_preview=preview(chunk.chunk_text),
    )


def count_by(chunks: list[PaperChunk], attr: str) -> dict[str, int]:
    """Count chunk rows by a nullable attribute."""
    counts: dict[str, int] = {}
    for chunk in chunks:
        key = str(getattr(chunk, attr) or "none")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def preview(text: str, limit: int = 220) -> str:
    """Return a single-line text preview."""
    return " ".join(text.split())[:limit]


def print_report(report: dict) -> None:
    """Print a compact human-readable report."""
    project = report["project"]
    chunks = report["chunks"]
    print(f"Project: {project['title']} ({project['id']})")
    print(f"Papers: {project['paper_count']}")
    print("\nChunks")
    print(f"  total: {chunks['total']}")
    print(f"  embedded: {chunks['embedded']}")
    print(f"  dimensions: {chunks['embedding_dimensions']}")
    print(f"  pipeline_versions: {chunks['pipeline_versions']}")
    print(f"  content_types: {chunks['content_types']}")
    print(f"  math_like_not_equation: {chunks['math_like_not_equation']}")
    for sample in chunks["math_like_not_equation_samples"]:
        print(f"    - [{sample['content_type']}] {sample['title']}: {sample['preview']}")
    print("\nRetrieval")
    for item in report["retrieval"]:
        if "error" in item:
            print(f"  {item['query']}: ERROR {item['error']}")
            continue
        print(
            f"  {item['query']}: total={item['total']} "
            f"unique_papers={item['unique_papers']} avg_score={item['avg_score']:.4f}"
        )
        for chunk in item["top_chunks"][:3]:
            print(
                f"    - {chunk['score']:.4f} {chunk['content_type']} "
                f"{chunk['title']}: {chunk['text_preview']}"
            )


if __name__ == "__main__":
    asyncio.run(main())
