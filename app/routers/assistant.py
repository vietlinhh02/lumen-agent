"""REST endpoints for AI assistant chat document history."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import ChatDocument, ChatMessage, Project, User
from app.db.session import get_db
from app.schemas.assistant import (
    ChatDocumentCreateRequest,
    ChatDocumentDetailResponse,
    ChatDocumentListResponse,
    ChatDocumentResponse,
    ChatMessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _doc_to_response(doc: ChatDocument) -> ChatDocumentResponse:
    return ChatDocumentResponse(
        id=str(doc.id),
        project_id=str(doc.project_id),
        title=doc.title,
        content_md=doc.content_md,
        version=doc.version,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        updated_at=doc.updated_at.isoformat() if doc.updated_at else "",
    )


@router.post("/documents", response_model=ChatDocumentResponse)
async def create_document(
    body: ChatDocumentCreateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDocumentResponse:
    title = (body.title if body else None) or "New assistant session"
    title = title.strip() or "New assistant session"
    project = Project(
        owner_id=user.id,
        title=title,
        topic="",
        research_question=None,
        status="active",
    )
    db.add(project)
    await db.flush()

    doc = ChatDocument(
        project_id=project.id,
        user_id=user.id,
        title=title,
        content_md="",
        version=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _doc_to_response(doc)


@router.get("/documents", response_model=ChatDocumentListResponse)
async def list_documents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDocumentListResponse:
    stmt = (
        select(ChatDocument)
        .where(ChatDocument.user_id == user.id)
        .order_by(ChatDocument.updated_at.desc())
    )
    docs = list((await db.execute(stmt)).scalars().all())
    return ChatDocumentListResponse(
        items=[_doc_to_response(d) for d in docs],
        total=len(docs),
    )


@router.get("/documents/{doc_id}", response_model=ChatDocumentDetailResponse)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatDocumentDetailResponse:
    try:
        did = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid doc_id") from exc

    doc = (
        await db.execute(
            select(ChatDocument).where(ChatDocument.id == did, ChatDocument.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    msgs_stmt = (
        select(ChatMessage)
        .where(ChatMessage.document_id == doc.id)
        .order_by(ChatMessage.created_at.asc())
    )
    msgs = list((await db.execute(msgs_stmt)).scalars().all())

    msg_responses = [
        ChatMessageResponse(
            id=str(m.id),
            document_id=str(m.document_id),
            project_id=str(m.project_id),
            role=m.role,
            content=m.content,
            tool_name=m.tool_name,
            tool_args=m.tool_args or {},
            tool_result=m.tool_result or {},
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in msgs
    ]
    base = _doc_to_response(doc)
    return ChatDocumentDetailResponse(**base.model_dump(), messages=msg_responses)


@router.get("/documents/{doc_id}/export")
async def export_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        did = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid doc_id") from exc

    doc = (
        await db.execute(
            select(ChatDocument).where(ChatDocument.id == did, ChatDocument.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return PlainTextResponse(
        content=doc.content_md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{doc.title[:60]}.md"'},
    )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    try:
        did = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid doc_id") from exc

    doc = (
        await db.execute(
            select(ChatDocument).where(ChatDocument.id == did, ChatDocument.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    return Response(status_code=204)
