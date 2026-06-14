"""Tool: edit_report_section — rewrite one section of the current report."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.db.models import ChatDocument
from app.services.report_chat_doc import edit_section

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    section_index = int(args["section_index"])
    instruction = args["instruction"]

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
        return {"error": "No chat document for this project", "status": "failed"}

    result = await edit_section(
        db=db,
        document_id=doc.id,
        project_id=project_id,
        section_index=section_index,
        instruction=instruction,
        current_markdown=doc.content_md,
    )

    if "error" in result:
        return {"error": result["error"], "status": "failed"}

    if runner:
        await runner.emit(
            {
                "type": "markdown_updated",
                "content": result["markdown"],
                "version": result["version"],
                "section_changed": section_index,
            }
        )

    return {
        "status": "completed",
        "version": result["version"],
        "section_index": section_index,
        "section_preview": result.get("section_preview", ""),
    }
