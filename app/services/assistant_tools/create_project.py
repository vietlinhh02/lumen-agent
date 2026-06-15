"""Tool: create_project — create or update a Project and a chat_documents row.

If the runner already has a scratch project (created up-front by the WS
handler with title="New conversation"), this tool UPDATES that project in
place. Otherwise it creates a brand-new Project + ChatDocument.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.models import ChatDocument, ChatMessage, Project, User
from app.schemas.project import ProjectCreate
from app.services.assistant_tools.ids import coerce_uuid
from app.services.project import create_project as svc_create_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)

_SCRATCH_TITLE = "New conversation"


async def _is_scratch(db, project_id) -> bool:
    """Return True if *project_id* is still a scratch project (placeholder
    title set by the WS handler)."""
    row = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    return row is not None and row.title == _SCRATCH_TITLE


async def handle(
    db,
    user: User,
    args: dict,
    runner: AssistantRunner | None = None,
) -> dict:
    title = args["title"]
    topic = args["topic"]
    research_question = args.get("research_question")
    max_papers = args.get("max_papers", 12)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "create_project",
                "status": "running",
                "percent": 0,
                "label": f"Creating project: {title}",
            }
        )
        await runner.emit(
            {"type": "log", "level": "info", "message": f"📁 Creating project: {title}"}
        )

    # Decide: UPDATE existing scratch project, or CREATE a new one?
    update_existing = (
        runner is not None
        and runner.project_id is not None
        and await _is_scratch(db, runner.project_id)
    )

    if update_existing:
        # Reuse the scratch project + chat document created at WS open
        project_id = runner.project_id
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one()
        project.title = title
        project.topic = topic
        if research_question is not None:
            project.research_question = research_question
        await db.commit()
        await db.refresh(project)

        doc = (
            await db.execute(
                select(ChatDocument).where(ChatDocument.project_id == project_id)
            )
        ).scalar_one()
        doc.title = title
        await db.commit()
        await db.refresh(doc)

        resp = await _to_response(project, paper_count=0)
    else:
        # No scratch → create a brand-new project (legacy behavior, or the
        # agent is creating a second project within the same WS session).
        data = ProjectCreate(
            title=title, topic=topic, research_question=research_question
        )
        resp = await svc_create_project(db, user, data)
        project_id = coerce_uuid(resp.id)

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

    if runner:
        await runner.emit(
            {"type": "log", "level": "info", "message": f"✓ Project created: {title}"}
        )

    if runner is not None:
        runner.project_id = project_id
        runner.document_id = doc.id
        # Backfill any history that was persisted with a stale/None
        # document_id (shouldn't happen now that the WS handler creates a
        # scratch project up-front, but keep this as a safety net).
        for item in runner.history:
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = item.get("content", "")
            if not content:
                continue
            # Skip if a row with the same role+content already exists
            existing = await db.execute(
                select(ChatMessage).where(
                    ChatMessage.document_id == doc.id,
                    ChatMessage.role == role,
                    ChatMessage.content == content,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            db.add(
                ChatMessage(
                    document_id=doc.id,
                    project_id=project_id,
                    role=role,
                    content=content,
                )
            )
        await db.commit()
        await runner.emit(
            {
                "type": "project_created",
                "project_id": str(project_id),
                "document_id": str(doc.id),
            }
        )
        await runner.emit(
            {
                "type": "progress",
                "step": "create_project",
                "status": "done",
                "percent": 100,
                "label": f"Project ready: {title}",
            }
        )

    return {
        "project_id": str(project_id),
        "title": title,
        "topic": topic,
        "max_papers": max_papers,
        "document_id": str(doc.id),
    }


async def _to_response(project: Project, paper_count: int):
    """Lightweight project→response converter (avoid circular import)."""
    from app.schemas.project import ProjectResponse

    return ProjectResponse(
        id=project.id,
        owner_id=project.owner_id,
        title=project.title,
        topic=project.topic,
        research_question=project.research_question,
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        paper_count=paper_count,
    )
