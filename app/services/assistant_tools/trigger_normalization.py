"""Tool: trigger_normalization — force-start PDF normalization for a project.

Triggers the batch normalization pipeline (raw text → LLM clean → chunk → embed)
for all papers with raw_extracted status. This is critical before matrix generation
because the matrix tool needs embedded chunks for RAG-based extraction.

Emits real progress as each paper is processed. Uses its own DB session.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.db.models import PaperChunk, Project, ProjectPaper
from app.db.session import async_session_factory
from app.services.assistant_tools.ids import coerce_uuid
from app.services.pdf_normalizer import count_raw_papers

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)

_EMIT_INTERVAL_SECONDS = 5
_MAX_WAIT_SECONDS = 180  # 3 minutes max wait


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    project_id = coerce_uuid(args["project_id"])
    wait_for_chunks = args.get("wait_for_chunks", True)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "normalization",
                "status": "running",
                "percent": 0,
                "label": "Triggering PDF normalization",
            }
        )

    # Verify project exists
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "normalization",
                    "status": "failed",
                    "percent": 0,
                    "label": "Project not found",
                }
            )
        return {"status": "failed", "error": "project_not_found"}

    raw_count = await count_raw_papers(db, project_id)

    if runner:
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (
                    f"Triggering normalization for {raw_count} papers. "
                    "PDFs will be extracted, chunked, and embedded."
                ),
            }
        )

    if raw_count == 0:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "normalization",
                    "status": "done",
                    "percent": 100,
                    "label": "No raw papers to normalize",
                }
            )
        return {"status": "completed", "papers_queued": 0, "message": "no_raw_papers"}

    # Launch normalization in background with its own session
    # Progress is emitted by the background task
    asyncio.ensure_future(_run_normalization_with_progress(project_id, raw_count, runner))

    if not wait_for_chunks:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "normalization",
                    "status": "running",
                    "percent": 10,
                    "label": f"Normalization started for {raw_count} papers",
                }
            )
        return {"status": "started", "papers_queued": raw_count}

    # Poll for chunk count with real-time progress updates
    import time

    start_time = time.monotonic()
    last_known_chunks = 0

    for attempt in range(1, 30):  # up to 30 * 5 = 150 seconds
        if runner and runner.stopped.is_set():
            return {"status": "stopped", "papers_queued": raw_count}

        elapsed = int(time.monotonic() - start_time)
        if elapsed >= _MAX_WAIT_SECONDS:
            if runner:
                await runner.emit(
                    {
                        "type": "progress",
                        "step": "normalization",
                        "status": "done",
                        "percent": 95,
                        "label": "Normalization in progress (timeout reached)",
                    }
                )
            return {
                "status": "in_progress",
                "papers_queued": raw_count,
                "message": f"Timeout after {elapsed}s. Normalization still running in background.",
            }

        # Count chunks for papers in this project
        chunk_stmt = (
            select(func.count(PaperChunk.id))
            .join(ProjectPaper, ProjectPaper.id == PaperChunk.project_paper_id)
            .where(
                ProjectPaper.project_id == project_id,
                PaperChunk.chunk_type == "full_text",
            )
        )
        total_chunks = (await db.execute(chunk_stmt)).scalar() or 0

        # Progress percent: estimate based on chunks seen vs expected
        # ~10 chunks per paper on average is a reasonable baseline
        expected_approx = raw_count * 10
        if expected_approx > 0:
            percent = min(int((total_chunks / expected_approx) * 95), 95)
        else:
            percent = min(int(attempt / 30 * 95), 95)

        if runner:
            label = (
                f"Normalizing... {total_chunks} chunks ({elapsed}s elapsed)"
                + (" — done!" if total_chunks > last_known_chunks * 1.5 else "")
            )
            await runner.emit(
                {
                    "type": "progress",
                    "step": "normalization",
                    "status": "running",
                    "percent": percent,
                    "label": label,
                }
            )

        # If we see chunks growing, normalization is working
        if total_chunks > 0 and total_chunks >= last_known_chunks:
            last_known_chunks = total_chunks

        await asyncio.sleep(_EMIT_INTERVAL_SECONDS)

    # Shouldn't reach here normally
    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "normalization",
                "status": "done",
                "percent": 95,
                "label": "Normalization in progress",
            }
        )
    return {"status": "in_progress", "papers_queued": raw_count}


async def _run_normalization_with_progress(
    project_id,
    raw_count: int,
    runner,
) -> None:
    """Run normalization in background, emitting progress events."""
    from app.services.pdf_normalizer import normalize_project_papers

    try:
        async with async_session_factory() as bg_db:
            result = await normalize_project_papers(bg_db, project_id)
            logger.info("Background normalization done for %s: %s", project_id, result)
            if runner:
                processed = result.get("processed", 0)
                failed = result.get("failed", 0)
                label = (
                    f"Normalization complete: {processed} papers processed"
                    + (f", {failed} failed" if failed else "")
                )
                await runner.emit(
                    {
                        "type": "log",
                        "level": "info" if failed == 0 else "warn",
                        "message": label,
                    }
                )
    except Exception as exc:
        logger.exception("Background normalization crashed for %s", project_id)
        if runner:
            await runner.emit(
                {
                    "type": "log",
                    "level": "error",
                    "message": f"Normalization failed: {exc}",
                }
            )
