"""Tool: generate_report — generate Markdown report and write to chat_documents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.db.models import ChatDocument, Project
from app.services.report_chat_doc import generate_markdown_for_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    include_gaps = args.get("include_gaps", True)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "report",
                "status": "running",
                "percent": 0,
                "label": "Writing report",
            }
        )

    # Find or create chat_documents row for this project
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
            title="Literature Review",
            content_md="",
            version=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

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

    result = await generate_markdown_for_project(
        db=db,
        project_id=project_id,
        document_id=doc.id,
        user_id=user.id,
        topic=project.topic,
        research_question=project.research_question,
        include_gaps=include_gaps,
    )

    if "error" in result and result.get("markdown", "") == "":
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "report",
                    "status": "failed",
                    "percent": 0,
                    "label": result["error"],
                }
            )
        return {"status": "failed", "error": result["error"]}

    if runner:
        await runner.emit(
            {
                "type": "markdown_updated",
                "content": result["markdown"],
                "version": result["version"],
                "section_changed": None,
            }
        )
        await runner.emit(
            {
                "type": "progress",
                "step": "report",
                "status": "done",
                "percent": 100,
                "label": "Report done",
            }
        )

    return {
        "status": "completed",
        "document_id": str(doc.id),
        "title": result["title"],
        "version": result["version"],
        "section_count": result["section_count"],
    }
