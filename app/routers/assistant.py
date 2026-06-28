"""
REST endpoints for the Assistant (Plan-Act Chat).

Provides:
- Session CRUD (create/list/get/delete)
- Chat endpoint with SSE streaming
- Session stop/cancel endpoint
- Per-session structured JSON logging
- Per-user rate limiting (concurrent sessions + message rate)

All endpoints require JWT authentication. Sessions are scoped to the
authenticated user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.assistant.event_mapper import EventMapper
from app.agents.assistant.events import BaseEvent
from app.agents.assistant.graph.adapter import is_graph_enabled
from app.ai.provider import LLMUsage
from app.services.cost_tracker import log_llm_usage
from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.assistant import (
    ChatRequest,
    ErrorResponse,
    SessionCreate,
    SessionDetail,
    SessionEvent,
    SessionListResponse,
    SessionProjectUpdate,
    SessionResponse,
    SessionSummary,
    SessionTitleUpdate,
)
from app.services.assistant.metrics import metrics
from app.services.assistant.rate_limit import rate_limiter
from app.services.assistant.session_service import AssistantSessionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistant"])


# ── SSE Streaming Helper ───────────────────────────────────────────────────────


async def _event_stream(
    event_generator: AsyncGenerator[BaseEvent],
    session_id: UUID,
) -> AsyncGenerator[dict]:
    """
    Convert an event generator to SSE format.

    Yields dicts with 'event' and 'data' keys for sse_starlette.
    """
    try:
        async for event in event_generator:
            sse_data = EventMapper.event_to_sse_event(event)
            yield {
                "event": sse_data["event"],
                "data": json.dumps(sse_data["data"], default=str),
            }
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for session %s", session_id)
        raise
    except Exception as exc:
        logger.exception("Error in event stream for session %s: %s", session_id, exc)
        yield {
            "event": "error",
            "data": json.dumps({"code": "STREAM_ERROR", "message": str(exc)}),
        }


# ── Session CRUD Endpoints ─────────────────────────────────────────────────────


@router.put(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResponse:
    """
    Create a new assistant session.

    Optionally pin the session to a project by providing `project_id`.

    Rate limited: max 10 concurrent sessions per user.
    """
    # Check concurrent session limit
    if not rate_limiter.check_concurrent_sessions(user.id):
        logger.warning(
            "Concurrent session limit exceeded for user %s",
            user.id,
            extra={"user_id": str(user.id), "limit": 10},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many concurrent sessions. Maximum is 10. "
                   f"Current: {rate_limiter.get_active_sessions(user.id)}",
        )

    service = AssistantSessionService(db=db)
    try:
        session = await service.create_session(
            user=user,
            project_id=body.project_id,
            title=body.title,
        )

        # Record metrics
        metrics.record_session_created(session.id, user.id)
        rate_limiter.record_session_started(user.id)

        # Log session creation
        logger.info(
            "Assistant session created",
            extra={
                "session_id": str(session.id),
                "user_id": str(user.id),
                "project_id": str(body.project_id) if body.project_id else None,
            },
        )

        return SessionResponse(
            id=session.id,
            title=session.title,
            project_id=session.project_id,
            status=session.status,
            created_at=session.created_at,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    responses={
        401: {"model": ErrorResponse},
    },
)
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionListResponse:
    """
    List all sessions for the authenticated user.

    Returns lightweight summaries ordered by most recently updated.
    """
    service = AssistantSessionService(db=db)
    sessions = await service.list_sessions(user, limit=limit, offset=offset)

    summaries = [
        SessionSummary(
            id=s.id,
            title=s.title,
            project_id=s.project_id,
            project_title=s.project_title,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            event_count=s.event_count,
        )
        for s in sessions
    ]

    return SessionListResponse(sessions=summaries, total=len(summaries))


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionDetail:
    """
    Get a session by ID with all events and plan.

    Use this endpoint to replay a session's history before attaching
    to a live SSE stream.
    """
    service = AssistantSessionService(db=db)
    session = await service.get_session(user, session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or you don't have access to it.",
        )

    # Build event list
    from app.services.assistant.session_service import sort_session_events
    sorted_events = sort_session_events(session.events)
    events = [
        SessionEvent(
            id=e.id,
            event_type=e.event_type,
            payload=e.payload,
            created_at=e.created_at,
        )
        for e in sorted_events
    ]

    # Get project title
    project_title = None
    if session.project:
        project_title = session.project.title

    return SessionDetail(
        id=session.id,
        title=session.title,
        project_id=session.project_id,
        project_title=project_title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        events=events,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """
    Delete a session and all its events.

    The session must be owned by the authenticated user.
    """
    service = AssistantSessionService(db=db)
    deleted = await service.delete_session(user, session_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or you don't have access to it.",
        )

    # Decrement active sessions counter
    rate_limiter.record_session_ended(user.id)
    metrics.decrement_active_sessions(user.id)

    logger.info(
        "Assistant session deleted",
        extra={"session_id": str(session_id), "user_id": str(user.id)},
    )


@router.patch(
    "/sessions/{session_id}/title",
    response_model=SessionResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def update_session_title(
    session_id: UUID,
    body: SessionTitleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResponse:
    """
    Rename an assistant session.

    Empty/whitespace-only titles are rejected so the list view always has
    something to show.
    """
    new_title = body.title.strip()
    if not new_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title cannot be empty.",
        )
    if len(new_title) > 200:
        new_title = new_title[:200].rstrip()

    service = AssistantSessionService(db=db)
    session = await service.get_session(user, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or you don't have access to it.",
        )

    await service.update_session_title(session, new_title)

    logger.info(
        "Assistant session renamed",
        extra={
            "session_id": str(session_id),
            "user_id": str(user.id),
            "title": new_title,
        },
    )

    return SessionResponse(
        id=session.id,
        title=session.title,
        project_id=session.project_id,
        status=session.status,
        created_at=session.created_at,
    )


@router.patch(
    "/sessions/{session_id}/project",
    response_model=SessionResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
)
async def update_session_project(
    session_id: UUID,
    body: SessionProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionResponse:
    """
    Update the project linked to an assistant session.
    """
    service = AssistantSessionService(db=db)
    session = await service.get_session(user, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or you don't have access to it.",
        )

    # If setting to a new project, verify project exists and user owns it
    if body.project_id:
        from sqlalchemy import select

        from app.db.models import Project
        result = await db.execute(
            select(Project).where(
                Project.id == body.project_id,
                Project.owner_id == user.id,
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project not found or you don't have access to it.",
            )

    await service.update_session_project(session, body.project_id)

    logger.info(
        "Assistant session project updated",
        extra={
            "session_id": str(session_id),
            "user_id": str(user.id),
            "project_id": str(body.project_id) if body.project_id else None,
        },
    )

    return SessionResponse(
        id=session.id,
        title=session.title,
        project_id=session.project_id,
        status=session.status,
        created_at=session.created_at,
    )


# ── Chat & Control Endpoints ───────────────────────────────────────────────────


@router.post(
    "/sessions/{session_id}/chat",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def chat(
    session_id: UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EventSourceResponse:
    """
    Send a chat message to the assistant.

    Returns a Server-Sent Events (SSE) stream. Each event has:
    - `event`: the event type (message, plan, step, tool, done, error, wait)
    - `data`: JSON-encoded event data

    The stream is `text/event-stream` with proper caching headers.

    Rate limited: max 100 messages per hour per user.
    """
    # Check message rate limit
    if not rate_limiter.check_message_rate(user.id):
        logger.warning(
            "Message rate limit exceeded for user %s",
            user.id,
            extra={"user_id": str(user.id), "limit": 100},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Message rate limit exceeded. Maximum is 100 messages per hour. "
                   f"Remaining: {rate_limiter.get_message_remaining(user.id)}",
        )

    service = AssistantSessionService(db=db)

    # Track session metrics
    session_metrics = metrics.get_session_metrics(session_id)
    if session_metrics is None:
        session_metrics = metrics.record_session_created(session_id, user.id)

    # Track step count and tool calls for metrics
    step_count = 0
    tool_calls: Counter[str] = Counter()

    # Use LangGraph-based chat by default (Task 9: LangGraph integration)
    use_graph = is_graph_enabled()
    logger.info("Using %s-based chat for session %s", "LangGraph" if use_graph else "ReActAgent", session_id)

    # Create event generator with metrics tracking
    async def event_generator() -> AsyncGenerator[dict]:
        nonlocal step_count
        session_start_time = time.time()

        try:
            # Use graph-based chat if enabled (Task 9)
            if use_graph and hasattr(service, 'chat_with_graph'):
                chat_generator = service.chat_with_graph(
                    session_id, user.id, body.message, client_message_id=body.client_message_id
                )
            else:
                chat_generator = service.chat(
                    session_id, user.id, body.message, client_message_id=body.client_message_id
                )
            
            async for event in chat_generator:
                event_dict = None
                try:
                    sse_data = EventMapper.event_to_sse_event(event)
                    event_dict = {
                        "event": sse_data["event"],
                        "data": json.dumps(sse_data["data"], default=str),
                    }
                except Exception as exc:
                    logger.warning("Failed to map event: %s", exc)
                    continue

                # Track metrics based on event type
                event_type = sse_data.get("event", "")
                if event_type == "step":
                    step_count += 1
                elif event_type == "tool":
                    tool_name = sse_data.get("data", {}).get("tool", "unknown")
                    tool_calls[tool_name] += 1
                    metrics.record_tool_call(tool_name)
                    
                if hasattr(event, "usage") and getattr(event, "usage", None):
                    usage_dict = event.usage
                    try:
                        usage_obj = LLMUsage(
                            input_tokens=usage_dict.get("input_tokens", 0),
                            output_tokens=usage_dict.get("output_tokens", 0),
                            model=usage_dict.get("model", "unknown")
                        )
                        # Fire and forget logging (db.add is sync within async session)
                        await log_llm_usage(db, user.id, usage_obj, context="assistant")
                    except Exception as e:
                        logger.warning("Failed to log LLM usage: %s", e)

                yield event_dict

        finally:
            # Record session ended metrics
            wall_time = time.time() - session_start_time
            final_status = "completed"

            # Log structured summary for the session
            logger.info(
                "Assistant session completed",
                extra={
                    "session_id": str(session_id),
                    "user_id": str(user.id),
                    "step_count": step_count,
                    "wall_time": round(wall_time, 2),
                    "tool_calls": dict(tool_calls),
                    "status": final_status,
                },
            )

            # Record session ended
            metrics.record_session_ended(
                session_id=session_id,
                status=final_status,
                step_count=step_count,
                tool_calls=tool_calls,
                tokens_used=0,  # Token tracking requires integration with provider
            )
            # Record into eval counters for /api/stats/eval
            from app.services.eval_counters import eval_counters as _ec
            _ec.sessions.record(wall_time_s=wall_time, success=(final_status == "completed"))

    # Verify session exists
    session = await service.get_session(user, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or you don't have access to it.",
        )

    # Record message after validation
    rate_limiter.record_message(user.id)

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            # Disable Nginx buffering so tokens stream to the client immediately
            "X-Accel-Buffering": "no",
            # Prevent proxies from caching the stream
            "Cache-Control": "no-cache, no-transform",
        },
    )


@router.post(
    "/sessions/{session_id}/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def stop_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """
    Stop a running chat session.

    This sets a cancellation flag that the in-flight chat() generator
    will check and respond to by yielding DoneEvent.

    Returns 204 immediately. The SSE stream will end with:
    - ErrorEvent(code="CANCELLED", ...)
    - DoneEvent(summary="Session cancelled.")
    """
    service = AssistantSessionService(db=db)

    # Verify session exists and is owned by user
    session = await service.get_session(user, session_id, include_events=False)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or you don't have access to it.",
        )

    # Stop the session (no-op if not running)
    await service.stop_session(session_id)


# ── Observability Endpoints ────────────────────────────────────────────────────


@router.get(
    "/rate-limits",
    responses={
        401: {"model": ErrorResponse},
    },
)
async def get_rate_limits(
    user: User = Depends(get_current_user),
) -> dict:
    """
    Get current rate limit status for the authenticated user.

    Returns:
        - concurrent_sessions: active, max (10), remaining
        - message_rate: remaining, max_per_hour (100)
    """
    return rate_limiter.get_limits_info(user.id)


@router.get(
    "/metrics",
    responses={
        401: {"model": ErrorResponse},
    },
)
async def get_metrics(
    user: User = Depends(get_current_user),
) -> dict:
    """
    Get aggregated metrics summary (admin-level view).

    For production, consider exposing via Prometheus /metrics endpoint.

    Returns:
        - sessions_created: Total sessions created
        - tool_calls_total: Tool calls by tool name
        - llm_tokens_total: LLM tokens by role
        - steps_total: Steps by final status
    """
    return metrics.get_summary()

