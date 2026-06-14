"""Tool: generate_matrix — extract structured rows for saved project papers.

Loads saved papers from DB, calls LLM to extract matrix fields, persists via
literature_matrix.upsert_rows. Emits progress events through the runner.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ai.provider import get_provider
from app.db.models import LiteratureMatrixRow, Paper, ProjectPaper
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence
from app.services.literature_matrix import get_existing_paper_ids, upsert_rows

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)

_MAX_CHUNKS_PER_PAPER = 4
_MAX_PAPERS = 20
_MAX_CHUNK_CHARS = 6000


def _build_chunk_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "No full-text sections available."
    parts = []
    total = 0
    for c in chunks:
        label = c.section_label or c.content_type or "section"
        block = f"---{label}---\n{c.chunk_text}"
        if total + len(block) > _MAX_CHUNK_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "No full-text sections available."


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "matrix",
                "status": "running",
                "percent": 0,
                "label": "Generating matrix",
            }
        )

    # Load saved project_papers with paper metadata
    stmt = (
        select(ProjectPaper)
        .options(selectinload(ProjectPaper.paper))
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
        )
        .limit(_MAX_PAPERS)
    )
    project_papers = (await db.execute(stmt)).scalars().all()

    if not project_papers:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "matrix",
                    "status": "failed",
                    "percent": 0,
                    "label": "No saved papers",
                }
            )
        return {"rows_created": 0, "status": "failed", "error": "no_saved_papers"}

    # Skip papers that already have matrix rows
    existing_ids = await get_existing_paper_ids(db, project_id)
    papers_to_process = [pp for pp in project_papers if pp.id not in existing_ids]
    if not papers_to_process:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "matrix",
                    "status": "done",
                    "percent": 100,
                    "label": "Matrix up to date",
                }
            )
        return {"rows_created": 0, "status": "completed", "note": "all_up_to_date"}

    # RAG retrieval for the whole project
    topic = args.get("topic") or ""
    try:
        all_chunks = await retrieve_project_evidence(db, project_id, topic, limit=40)
    except Exception as exc:
        logger.warning("RAG retrieval failed: %s", exc)
        all_chunks = []

    chunks_by_paper: dict = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # Extract matrix rows
    provider = get_provider()
    rows: list[dict] = []
    for pp in papers_to_process:
        paper = pp.paper
        paper_chunks = chunks_by_paper.get(pp.id, [])[:_MAX_CHUNKS_PER_PAPER]
        chunk_context = _build_chunk_context(paper_chunks)

        try:
            user_msg = (
                f"Project topic: {topic or 'N/A'}\n\n"
                f"Paper title: {paper.title}\n"
                f"Authors: {', '.join(a.get('name', str(a)) if isinstance(a, dict) else str(a) for a in (paper.authors or []))}\n"
                f"Year: {paper.year or 'unknown'}\n"
                f"Abstract: {paper.abstract or 'No abstract available'}\n"
                f"Venue: {paper.venue or 'not specified'}\n\n"
                f"Relevant sections from the full text:\n{chunk_context}\n\n"
                "Extract the literature matrix row for this paper. Return JSON with "
                "research_problem, method, dataset_or_context, key_result, limitation, "
                "contribution, relevance, confidence."
            )
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                schema={
                    "type": "object",
                    "properties": {
                        "research_problem": {"type": "string"},
                        "method": {"type": "string"},
                        "dataset_or_context": {"type": "string"},
                        "key_result": {"type": "string"},
                        "limitation": {"type": "string"},
                        "contribution": {"type": "string"},
                        "relevance": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                },
                tool_name="matrix_row",
                max_tokens=1500,
            )
            rows.append(
                {
                    "project_paper_id": pp.id,
                    "research_problem": result.get("research_problem", "not specified"),
                    "method": result.get("method", "not specified"),
                    "dataset_or_context": result.get("dataset_or_context", "not specified"),
                    "key_result": result.get("key_result", "not specified"),
                    "limitation": result.get("limitation", "not specified"),
                    "contribution": result.get("contribution", "not specified"),
                    "relevance": result.get("relevance", "not specified"),
                    "extraction_confidence": result.get("confidence", "medium"),
                }
            )
        except Exception as exc:
            logger.warning("Matrix extraction failed for paper '%s': %s", paper.title[:60], exc)

    if rows:
        try:
            saved_count = await upsert_rows(db, project_id, rows)
        except Exception as exc:
            logger.error("Failed to persist matrix rows: %s", exc)
            if runner:
                await runner.emit(
                    {
                        "type": "progress",
                        "step": "matrix",
                        "status": "failed",
                        "percent": 0,
                        "label": str(exc),
                    }
                )
            return {"rows_created": 0, "status": "failed", "error": str(exc)[:200]}

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "matrix",
                "status": "done",
                "percent": 100,
                "label": f"Matrix done: {len(rows)} rows",
            }
        )

    return {
        "rows_created": len(rows),
        "status": "completed",
    }
