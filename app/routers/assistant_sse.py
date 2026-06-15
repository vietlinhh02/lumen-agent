"""SSE endpoints for the AI assistant chat page.

Replaces the legacy WebSocket transport with Server-Sent Events:

  POST /api/assistant/message          — start streaming a turn (SSE)
  POST /api/assistant/stop             — cancel the currently running turn
  GET  /api/assistant/health           — simple liveness check

Why SSE instead of WebSocket:
  • The assistant follows a request-then-stream pattern (one user message
    → many server events → done). Bidirectional communication is unused.
  • SSE works through every HTTP proxy / CDN / corporate firewall.
  • Auth via standard `Authorization: Bearer` header instead of query string.
  • Browser EventSource API auto-reconnects on drop; no manual backoff.
  • Each turn is an independent HTTP request, so horizontal scaling needs
    no sticky sessions and no shared connection state.
  • "Stop" is a separate idempotent POST instead of a WS frame.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.core.security import get_current_user
from app.db.models import ChatDocument, Project, User
from app.db.session import async_session_factory, get_db
from app.services.assistant_runner import (
    AssistantRunner,
    get_runner,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant-sse"])


# ── Schemas ──────────────────────────────────────────────────────────────


class MessageRequest(BaseModel):
    project_id: str
    content: str


class StopRequest(BaseModel):
    project_id: str


# ── Helpers ──────────────────────────────────────────────────────────────


async def _resolve_or_create_scratch(
    db, user: User, project_id_str: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Return (project_id, document_id) — create a scratch project/doc if
    the caller passed the special sentinel 'new'."""
    if project_id_str == "new":
        scratch = Project(
            owner_id=user.id,
            title="New conversation",
            topic="",
            research_question=None,
            status="active",
        )
        db.add(scratch)
        await db.commit()
        await db.refresh(scratch)
        doc = ChatDocument(
            project_id=scratch.id,
            user_id=user.id,
            title="New conversation",
            content_md="",
            version=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return scratch.id, doc.id

    try:
        project_id = uuid.UUID(project_id_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project_id") from exc

    # Verify ownership
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id, Project.owner_id == user.id
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    doc = (
        await db.execute(
            select(ChatDocument)
            .where(
                ChatDocument.project_id == project_id,
                ChatDocument.user_id == user.id,
            )
            .order_by(ChatDocument.created_at.desc())
        )
    ).scalars().first()
    if doc is None:
        doc = ChatDocument(
            project_id=project_id,
            user_id=user.id,
            title=project.title,
            content_md="",
            version=0,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
    return project_id, doc.id


def _sse_format(event: dict) -> bytes:
    """Serialize an event dict into SSE wire format (text/event-stream)."""
    event_type = event.get("type", "message")
    payload = json.dumps(event, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n".encode()


# ── Routes ───────────────────────────────────────────────────────────────


@router.post("/message")
async def post_message(
    body: MessageRequest,
    db=Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Accept a user message and stream the agent's events back as SSE.

    The client opens this endpoint with `fetch()` + ReadableStream and
    consumes `event:`/`data:` frames as they arrive.
    """
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    project_id, document_id = await _resolve_or_create_scratch(db, user, body.project_id)

    # Queue bridges the runner's emit() to the SSE response generator.
    # Sized large enough to absorb bursty tool-call events; consumers
    # will keep up in practice.
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    async def event_stream() -> AsyncIterator[bytes]:
        # Send a 'connected' frame first so the client can update its URL
        yield _sse_format(
            {
                "type": "connected",
                "session_id": str(uuid.uuid4()),
                "project_id": str(project_id),
                "document_id": str(document_id),
                "resumed": body.project_id != "new",
            }
        )

        # Open a dedicated DB session for the runner so the request-scoped
        # session from get_db() can close cleanly when this generator returns.
        async with async_session_factory() as runner_db:
            runner = AssistantRunner(
                db=runner_db,
                user=user,
                project_id=project_id,
                document_id=document_id,
                ws_send=None,
                event_queue=queue,
            )
            task = runner.start(content)

            try:
                while True:
                    # If the runner task crashed, drain remaining events then exit
                    if task.done() and queue.empty():
                        # Make sure the task's exception is surfaced
                        if task.exception() is not None:
                            err = task.exception()
                            yield _sse_format(
                                {
                                    "type": "error",
                                    "message": str(err)[:300],
                                    "code": "runner_failed",
                                }
                            )
                        break

                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except TimeoutError:
                        # Heartbeat to keep proxies from closing the connection
                        yield b": heartbeat\n\n"
                        continue

                    yield _sse_format(event)

                    if event.get("type") in {"done", "stopped", "error"}:
                        # Drain any remaining buffered events (best-effort)
                        while not queue.empty():
                            try:
                                yield _sse_format(queue.get_nowait())
                            except asyncio.QueueEmpty:
                                break
                        break
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disable Nginx response buffering (critical for SSE to actually stream)
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/stop")
async def post_stop(
    body: StopRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """Stop the currently running agent turn for *project_id* (idempotent)."""
    if body.project_id == "new":
        return {"stopped": False, "reason": "no persisted session"}

    try:
        project_id = uuid.UUID(body.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project_id") from exc

    # Verify ownership before signaling
    async with async_session_factory() as db:
        project = (
            await db.execute(
                select(Project).where(
                    Project.id == project_id, Project.owner_id == user.id
                )
            )
        ).scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    runner = get_runner(project_id)
    if runner is None:
        # No active run — treat as a no-op (idempotent)
        return {"stopped": False, "reason": "no active run"}

    runner.stopped.set()
    return {"stopped": True}


@router.get("/health")
async def health() -> dict:
    """SSE endpoint liveness probe (no auth required)."""
    return {"status": "ok", "transport": "sse"}
