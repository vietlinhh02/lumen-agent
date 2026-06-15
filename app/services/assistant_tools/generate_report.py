"""Tool: generate_report — generate citation-safe ReviewReport and update ChatDocument.

This tool calls the real production report_generation service, which writes
a ReviewReport to the DB. This makes the report visible on the Reports page.

It also updates the ChatDocument so the assistant chat preview stays in sync.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import ChatDocument, Project
from app.services.assistant_tools.ids import coerce_uuid
from app.services.report_generation import generate_report as production_generate_report

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    project_id = coerce_uuid(args["project_id"])
    include_gaps = args.get("include_gaps", True)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "report",
                "status": "running",
                "percent": 0,
                "label": "Generating report",
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
                    "step": "report",
                    "status": "failed",
                    "percent": 0,
                    "label": "Project not found",
                }
            )
        return {"error": "Project not found", "status": "failed"}

    if runner:
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": "Generating citation-safe literature review...",
            }
        )

    # ── 1. Write to ReviewReport (production persistence for Reports page) ─────
    try:
        prod_result = await production_generate_report(
            db=db,
            project_id=project_id,
            user_id=user.id,
            topic=project.topic,
            research_question=project.research_question,
            title=None,
            include_gap_section=include_gaps,
            selected_gap_ids=None,
        )
    except Exception as exc:
        logger.exception("Production report generation failed for project %s", project_id)
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "report",
                    "status": "failed",
                    "percent": 0,
                    "label": str(exc),
                }
            )
        return {"error": str(exc)[:200], "status": "failed"}

    if "error" in prod_result and prod_result.get("status") == "failed":
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "report",
                    "status": "failed",
                    "percent": 0,
                    "label": prod_result.get("error", "Report generation failed"),
                }
            )
        return {"status": "failed", "error": prod_result.get("error", "unknown error")}

    report_id = prod_result.get("id")
    validation_status = prod_result.get("validation_status", "unknown")
    citation_audit = prod_result.get("citation_audit", {})

    if runner:
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (
                    f"Report persisted: {citation_audit.get('valid_citations', 0)} "
                    f"valid citations ({validation_status})"
                ),
            }
        )

    # ── 2. Also update ChatDocument for the assistant chat preview ───────────
    # Find or create chat_documents row
    doc = (
        (
            await db.execute(
                select(ChatDocument)
                .where(ChatDocument.project_id == project_id, ChatDocument.user_id == user.id)
                .order_by(ChatDocument.created_at.desc())
            )
        )
        .scalars()
        .first()
    )

    if doc is None:
        doc = ChatDocument(
            project_id=project_id,
            user_id=user.id,
            title=project.topic or "Literature Review",
            content_md=prod_result.get("content_markdown", ""),
            version=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
    else:
        # Use the same markdown from the production report
        doc.content_md = prod_result.get("content_markdown", "")
        doc.version = doc.version + 1
        await db.commit()

    if runner:
        await runner.emit(
            {
                "type": "markdown_updated",
                "content": prod_result.get("content_markdown", ""),
                "version": doc.version,
                "section_changed": None,
            }
        )
        await runner.emit(
            {
                "type": "progress",
                "step": "report",
                "status": "done",
                "percent": 100,
                "label": (
                    f"Report done: {citation_audit.get('valid_citations', 0)} citations, "
                    f"status={validation_status}"
                ),
            }
        )

    return {
        "status": "completed",
        "report_id": report_id,
        "validation_status": validation_status,
        "title": prod_result.get("title"),
        "version": doc.version,
        "citations": citation_audit,
    }
