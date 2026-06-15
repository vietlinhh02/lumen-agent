"""Tool: detect_conflicts — detect conflicting findings from matrix rows + full-text."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import Project
from app.services.assistant_tools.ids import coerce_uuid
from app.services.conflict_detection import detect_and_persist_conflicts

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    project_id = coerce_uuid(args["project_id"])

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "conflicts",
                "status": "running",
                "percent": 0,
                "label": "Detecting conflicts",
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
                    "step": "conflicts",
                    "status": "failed",
                    "percent": 0,
                    "label": "Project not found",
                }
            )
        return {"conflicts_found": 0, "status": "failed", "error": "project_not_found"}

    if runner:
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": "Analyzing matrix rows for conflicting findings...",
            }
        )

    topic = args.get("topic") or project.topic or ""

    try:
        conflicts = await detect_and_persist_conflicts(db, project_id, topic)
    except Exception as exc:
        logger.exception("Conflict detection failed for project %s", project_id)
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "conflicts",
                    "status": "failed",
                    "percent": 0,
                    "label": str(exc),
                }
            )
        return {"conflicts_found": 0, "status": "failed", "error": str(exc)[:200]}

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "conflicts",
                "status": "done",
                "percent": 100,
                "label": f"Conflicts done: {len(conflicts)} found",
            }
        )

    return {
        "conflicts_found": len(conflicts),
        "status": "completed",
        "conflicts": conflicts,
    }
