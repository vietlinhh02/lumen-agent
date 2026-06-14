"""WebSocket endpoint for the AI assistant chat page."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.db.models import ChatDocument, Project, User
from app.db.session import async_session_factory
from app.services.assistant_runner import AssistantRunner
from app.services.auth import decode_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_user_from_token(token: str) -> uuid.UUID | None:
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        return uuid.UUID(sub) if sub else None
    except Exception:
        return None


@router.websocket("/ws")
async def assistant_ws(websocket: WebSocket, project_id: str, token: str):
    """WebSocket entry: project_id query param + JWT token.

    Lifecycle:
    1. Validate token → user_id
    2. If project_id == "new", wait for first message to create a project
    3. Find or create chat_documents row for this project
    4. Loop: receive user_message → run agent turn → send events
    """
    await websocket.accept()
    user_id = await _resolve_user_from_token(token)
    if not user_id:
        await websocket.send_json(
            {"type": "error", "message": "Invalid or expired token", "code": "unauthorized"}
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user or not user.is_active:
            await websocket.send_json(
                {"type": "error", "message": "User not found or inactive", "code": "unauthorized"}
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        actual_project_id: uuid.UUID | None = None
        document_id: uuid.UUID | None = None
        if project_id != "new":
            try:
                actual_project_id = uuid.UUID(project_id)
            except ValueError:
                await websocket.send_json(
                    {"type": "error", "message": "Invalid project_id", "code": "bad_request"}
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            project = (
                await db.execute(
                    select(Project).where(
                        Project.id == actual_project_id, Project.owner_id == user.id
                    )
                )
            ).scalar_one_or_none()
            if not project:
                await websocket.send_json(
                    {"type": "error", "message": "Project not found", "code": "not_found"}
                )
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

            doc = (
                (
                    await db.execute(
                        select(ChatDocument)
                        .where(
                            ChatDocument.project_id == actual_project_id,
                            ChatDocument.user_id == user.id,
                        )
                        .order_by(ChatDocument.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            if doc:
                document_id = doc.id
                await websocket.send_json(
                    {
                        "type": "markdown_snapshot",
                        "content": doc.content_md,
                        "version": doc.version,
                        "title": doc.title,
                    }
                )
            else:
                doc = ChatDocument(
                    project_id=actual_project_id,
                    user_id=user.id,
                    title=project.title,
                    content_md="",
                    version=0,
                )
                db.add(doc)
                await db.commit()
                await db.refresh(doc)
                document_id = doc.id

        await websocket.send_json(
            {
                "type": "connected",
                "session_id": str(uuid.uuid4()),
                "project_id": str(actual_project_id) if actual_project_id else None,
                "document_id": str(document_id) if document_id else None,
                "resumed": project_id != "new",
            }
        )

        async def ws_send(event: dict) -> None:
            try:
                await websocket.send_json(event)
            except Exception as exc:
                logger.debug("WS send failed: %s", exc)

        runner: AssistantRunner | None = None
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws_send(
                        {"type": "error", "message": "Invalid JSON", "code": "bad_request"}
                    )
                    continue

                mtype = msg.get("type")
                if mtype == "ping":
                    await ws_send({"type": "pong"})
                    continue
                if mtype == "stop":
                    if runner is not None:
                        runner.stopped.set()
                    continue
                if mtype == "resume":
                    continue
                if mtype != "user_message":
                    await ws_send(
                        {
                            "type": "error",
                            "message": f"Unknown type: {mtype}",
                            "code": "bad_request",
                        }
                    )
                    continue

                content = (msg.get("content") or "").strip()
                if not content:
                    continue

                runner = AssistantRunner(
                    db=db,
                    user=user,
                    project_id=actual_project_id,
                    document_id=document_id,
                    ws_send=ws_send,
                )
                await runner.run_turn(content)

                if actual_project_id is None:
                    doc = (
                        (
                            await db.execute(
                                select(ChatDocument)
                                .where(ChatDocument.user_id == user.id)
                                .order_by(ChatDocument.created_at.desc())
                            )
                        )
                        .scalars()
                        .first()
                    )
                    if doc:
                        actual_project_id = doc.project_id
                        document_id = doc.id
                        await ws_send(
                            {
                                "type": "project_created",
                                "project_id": str(actual_project_id),
                                "document_id": str(document_id),
                            }
                        )
        except WebSocketDisconnect:
            logger.info("WS disconnected for user %s", user_id)
        except Exception as exc:
            logger.exception("WS handler error")
            try:
                await ws_send({"type": "error", "message": str(exc)[:200], "code": "server_error"})
            except Exception:
                pass
