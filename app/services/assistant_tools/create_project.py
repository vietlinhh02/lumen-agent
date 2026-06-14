"""Tool: create_project — create a new Project and a chat_documents row."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.db.models import ChatDocument, User
from app.schemas.project import ProjectCreate
from app.services.project import create_project as svc_create_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(
    db,
    user: User,
    args: dict,
    runner: "AssistantRunner | None" = None,
) -> dict:
    title = args["title"]
    topic = args["topic"]
    research_question = args.get("research_question")
    max_papers = args.get("max_papers", 12)

    data = ProjectCreate(title=title, topic=topic, research_question=research_question)
    resp = await svc_create_project(db, user, data)
    project_id = uuid.UUID(resp.id)

    # Create chat_documents row
    doc = ChatDocument(
        project_id=project_id,
        user_id=user.id,
        title=title,
        content_md="",
        version=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "project_id": str(project_id),
        "title": title,
        "topic": topic,
        "max_papers": max_papers,
        "document_id": str(doc.id),
    }
