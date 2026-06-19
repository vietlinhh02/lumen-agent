"""AssistantSessionService - Session lifecycle and chat orchestration.

This service owns the session lifecycle (create/get/list/delete) and exposes
`chat()` as an AsyncGenerator[BaseEvent] that:
1. Builds toolkits with the user's context
2. Loads ReActAgent scratchpad context if resuming
3. Runs ReActAgent (or AssistantGraph when USE_LANGGRAPH_ASSISTANT=true)
4. Persists high-value events to the DB

LangGraph Integration (Task 9):
    When USE_LANGGRAPH_ASSISTANT=true, the service uses AssistantGraph
    with checkpointing instead of ReActAgent. This provides:
    - Persistent scratchpad across interruptions
    - Native LangGraph state management
    - Reliable wait/resume capability

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
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.assistant.event_mapper import EventMapper
from app.agents.assistant.events import (
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    TitleEvent,
)
from app.agents.assistant.react.agent import ProjectContext, ReActAgent
from app.agents.assistant.react.memory import Scratchpad
from app.agents.assistant.tools import get_all_tools
from app.agents.assistant.tools.context import clear_user_context, set_user_context

# LangGraph integration (Task 9)
try:
    from app.agents.assistant.graph.adapter import create_graph_runner, is_graph_enabled
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    def is_graph_enabled() -> bool:
        return False
from app.ai.provider import get_provider
from app.db.models import AssistantEvent as DBAssistantEvent
from app.db.models import AssistantSession as DBAssistantSession
from app.db.models import Project, User

if TYPE_CHECKING:
    from app.db.models import AssistantSession

logger = logging.getLogger(__name__)


# In-memory maps for tracking.
# Limitation: only works for a single backend instance.
# For multi-instance deployment, move to Redis pub/sub in a follow-up.
_cancellation_flags: dict[str, asyncio.Event] = {}  # For external cancellation (stop button)
_active_chat_flags: dict[str, bool] = {}  # For tracking concurrent chats
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
                        dt = dt.replace(tzinfo=UTC)
                    return dt
                except ValueError:
                    pass
        created_at = event.created_at
        if created_at is None or not isinstance(created_at, datetime):
            return datetime.min.replace(tzinfo=UTC)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
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
    events: list[DBAssistantEvent],
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
        title: str | None,
        project_id: uuid.UUID | None,
        project_title: str | None,
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
    def from_model(cls, session: AssistantSession) -> AssistantSessionSummary:
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
        project_id: uuid.UUID | None = None,
        title: str | None = None,
    ) -> AssistantSession:
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
    ) -> AssistantSession | None:
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
    ) -> list[AssistantSessionSummary]:
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

    async def update_session_project(
        self,
        session: DBAssistantSession,
        project_id: uuid.UUID | None,
    ) -> None:
        """Update a session's project."""
        session.project_id = project_id
        session.updated_at = datetime.now()
        await self.db.commit()

    # ── Chat Operation ─────────────────────────────────────────────────────────

    async def chat(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        message: str,
    ) -> AsyncGenerator[BaseEvent]:
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
            if session.project:
                {
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
                    project_name=session.project.title if session.project else None,
                    topic=session.project.topic if session.project else None,
                    research_question=session.project.research_question if session.project else None,
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
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            generated_title = message.strip().splitlines()[0] if message.strip() else ""
            if generated_title and not title_from_history and not session.title:
                title_from_history = generated_title[:60].rstrip()
                if title_from_history:
                    await self.update_session_title(session, title_from_history)
                    title_event = TitleEvent(title=title_from_history)
                    await self._persist_event(
                        session_id=session.id,
                        event_type="title",
                        payload=EventMapper.event_to_sse_event(title_event)["data"],
                    )
                    yield title_event

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

    # ── LangGraph Chat (Task 9) ─────────────────────────────────────────────────

    async def chat_with_graph(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        message: str,
        client_message_id: str | None = None,
    ) -> AsyncGenerator[BaseEvent]:
        """
        Run the chat flow using LangGraph-based AssistantGraph.

        This method provides checkpointing for reliable wait/resume:
        - Scratchpad is persisted in LangGraph state
        - No need to reconstruct from SQL events on resume
        - Native LangGraph state management

        Enabled via USE_LANGGRAPH_ASSISTANT=true environment variable.

        Args:
            session_id: The session ID.
            user_id: The authenticated user's ID.
            message: The user's message.
            client_message_id: Optional client-generated ID for deduplication.

        Yields:
            BaseEvent: Events from the agent execution.
        """
        if not LANGGRAPH_AVAILABLE:
            logger.warning("LangGraph not available, falling back to chat()")
            async for event in self.chat(session_id, user_id, message, client_message_id):
                yield event
            return

        session_id_str = str(session_id)
        logger.info("Chat with graph started for session %s", session_id_str)

        # Generate turn_id for this user request
        turn_id = str(uuid.uuid4())

        # Check for concurrent chat
        if _active_chat_flags.get(session_id_str, False):
            yield ErrorEvent(
                code="SESSION_BUSY",
                message="A chat is already running on this session.",
            )
            yield DoneEvent(summary="Session is busy.")
            return

        # Load session
        from sqlalchemy.orm import selectinload

        from app.db.models import AssistantMessage

        result = await self.db.execute(
            select(DBAssistantSession)
            .where(
                DBAssistantSession.id == session_id,
                DBAssistantSession.user_id == user_id,
            )
            .options(
                selectinload(DBAssistantSession.project),
                selectinload(DBAssistantSession.messages),
                selectinload(DBAssistantSession.events),
            )
        )
        session = result.scalar_one_or_none()

        if session is None:
            yield ErrorEvent(
                code="SESSION_NOT_FOUND",
                message=f"Session {session_id} not found.",
            )
            yield DoneEvent(summary="Session not found.")
            return

        # Get cancellation event
        cancel_event = _get_cancellation_event(session_id_str)

        try:
            # Build project context
            project_context: dict[str, Any] = {}
            if session.project:
                project_context = {
                    "project_id": str(session.project.id),
                    "project_name": session.project.title,
                    "topic": session.project.topic,
                    "research_question": session.project.research_question,
                }

            # Get user
            from app.db.models import User
            user_result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if user is None:
                yield ErrorEvent(code="USER_NOT_FOUND", message="User not found.")
                yield DoneEvent(summary="User not found.")
                return

            # Get tools
            tools = get_all_tools(
                user_id=str(user_id),
                project_id=str(session.project_id) if session.project_id else None,
                user=user,
            )

            # Set user context for tools (include tools for graph access)
            set_user_context(
                user_id=str(user_id),
                project_id=str(session.project_id) if session.project_id else None,
                user=user,
                tools=tools,
            )

            # Get provider
            from app.ai.provider import get_provider
            provider = get_provider()

            # Check if session was waiting (for resume)
            resume = False
            sorted_events = sort_session_events(session.events)
            if sorted_events:
                for event in sorted_events[-10:]:
                    if event.event_type == "wait":
                        resume = True
                        break

            # ── Auto-create project if session has none ─────────────────────
            # Only auto-create for research-related intents (not greetings,
            # chitchat, or ambiguous messages). Uses IntentClassifier to
            # check intent BEFORE creating a project.
            _RESEARCH_INTENTS = {
                "research_pipeline", "search_only", "matrix_only",
                "gap_only", "report_only", "qa", "create_project",
            }
            auto_created_message: MessageEvent | None = None
            if session.project_id is None:
                # Classify intent first to avoid creating projects for greetings
                from app.agents.assistant.react.intent_classifier import IntentClassifier
                _classifier = IntentClassifier(provider)
                try:
                    _intent = await _classifier.classify(message, project_context or None)
                    _should_create = _intent.intent in _RESEARCH_INTENTS
                except Exception as _exc:
                    logger.warning("Intent pre-check failed, skipping auto-create: %s", _exc)
                    _should_create = False

                if _should_create:
                    auto_project = await self._auto_create_project(session, message, user)
                    if auto_project is not None:
                        session.project_id = auto_project.id
                        await self.db.commit()
                        await self.db.refresh(session, attribute_names=["project"])
                        # Rebuild project_context with the new project so the
                        # graph and downstream tools see it.
                        project_context = {
                            "project_id": str(auto_project.id),
                            "project_name": auto_project.title,
                            "topic": auto_project.topic,
                            "research_question": auto_project.research_question,
                        }
                        # Update user context (tools look up project_id from here)
                        set_user_context(
                            user_id=str(user_id),
                            project_id=str(auto_project.id),
                            user=user,
                            tools=tools,
                        )
                        logger.info(
                            "Auto-created project %s for session %s",
                            auto_project.id,
                            session_id,
                        )
                        # Surface the project creation to the user before the
                        # pipeline starts so the action is visible in the chat.
                        auto_created_message = MessageEvent(
                            role="assistant",
                            content=(
                                f"Đã tạo project mới: **{auto_project.title}**. "
                                "Em sẽ chạy research pipeline với chủ đề này nhé."
                            ),
                        )

            # ── Build conversation context (windowed + truncated) ──────────
            # For long-running sessions the LLM context window would explode
            # if we passed every prior turn verbatim. _build_conversation_context
            # keeps the last 8 messages and truncates each to 1200 chars
            # (matches the legacy ReAct path so behavior is consistent).
            sorted_events = sort_session_events(session.events)
            conversation_context = _build_conversation_context(sorted_events)
            graph_message = message
            if conversation_context:
                graph_message = (
                    "Previous conversation in this session:\n"
                    f"{conversation_context}\n\n"
                    "Current user request:\n"
                    f"{message}"
                )

            # Create graph runner
            runner = create_graph_runner(
                session_id=session.id,
                user_id=user.id,
                project_context=project_context,
                tools=tools,
                provider=provider,
            )

            # Save user message
            canonical_message_id = client_message_id or str(uuid.uuid4())
            from app.db.models import AssistantMessage
            user_message = AssistantMessage(
                session_id=session.id,
                turn_id=turn_id,
                role="user",
                content=message,
                client_message_id=client_message_id,
            )
            self.db.add(user_message)
            await self.db.flush()  # Flush to get the user_message.id
            # Also persist event for frontend compatibility
            await self._persist_event(
                session_id=session.id,
                event_type="message",
                payload={
                    "id": str(user_message.id),
                    "type": "message",
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "turn_id": turn_id,
                },
                turn_id=turn_id,
            )
            await self.db.commit()

            generated_title = message.strip().splitlines()[0] if message.strip() else ""
            if generated_title and not session.title:
                title = generated_title[:60].rstrip()
                if title:
                    session.title = title
                    session.updated_at = datetime.now()
                    await self.db.commit()
                    title_event = TitleEvent(title=title, turn_id=turn_id)
                    await self._persist_event(
                        session_id=session.id,
                        event_type="title",
                        payload=EventMapper.event_to_sse_event(title_event)["data"],
                        turn_id=turn_id,
                    )
                    yield title_event

            # Emit ack if client provided ID
            if client_message_id:
                from app.agents.assistant.events import MessageAckEvent as MAE
                yield MAE(
                    client_message_id=client_message_id,
                    canonical_id=canonical_message_id,
                    turn_id=turn_id,
                )

            # Surface auto-created project (if any) to the user before the
            # pipeline starts. Persist to DB so it's part of the transcript.
            if auto_created_message is not None:
                # Persist as a message row so reload shows the same text
                acm_row = AssistantMessage(
                    session_id=session.id,
                    turn_id=turn_id,
                    role="assistant",
                    content=auto_created_message.content,
                )
                self.db.add(acm_row)
                await self.db.flush()
                # Also persist as a message event for FE compatibility
                await self._persist_event(
                    session_id=session.id,
                    event_type="message",
                    payload={
                        "id": str(acm_row.id),
                        "type": "message",
                        "role": "assistant",
                        "content": auto_created_message.content,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "turn_id": turn_id,
                    },
                    turn_id=turn_id,
                )
                await self.db.commit()
                yield auto_created_message

            # Mark chat as active
            _active_chat_flags[session_id_str] = True

            # Track accumulators for assistant message
            assistant_content = ""
            assistant_pending = False

            # Run graph
            async for event in runner.run(
                graph_message,
                resume=resume,
                cancel_event=cancel_event,
            ):
                event.turn_id = turn_id

                # Handle assistant delta accumulation
                from app.agents.assistant.events import AssistantDeltaEvent as ADE
                if isinstance(event, ADE):
                    # Accumulate delta content
                    if event.delta:
                        assistant_content += event.delta
                        assistant_pending = True
                    
                    # When final delta arrives (is_final=True), persist the message
                    # regardless of whether this final delta had content
                    if event.is_final and assistant_pending:
                        # Yield the final delta FIRST so frontend closes the streaming message
                        yield event

                        # Persist final assistant message
                        assistant_msg = AssistantMessage(
                            session_id=session.id,
                            turn_id=turn_id,
                            role="assistant",
                            content=assistant_content,
                        )
                        self.db.add(assistant_msg)
                        await self.db.flush()  # Flush to get the assistant_msg.id
                        # Also persist event for frontend compatibility
                        await self._persist_event(
                            session_id=session.id,
                            event_type="message",
                            payload={
                                "id": str(assistant_msg.id),
                                "type": "message",
                                "role": "assistant",
                                "content": assistant_content,
                                "timestamp": datetime.now(UTC).isoformat(),
                                "turn_id": turn_id,
                            },
                            turn_id=turn_id,
                        )
                        await self.db.commit()

                        # Emit MessageEvent to frontend with canonical ID
                        # so the frontend can replace the streaming message
                        from app.agents.assistant.events import MessageEvent as ME
                        yield ME(
                            id=str(assistant_msg.id),
                            role="assistant",
                            content=assistant_content,
                            turn_id=turn_id,
                        )

                        assistant_pending = False
                        assistant_content = ""
                        continue  # Skip yielding the event again at the bottom

                elif isinstance(event, MessageEvent) and event.role == "assistant":
                    # Persist direct message events immediately
                    assistant_msg = AssistantMessage(
                        session_id=session.id,
                        turn_id=turn_id,
                        role="assistant",
                        content=event.content,
                    )
                    self.db.add(assistant_msg)
                    await self.db.flush()
                    
                    event.id = str(assistant_msg.id)
                    
                    await self._persist_event(
                        session_id=session.id,
                        event_type="message",
                        payload={
                            "id": str(assistant_msg.id),
                            "type": "message",
                            "role": "assistant",
                            "content": event.content,
                            "timestamp": datetime.now(UTC).isoformat(),
                            "turn_id": turn_id,
                        },
                        turn_id=turn_id,
                    )
                    await self.db.commit()

                # Update session status on completion
                if isinstance(event, DoneEvent):
                    if event.summary and "cancelled" in event.summary.lower():
                        session.status = "cancelled"
                    else:
                        session.status = "completed"
                    await self.db.commit()

                yield event

        except asyncio.CancelledError:
            logger.info("Graph chat cancelled for session %s", session_id)
            if session:
                session.status = "cancelled"
                await self.db.commit()
            yield ErrorEvent(code="CANCELLED", message="Session was cancelled.")
            yield DoneEvent(summary="Session cancelled.")
        except Exception as exc:
            logger.exception("Graph chat failed for session %s: %s", session_id, exc)
            if session:
                session.status = "failed"
                await self.db.commit()
            yield ErrorEvent(code="CHAT_FAILED", message=f"Chat failed: {exc}")
            yield DoneEvent(summary="Chat failed.")
        finally:
            _active_chat_flags.pop(session_id_str, None)
            _clear_cancellation_event(session_id_str)
            clear_user_context()

    # ── Internal Helpers ───────────────────────────────────────────────────────

    async def _auto_create_project(
        self,
        session: DBAssistantSession,
        message: str,
        user: User,
    ):
        """Auto-create a Project when a chat session has no project pinned.

        Uses the LLM to analyze the user's message and generate a concise,
        descriptive project title, a refined research topic, and a research
        question — instead of naively copying the raw message.

        Falls back to simple text extraction if the LLM call fails.

        Args:
            session: The chat session.
            message: The user's first message.
            user: The authenticated user (becomes project owner).

        Returns:
            The created Project instance, or None on failure.
        """
        from app.schemas.project import ProjectCreate
        from app.services.project import create_project

        title, topic, research_question = await self._extract_project_metadata(message)

        try:
            project = await create_project(
                self.db,
                user,
                ProjectCreate(
                    title=title,
                    topic=topic,
                    research_question=research_question,
                ),
            )
            return project
        except Exception as exc:
            logger.warning("Auto-create project failed for session %s: %s", session.id, exc)
            return None

    async def _extract_project_metadata(
        self,
        message: str,
    ) -> tuple[str, str, str | None]:
        """Use LLM to extract a proper title, topic, and research question.

        Returns:
            (title, topic, research_question) tuple. research_question may
            be None if the LLM cannot infer one.
        """
        import asyncio

        from pydantic import BaseModel, Field

        class _ProjectMeta(BaseModel):
            title: str = Field(
                description="Short, descriptive project title (max 60 chars). "
                "NOT the raw user message. Example: 'RAG for Medical QA'.",
            )
            topic: str = Field(
                description="Refined research topic (1-2 sentences). "
                "Example: 'Retrieval-Augmented Generation applied to medical question answering systems'.",
            )
            research_question: str | None = Field(
                default=None,
                description="A concrete research question if one can be inferred, else null. "
                "Example: 'How does RAG improve accuracy in medical QA compared to fine-tuned LLMs?'",
            )

        system = (
            "You are a research project metadata extractor. Given a user's "
            "chat message, produce a concise project title, a refined research "
            "topic, and an optional research question.\n\n"
            "Rules:\n"
            "- Title: max 60 characters, academic style, no quotes.\n"
            "- Topic: 1-2 clear sentences describing the research area.\n"
            "- Research question: a focused, answerable question if possible, "
            "otherwise null.\n"
            "- ALL output MUST be in English. If the user's input is in another "
            "language (e.g. Vietnamese), translate and normalize it to English "
            "to optimize for paper searching.\n"
            "- Do NOT copy the raw user message verbatim."
        )

        try:
            from app.ai.provider import get_provider
            provider = get_provider()

            result = await asyncio.wait_for(
                provider.complete_structured(
                    messages=[{"role": "user", "content": message.strip()}],
                    schema=_ProjectMeta.model_json_schema(),
                    tool_name="extract_project_metadata",
                    system=system,
                    max_tokens=300,
                ),
                timeout=8.0,
            )
            meta = _ProjectMeta.model_validate(result)
            title = (meta.title.strip()[:60] or "Untitled Research").rstrip()
            topic = (meta.topic.strip() or message.strip())[:512]
            return title, topic, meta.research_question
        except Exception as exc:
            logger.warning("LLM project metadata extraction failed: %s", exc)

        # Fallback: simple extraction
        first_line = (message.strip().splitlines() or [""])[0].strip()
        title = (first_line[:60].rstrip()) or "Untitled Research"
        topic = (message.strip() or title)[:512]
        return title, topic, None

    async def _persist_event(
        self,
        session_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
        turn_id: str | None = None,
    ) -> DBAssistantEvent:
        """
        Persist an event to the database.

        Args:
            session_id: The session ID.
            event_type: The event type string.
            payload: The serialized event payload.
            turn_id: The turn ID for grouping events.

        Returns:
            The created DBAssistantEvent.
        """
        # Default turn_id to "initial" if not provided
        if turn_id is None:
            turn_id = "initial"

        event = DBAssistantEvent(
            session_id=session_id,
            turn_id=turn_id,
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
        await self.db.refresh(event)
        return event

    # ── Event Replay ───────────────────────────────────────────────────────────

    async def get_persisted_events(
        self,
        session_id: uuid.UUID,
    ) -> list[BaseEvent]:
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

        parsed_events: list[BaseEvent] = []
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
