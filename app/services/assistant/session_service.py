"""AssistantSessionService - Session lifecycle and chat orchestration.

This service owns the session lifecycle (create/get/list/delete) and exposes
`chat()` as an AsyncGenerator[BaseEvent] that:
1. Builds toolkits with the user's context
2. Loads ReActAgent scratchpad context if resuming
3. Runs ReActAgent
4. Persists every event to the DB

Usage:
    service = AssistantSessionService(db=db)
    
    # Create a session
    session = await service.create_session(user, project_id=None)
    
    # List sessions
    sessions = await service.list_sessions(user)
    
    # Chat (yields events in real time)
    async for event in service.chat(session.id, user.id, "Find papers on RAG"):
        print(event)
    
    # Stop a running session
    await service.stop_session(session.id)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.assistant.event_mapper import EventMapper
from app.agents.assistant.events import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
)
from app.agents.assistant.react.agent import ReActAgent, ProjectContext
from app.agents.assistant.react.memory import Scratchpad
from app.agents.assistant.tools import get_all_tools, get_all_toolkits
from app.agents.assistant.tools.context import set_user_context, clear_user_context
from app.db.models import AssistantEvent as DBAssistantEvent
from app.db.models import AssistantSession as DBAssistantSession
from app.db.models import Project
from app.db.models import User
from app.ai.provider import get_provider

if TYPE_CHECKING:
    from app.db.models import AssistantSession

logger = logging.getLogger(__name__)


# In-memory maps for tracking.
# Limitation: only works for a single backend instance.
# For multi-instance deployment, move to Redis pub/sub in a follow-up.
_cancellation_flags: Dict[str, asyncio.Event] = {}  # For external cancellation (stop button)
_active_chat_flags: Dict[str, bool] = {}  # For tracking concurrent chats
MAX_CONTEXT_MESSAGES = 8
MAX_CONTEXT_CHARS_PER_MESSAGE = 1200


def sort_session_events(events: list[DBAssistantEvent]) -> list[DBAssistantEvent]:
    """Sort assistant events chronologically by the timestamp in their payload.
    
    Falls back to e.created_at if timestamp is missing or invalid.
    """
    def get_event_timestamp(event: DBAssistantEvent) -> datetime:
        if isinstance(event.payload, dict) and "timestamp" in event.payload:
            ts_str = event.payload["timestamp"]
            if isinstance(ts_str, str):
                try:
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    dt = datetime.fromisoformat(ts_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    pass
        created_at = event.created_at
        if created_at is None or not isinstance(created_at, datetime):
            return datetime.min.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at

    return sorted(events, key=get_event_timestamp)


def _build_conversation_context(events: list[DBAssistantEvent]) -> str:
    """Build a compact chat history block for the next LLM request."""
    messages: list[str] = []

    sorted_events = sort_session_events(events)
    for event in sorted_events:
        if event.event_type != "message":
            continue

        role = event.payload.get("role")
        content = event.payload.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue

        text = content.strip()
        if not text:
            continue

        if len(text) > MAX_CONTEXT_CHARS_PER_MESSAGE:
            text = f"{text[:MAX_CONTEXT_CHARS_PER_MESSAGE].rstrip()}..."

        messages.append(f"{role}: {text}")

    return "\n".join(messages[-MAX_CONTEXT_MESSAGES:])


def _restore_scratchpad_from_events(
    scratchpad: Scratchpad,
    events: List["DBAssistantEvent"],
) -> None:
    """Restore scratchpad from persisted events for resume.

    Reconstructs observations from tool events so the ReAct loop
    can continue from where it left off.

    Args:
        scratchpad: The scratchpad to restore into.
        events: The persisted session events.
    """
    # Sort events first so they are chronological
    sorted_events = sort_session_events(events)
    # Only look at recent events to avoid excessive context
    recent_events = sorted_events[-50:] if len(sorted_events) > 50 else sorted_events

    for event in recent_events:
        if event.event_type == "tool":
            payload = event.payload
            tool_name = payload.get("function") or payload.get("name", "")
            args = payload.get("args", {})
            result = payload.get("result")

            if tool_name and result:
                # Add observation to scratchpad
                scratchpad.add_observation(tool_name, args, result)

        elif event.event_type == "thought":
            payload = event.payload
            delta = payload.get("delta", "")
            iteration = payload.get("iteration", 0)

            # Add thought to scratchpad trace
            if delta:
                scratchpad.trace.append({
                    "type": "thought",
                    "content": delta,
                    "iteration": iteration,
                })


def _get_cancellation_event(session_id: str) -> asyncio.Event:
    """Get or create a cancellation event for a session."""
    if session_id not in _cancellation_flags:
        _cancellation_flags[session_id] = asyncio.Event()
    return _cancellation_flags[session_id]


def _clear_cancellation_event(session_id: str) -> None:
    """Clear a cancellation event after session ends."""
    if session_id in _cancellation_flags:
        del _cancellation_flags[session_id]


class AssistantSessionSummary:
    """Lightweight summary of a session for list display."""

    def __init__(
        self,
        id: uuid.UUID,
        title: Optional[str],
        project_id: Optional[uuid.UUID],
        project_title: Optional[str],
        status: str,
        created_at: datetime,
        updated_at: datetime,
        event_count: int,
    ) -> None:
        self.id = id
        self.title = title
        self.project_id = project_id
        self.project_title = project_title
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.event_count = event_count

    @classmethod
    def from_model(cls, session: "AssistantSession") -> "AssistantSessionSummary":
        """Create a summary from a database model."""
        project_title = None
        if session.project:
            project_title = session.project.title

        return cls(
            id=session.id,
            title=session.title,
            project_id=session.project_id,
            project_title=project_title,
            status=session.status,
            created_at=session.created_at,
            updated_at=session.updated_at,
            event_count=len(session.events) if hasattr(session, "events") else 0,
        )


class AssistantSessionService:
    """
    Service for managing assistant session lifecycle and chat.

    Provides CRUD operations for sessions and the main chat() method
    that orchestrates the ReActAgent.

    Attributes:
        db: SQLAlchemy AsyncSession for database operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize the session service.

        Args:
            db: SQLAlchemy AsyncSession instance.
        """
        self.db = db

    # ── CRUD Operations ────────────────────────────────────────────────────────

    async def create_session(
        self,
        user: User,
        project_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
    ) -> "AssistantSession":
        """
        Create a new assistant session.

        Args:
            user: The authenticated user.
            project_id: Optional project ID to pin the session to.
            title: Optional session title.

        Returns:
            The created AssistantSession.

        Raises:
            ValueError: If project_id is provided but project doesn't exist.
            PermissionError: If project_id is provided but user doesn't own it.
        """
        # Validate project ownership if project_id is provided
        if project_id:
            result = await self.db.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.owner_id == user.id,
                )
            )
            project = result.scalar_one_or_none()
            if project is None:
                raise ValueError(
                    f"Project {project_id} not found or you don't have access to it"
                )

        # Create session
        session = DBAssistantSession(
            user_id=user.id,
            project_id=project_id,
            title=title,
            status="active",
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        logger.info("Created assistant session %s for user %s", session.id, user.id)
        return session

    async def get_session(
        self,
        user: User,
        session_id: uuid.UUID,
        include_events: bool = True,
    ) -> Optional["AssistantSession"]:
        """
        Get a session by ID.

        Args:
            user: The authenticated user.
            session_id: The session ID.
            include_events: If True, eagerly load events and plan.

        Returns:
            The session if found and owned by user, None otherwise.
        """
        query = select(DBAssistantSession).where(
            DBAssistantSession.id == session_id,
            DBAssistantSession.user_id == user.id,
        )

        if include_events:
            query = query.options(
                selectinload(DBAssistantSession.events),
                selectinload(DBAssistantSession.project),
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AssistantSessionSummary]:
        """
        List sessions for a user.

        Args:
            user: The authenticated user.
            limit: Maximum number of sessions to return.
            offset: Number of sessions to skip.

        Returns:
            List of session summaries ordered by updated_at descending.
        """
        # Get sessions with event count
        result = await self.db.execute(
            select(DBAssistantSession)
            .where(DBAssistantSession.user_id == user.id)
            .options(
                selectinload(DBAssistantSession.project),
                selectinload(DBAssistantSession.events),
            )
            .order_by(DBAssistantSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        sessions = result.scalars().all()

        return [AssistantSessionSummary.from_model(s) for s in sessions]

    async def delete_session(
        self,
        user: User,
        session_id: uuid.UUID,
    ) -> bool:
        """
        Delete a session.

        Args:
            user: The authenticated user.
            session_id: The session ID.

        Returns:
            True if deleted, False if not found.
        """
        session = await self.get_session(user, session_id, include_events=False)
        if session is None:
            return False

        await self.db.delete(session)
        await self.db.commit()

        # Clean up cancellation flag
        _clear_cancellation_event(str(session_id))

        logger.info("Deleted assistant session %s", session_id)
        return True

    async def update_session_title(
        self,
        session: DBAssistantSession,
        title: str,
    ) -> None:
        """Update a session's title."""
        session.title = title
        session.updated_at = datetime.now()
        await self.db.commit()

    # ── Chat Operation ─────────────────────────────────────────────────────────

    async def chat(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        message: str,
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Run the chat flow for a session.

        This method:
        1. Loads the session and validates ownership
        2. Builds toolkits with user/project context
        3. Initializes ReActAgent
        4. Runs ReActAgent loop
        5. Persists every event to the DB

        Args:
            session_id: The session ID.
            user_id: The authenticated user's ID.
            message: The user's message.

        Yields:
            BaseEvent: Events from the agent execution.

        Raises:
            ValueError: If session not found or user doesn't have access.
            RuntimeError: If a chat is already running on this session.
        """
        session_id_str = str(session_id)
        logger.info("Chat started for session %s", session_id_str)

        # Check for concurrent chat using separate flag
        if _active_chat_flags.get(session_id_str, False):
            # Previous chat is still running
            # Previous chat is still running
            yield ErrorEvent(
                code="SESSION_BUSY",
                message="A chat is already running on this session. Please wait or stop it first.",
            )
            yield DoneEvent(summary="Session is busy.")
            return

        # Load session
        result = await self.db.execute(
            select(DBAssistantSession)
            .where(
                DBAssistantSession.id == session_id,
                DBAssistantSession.user_id == user_id,
            )
            .options(
                selectinload(DBAssistantSession.project),
                selectinload(DBAssistantSession.events),
            )
        )
        session = result.scalar_one_or_none()

        if session is None:
            yield ErrorEvent(
                code="SESSION_NOT_FOUND",
                message=f"Session {session_id} not found or you don't have access.",
            )
            yield DoneEvent(summary="Session not found.")
            return

        # Note: We don't set cancel_event here because it would trigger
        # the agent's cancellation check at the start of each loop iteration.
        # The cancel_event is only meant for external cancellation (stop button).
        # For tracking concurrent chats, we rely on the SESSION_BUSY check above.

        # Get cancellation event for agent (will be set by stop_session if needed)
        cancel_event = _get_cancellation_event(session_id_str)

        try:
            # Build project context
            project_context: Dict[str, Any] = {}
            if session.project:
                project_context = {
                    "project_id": str(session.project.id),
                    "project_name": session.project.title,
                    "topic": session.project.topic,
                    "research_question": session.project.research_question,
                }

            # Get user from database for toolkit context
            user_result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if user is None:
                yield ErrorEvent(
                    code="USER_NOT_FOUND",
                    message="User not found.",
                )
                yield DoneEvent(summary="User not found.")
                return

            # Build toolkit context and tools with the authenticated user.
            # Set user context so tools can access authenticated user via contextvars
            set_user_context(
                user_id=str(user_id),
                project_id=str(session.project_id) if session.project_id else None,
                user=user,
            )
            tools = get_all_tools(
                user_id=str(user_id),
                project_id=str(session.project_id) if session.project_id else None,
                user=user,
            )

            # Get LLM provider
            provider = get_provider()

            # Initialize ReAct agent
            agent = ReActAgent(
                provider=provider,
                tools=tools,
                project_context=ProjectContext(
                    project_id=str(session.project_id) if session.project_id else None,
                    user_id=str(user_id),
                ),
            )

            # Sort events chronologically by payload timestamp
            sorted_events = sort_session_events(session.events)

            # Check for title event in persisted events
            title_from_history = None
            for event in sorted_events:
                if event.event_type == "title" and event.payload.get("title"):
                    title_from_history = event.payload["title"]
                    break

            # Resume logic: if session was waiting for user input, restore scratchpad
            resume = False
            if sorted_events:
                # Check if session was in a waiting state (can resume)
                for event in sorted_events[-10:]:  # Check last 10 events
                    if event.event_type == "wait":
                        resume = True
                        break

            # Restore scratchpad from persisted events if resuming
            if resume:
                # Re-build scratchpad from tool observation events
                _restore_scratchpad_from_events(agent.scratchpad, sorted_events)

            conversation_context = _build_conversation_context(sorted_events)
            flow_message = message
            if conversation_context:
                flow_message = (
                    "Previous conversation in this session:\n"
                    f"{conversation_context}\n\n"
                    "Current user request:\n"
                    f"{message}"
                )

            # Save user message
            await self._persist_event(
                session_id=session.id,
                event_type="message",
                payload={
                    "role": "user",
                    "content": message,
                    "id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            # Mark chat as active
            _active_chat_flags[session_id_str] = True

            # Run the agent
            async for event in agent.run(
                flow_message,
                resume=resume,
                cancel_event=cancel_event,
            ):
                # Persist event
                await self._persist_event(
                    session_id=session.id,
                    event_type=event.type,
                    payload=EventMapper.event_to_sse_event(event)["data"],
                )

                # Auto-generate session title from the first user message.
                # Only set once per session, and truncate to keep list views tidy.
                if (
                    isinstance(event, MessageEvent)
                    and event.role == "user"
                    and not title_from_history
                ):
                    cleaned = message.strip().splitlines()[0] if message.strip() else ""
                    title_from_history = cleaned[:60].rstrip()
                    if title_from_history:
                        await self.update_session_title(session, title_from_history)

                # Update session status on completion
                if isinstance(event, DoneEvent):
                    session.status = "archived"
                    await self.db.commit()

                yield event

        except asyncio.CancelledError:
            logger.info("Chat cancelled for session %s", session_id)
            yield ErrorEvent(
                code="CANCELLED",
                message="Session was cancelled.",
            )
            yield DoneEvent(summary="Session cancelled.")
        except Exception as exc:
            logger.exception("Chat failed for session %s: %s", session_id, exc)
            yield ErrorEvent(
                code="CHAT_FAILED",
                message=f"Chat failed: {exc}",
            )
            yield DoneEvent(summary="Chat failed.")
        finally:
            # Clear tracking flags and user context
            _active_chat_flags.pop(session_id_str, None)
            _clear_cancellation_event(session_id_str)
            clear_user_context()

    async def stop_session(self, session_id: uuid.UUID) -> bool:
        """
        Stop a running chat session.

        Args:
            session_id: The session ID.

        Returns:
            True if stopped, False if session was not running.
        """
        session_id_str = str(session_id)

        if not _active_chat_flags.get(session_id_str, False):
            # No active chat
            return False

        # Set cancellation event to trigger cancellation
        cancel_event = _get_cancellation_event(session_id_str)
        cancel_event.set()
        logger.info("Stop requested for session %s", session_id)
        return True

    # ── Internal Helpers ───────────────────────────────────────────────────────

    async def _persist_event(
        self,
        session_id: uuid.UUID,
        event_type: str,
        payload: Dict[str, Any],
    ) -> DBAssistantEvent:
        """
        Persist an event to the database.

        Args:
            session_id: The session ID.
            event_type: The event type string.
            payload: The serialized event payload.

        Returns:
            The created DBAssistantEvent.
        """
        event = DBAssistantEvent(
            session_id=session_id,
            event_type=event_type,
            payload=payload,
        )
        self.db.add(event)

        # Update session's updated_at
        result = await self.db.execute(
            select(DBAssistantSession).where(DBAssistantSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.updated_at = datetime.now()

        await self.db.commit()
        return event

    # ── Event Replay ───────────────────────────────────────────────────────────

    async def get_persisted_events(
        self,
        session_id: uuid.UUID,
    ) -> List[BaseEvent]:
        """
        Get all persisted events for a session, replayed as BaseEvent objects.

        Args:
            session_id: The session ID.

        Returns:
            List of BaseEvent objects in chronological order.
        """
        result = await self.db.execute(
            select(DBAssistantEvent)
            .where(DBAssistantEvent.session_id == session_id)
            .order_by(DBAssistantEvent.created_at)
        )
        events = result.scalars().all()
        sorted_events = sort_session_events(events)

        parsed_events: List[BaseEvent] = []
        for event in sorted_events:
            try:
                parsed = EventMapper.parse_event(event.event_type, event.payload)
                parsed_events.append(parsed)
            except Exception as exc:
                logger.warning(
                    "Failed to parse event %s (%s): %s",
                    event.id,
                    event.event_type,
                    exc,
                )
                # Create a generic message event as fallback
                parsed_events.append(
                    MessageEvent(
                        role="assistant",
                        content=f"[Could not parse event: {event.event_type}]",
                    )
                )

        return parsed_events
