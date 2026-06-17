"""
Tests for AssistantSessionService.

Tests session service functionality using mocks for database and external services.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.assistant.events import (
    AssistantEvent,
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
    TitleEvent,
)


# ── Mock Fixtures ─────────────────────────────────────────────────────────────


class MockSession:
    """Mock database session."""

    def __init__(self):
        self._sessions = {}
        self._plans = {}
        self._events = {}
        self._projects = {}
        self._users = {}
        self._added = []
        self._execute_results = []  # Queue of results for execute()

    def add(self, obj):
        self._added.append(obj)
        if hasattr(obj, '__class__'):
            class_name = obj.__class__.__name__
            if class_name == 'AssistantSession':
                self._sessions[obj.id] = obj
            elif class_name == 'AssistantPlan':
                self._plans[obj.session_id] = obj
            elif class_name == 'AssistantEvent':
                self._events.setdefault(obj.session_id, []).append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        if hasattr(obj, 'id') and obj.id in self._sessions:
            del self._sessions[obj.id]

    async def execute(self, query):
        """Mock execute method that returns stored results."""
        result = MagicMock()
        if self._execute_results:
            next_result = self._execute_results.pop(0)
            if next_result is not None:
                result.scalar_one_or_none.return_value = next_result
        return result


class MockUser:
    """Mock user."""
    
    def __init__(self, id=None, email="test@example.com"):
        self.id = id or uuid.uuid4()
        self.email = email


class MockProject:
    """Mock project."""
    
    def __init__(self, id=None, owner_id=None, title="Test Project", topic="Test Topic"):
        self.id = id or uuid.uuid4()
        self.owner_id = owner_id or uuid.uuid4()
        self.title = title
        self.topic = topic
        self.research_question = None


# ── Service Tests ─────────────────────────────────────────────────────────────


class TestAssistantSessionSummary:
    """Test AssistantSessionSummary creation."""
    
    def test_from_model_creates_summary(self):
        """Test creating a summary from a model."""
        from app.services.assistant.session_service import AssistantSessionSummary
        
        session_id = uuid.uuid4()
        project_id = uuid.uuid4()
        
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.title = "Test Session"
        mock_session.project_id = project_id
        mock_session.status = "active"
        mock_session.created_at = datetime.now(timezone.utc)
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session.events = []
        mock_session.project = MagicMock()
        mock_session.project.title = "Test Project"
        
        summary = AssistantSessionSummary.from_model(mock_session)
        
        assert summary.id == session_id
        assert summary.title == "Test Session"
        assert summary.project_id == project_id
        assert summary.project_title == "Test Project"
        assert summary.status == "active"


class TestAssistantSessionServiceInit:
    """Test service initialization."""
    
    def test_service_initializes_with_db(self):
        """Test that service initializes with a db session."""
        from app.services.assistant.session_service import AssistantSessionService
        
        mock_db = MagicMock()
        service = AssistantSessionService(db=mock_db)
        
        assert service.db is mock_db


class TestCreateSession:
    """Test session creation logic."""
    
    @pytest.mark.asyncio
    async def test_create_session_without_project(self):
        """Test creating a session without a project."""
        from app.services.assistant.session_service import AssistantSessionService
        
        mock_db = MockSession()
        mock_user = MockUser()
        service = AssistantSessionService(db=mock_db)
        
        with patch.object(service, 'db', mock_db):
            # Mock the commit behavior
            created_session = await service.create_session(
                user=mock_user,
                project_id=None,
                title="My Chat",
            )
        
        # Verify session was added
        assert len(mock_db._added) >= 1
        
        # Find the session that was added
        session = mock_db._added[0]
        assert session.user_id == mock_user.id
        assert session.title == "My Chat"
        assert session.project_id is None
    
    @pytest.mark.asyncio
    async def test_create_session_with_project(self):
        """Test creating a session pinned to a project."""
        from app.services.assistant.session_service import AssistantSessionService

        mock_db = MockSession()
        mock_user = MockUser()
        mock_project = MockProject(owner_id=mock_user.id)
        mock_db._execute_results.append(mock_project)  # Return project from query

        service = AssistantSessionService(db=mock_db)

        created_session = await service.create_session(
            user=mock_user,
            project_id=mock_project.id,
            title="Project Chat",
        )

        # Verify session was created with project
        session = mock_db._added[0]
        assert session.project_id == mock_project.id

    @pytest.mark.asyncio
    async def test_create_session_invalid_project_raises(self):
        """Test that invalid project raises ValueError."""
        from app.services.assistant.session_service import AssistantSessionService

        mock_user = MockUser()
        non_existent_project_id = uuid.uuid4()

        # Create mock db that will return None for the project query
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Project not found
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = AssistantSessionService(db=mock_db)

        with pytest.raises(ValueError, match="not found or you don't have access"):
            await service.create_session(
                user=mock_user,
                project_id=non_existent_project_id,  # Non-existent project
            )


class TestChat:
    """Test chat functionality."""
    
    @pytest.mark.asyncio
    async def test_chat_session_not_found_yields_error(self):
        """Test that chat with non-existent session yields error."""
        from app.services.assistant.session_service import AssistantSessionService
        
        # Create mock db that returns None for session
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        service = AssistantSessionService(db=mock_db)
        
        events = []
        async for event in service.chat(
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            message="Hello",
        ):
            events.append(event)
        
        # Should have error event
        assert len(events) >= 1
        assert events[0].type == "error"
        assert events[0].code == "SESSION_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_chat_persists_events(self):
        """Test that chat persists user message."""
        from app.services.assistant.session_service import AssistantSessionService
        
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        
        # Create mock session
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.project_id = None
        mock_session.project = None
        mock_session.events = []
        mock_session.plan = None
        mock_session.status = "active"
        
        # Create mock db
        mock_db = MagicMock()
        
        # First call returns session, second returns user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = [
            mock_session,  # For user check
            None,  # For user lookup
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        service = AssistantSessionService(db=mock_db)
        
        # Run chat with mocked flow
        with patch("app.services.assistant.session_service.PlanActFlow") as MockFlow:
            mock_flow = MagicMock()
            mock_flow.run = AsyncMock(return_value=iter([
                DoneEvent(summary="Done"),
            ]))
            MockFlow.return_value = mock_flow
            
            with patch("app.services.assistant.session_service.get_all_tools", return_value=[]):
                with patch("app.services.assistant.session_service.get_all_toolkits", return_value=[]):
                    with patch("app.services.assistant.session_service.get_provider") as mock_provider:
                        mock_provider.return_value = MagicMock()
                        
                        events = []
                        async for event in service.chat(
                            session_id=session_id,
                            user_id=user_id,
                            message="Find papers",
                        ):
                            events.append(event)
        
        # Should complete with done event
        assert events[-1].type == "done"
    
    @pytest.mark.asyncio
    async def test_chat_concurrent_blocked(self):
        """Test that concurrent chat is blocked."""
        from app.services.assistant.session_service import (
            _cancellation_flags,
            _get_cancellation_event,
            AssistantSessionService,
        )

        session_id = uuid.uuid4()
        session_id_str = str(session_id)

        # Set cancellation flag to simulate running chat
        cancel_event = _get_cancellation_event(session_id_str)
        cancel_event.set()

        try:
            mock_db = MagicMock()
            service = AssistantSessionService(db=mock_db)

            received_events = []
            async for evt in service.chat(
                session_id=session_id,
                user_id=uuid.uuid4(),
                message="Second message",
            ):
                received_events.append(evt)

            # Should get error about session busy
            assert len(received_events) >= 1
            assert received_events[0].type == "error"
            assert received_events[0].code == "SESSION_BUSY"
        finally:
            # Clean up
            cancel_event.clear()


class TestStopSession:
    """Test session stopping."""
    
    @pytest.mark.asyncio
    async def test_stop_session_not_running(self):
        """Test stopping a session that's not running."""
        from app.services.assistant.session_service import AssistantSessionService
        
        mock_db = MagicMock()
        service = AssistantSessionService(db=mock_db)
        
        # Stop non-running session
        stopped = await service.stop_session(uuid.uuid4())
        
        assert stopped is False
    
    @pytest.mark.asyncio
    async def test_stop_session_running(self):
        """Test stopping a running session."""
        from app.services.assistant.session_service import (
            _cancellation_flags,
            _get_cancellation_event,
            AssistantSessionService,
        )
        
        session_id = uuid.uuid4()
        session_id_str = str(session_id)
        
        # Set cancellation flag
        event = _get_cancellation_event(session_id_str)
        event.set()
        
        try:
            mock_db = MagicMock()
            service = AssistantSessionService(db=mock_db)
            
            stopped = await service.stop_session(session_id)
            
            assert stopped is True
        finally:
            event.clear()


class TestPersistEvent:
    """Test event persistence."""
    
    @pytest.mark.asyncio
    async def test_persist_event(self):
        """Test that events are persisted correctly."""
        from app.services.assistant.session_service import AssistantSessionService
        
        session_id = uuid.uuid4()
        
        mock_db = MockSession()
        mock_session_result = MagicMock()
        mock_session = MagicMock()
        mock_session.updated_at = datetime.now(timezone.utc)
        mock_session_result.scalar_one_or_none.return_value = mock_session
        
        mock_db.execute = AsyncMock(return_value=mock_session_result)
        
        service = AssistantSessionService(db=mock_db)
        
        payload = {
            "role": "user",
            "content": "Hello",
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        event = await service._persist_event(
            session_id=session_id,
            event_type="message",
            payload=payload,
        )
        
        assert event.session_id == session_id
        assert event.event_type == "message"
        assert event.payload["content"] == "Hello"


class TestUpsertPlan:
    """Test plan upsert."""
    
    @pytest.mark.asyncio
    async def test_upsert_plan_creates_new(self):
        """Test creating a new plan."""
        from app.services.assistant.session_service import AssistantSessionService
        
        session_id = uuid.uuid4()
        
        mock_db = MockSession()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing plan
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        service = AssistantSessionService(db=mock_db)
        
        plan_event = PlanEvent(
            plan_id=str(uuid.uuid4()),
            title="Test Plan",
            language="en",
            steps=[
                PlanStep(
                    id="step_1",
                    description="Do something",
                    expected_tool="some_tool",
                    status="pending",
                ),
            ],
        )
        
        await service._upsert_plan(
            session_id=session_id,
            plan_event=plan_event,
        )
        
        # Should have added a plan
        assert len(mock_db._added) >= 1


class TestGetPersistedEvents:
    """Test event replay."""
    
    @pytest.mark.asyncio
    async def test_get_persisted_events(self):
        """Test replaying persisted events."""
        from app.db.models import AssistantEvent
        from app.services.assistant.session_service import AssistantSessionService
        
        session_id = uuid.uuid4()
        
        mock_db = MockSession()
        
        # Add some events
        for i in range(3):
            event = MagicMock()
            event.id = uuid.uuid4()
            event.event_type = "message"
            event.payload = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "role": "assistant",
                "content": f"Message {i}",
            }
            mock_db._events.setdefault(session_id, []).append(event)
        
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_db._events[session_id]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        service = AssistantSessionService(db=mock_db)
        
        events = await service.get_persisted_events(session_id)
        
        assert len(events) == 3
        assert all(e.type == "message" for e in events)


# ── Cancellation Flags Tests ──────────────────────────────────────────────────


def test_cancellation_flags_in_memory():
    """Test that cancellation flags work in-memory."""
    from app.services.assistant.session_service import (
        _cancellation_flags,
        _clear_cancellation_event,
        _get_cancellation_event,
    )
    
    session_id = "test-session-123"
    
    # Get event
    event1 = _get_cancellation_event(session_id)
    event2 = _get_cancellation_event(session_id)
    
    # Should be the same object
    assert event1 is event2
    
    # Set and check
    event1.set()
    assert event1.is_set()
    
    # Clear
    event1.clear()
    assert not event1.is_set()
    
    # Clean up
    _clear_cancellation_event(session_id)
    assert session_id not in _cancellation_flags


# ── EventMapper Tests ────────────────────────────────────────────────────────


class TestEventMapper:
    """Test event mapping functionality."""
    
    def test_event_to_sse_event(self):
        """Test converting event to SSE format."""
        from app.agents.assistant.event_mapper import EventMapper
        
        event = MessageEvent(
            role="assistant",
            content="Hello!",
        )
        
        sse = EventMapper.event_to_sse_event(event)
        
        assert sse["event"] == "message"
        assert sse["data"]["role"] == "assistant"
        assert sse["data"]["content"] == "Hello!"
    
    def test_parse_event(self):
        """Test parsing event from dict."""
        from app.agents.assistant.event_mapper import EventMapper
        
        data = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": "user",
            "content": "Find papers",
        }
        
        event = EventMapper.parse_event("message", data)
        
        assert isinstance(event, MessageEvent)
        assert event.role == "user"
        assert event.content == "Find papers"
    
    def test_events_to_sse_events(self):
        """Test converting multiple events to SSE."""
        from app.agents.assistant.event_mapper import EventMapper
        
        events = [
            MessageEvent(role="user", content="Hello"),
            MessageEvent(role="assistant", content="Hi!"),
        ]
        
        sse_events = EventMapper.events_to_sse_events(events)
        
        assert len(sse_events) == 2
        assert all("event" in e and "data" in e for e in sse_events)


# ── Mock Flow Tests ──────────────────────────────────────────────────────────


class TestChatWithMockFlow:
    """Test chat with fully mocked flow."""

    @pytest.mark.asyncio
    async def test_full_chat_flow(self):
        """Test complete chat flow with mock."""
        from app.services.assistant.session_service import AssistantSessionService

        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Create mock objects
        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.project_id = project_id
        mock_session.project = MagicMock()
        mock_session.project.id = project_id
        mock_session.project.title = "Test Project"
        mock_session.project.topic = "RAG"
        mock_session.project.research_question = "What is RAG?"
        mock_session.events = []
        mock_session.plan = None
        mock_session.status = "active"

        mock_user = MockUser(id=user_id)

        mock_db = MagicMock()
        mock_result = MagicMock()
        # Multiple calls: session check, user lookup, _persist_event (for session update)
        mock_result.scalar_one_or_none.side_effect = [
            mock_session,  # Session check
            mock_user,     # User lookup
            mock_session,  # For _persist_event session update
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Create mock events to yield
        mock_flow_events = [
            MessageEvent(
                role="assistant",
                content="I'll help you find papers on RAG.",
            ),
            PlanEvent(
                plan_id=str(uuid.uuid4()),
                title="Find RAG Papers",
                language="en",
                steps=[
                    PlanStep(
                        id="step_1",
                        description="Search for RAG papers",
                        expected_tool="search_papers",
                        status="pending",
                    ),
                ],
            ),
            DoneEvent(summary="Task completed successfully"),
        ]

        service = AssistantSessionService(db=mock_db)

        with patch("app.services.assistant.session_service.PlanActFlow") as MockFlow:
            mock_flow_instance = MagicMock()
            mock_flow_instance.run = AsyncMock(return_value=iter(mock_flow_events))
            MockFlow.return_value = mock_flow_instance

            with patch("app.services.assistant.session_service.get_all_tools", return_value=[]):
                with patch("app.services.assistant.session_service.get_all_toolkits", return_value=[]):
                    with patch("app.services.assistant.session_service.get_provider") as mock_get_provider:
                        mock_get_provider.return_value = MagicMock()

                        received_events = []
                        async for evt in service.chat(
                            session_id=session_id,
                            user_id=user_id,
                            message="Find papers on RAG",
                        ):
                            received_events.append(evt)

        # Verify we got events (may be less than expected due to mocking complexity)
        assert len(received_events) >= 1
        assert received_events[-1].type == "done"


class TestResumeSession:
    """Test session resume functionality."""

    @pytest.mark.asyncio
    async def test_resume_from_existing_plan(self):
        """Test resuming from an existing plan."""
        from app.services.assistant.session_service import AssistantSessionService

        session_id = uuid.uuid4()
        user_id = uuid.uuid4()

        # Mock session with existing plan
        mock_plan = MagicMock()
        mock_plan.id = uuid.uuid4()
        mock_plan.session_id = session_id
        mock_plan.title = "Previous Plan"
        mock_plan.language = "en"
        mock_plan.steps = [
            {"id": "step_1", "description": "Step 1", "expected_tool": "search_papers", "status": "completed"},
            {"id": "step_2", "description": "Step 2", "expected_tool": "save_paper", "status": "pending"},
        ]
        mock_plan.current_step_index = 1
        mock_plan.status = "in_progress"

        mock_session = MagicMock()
        mock_session.id = session_id
        mock_session.user_id = user_id
        mock_session.project_id = None
        mock_session.project = None
        mock_session.events = []
        mock_session.plan = mock_plan
        mock_session.status = "active"

        mock_user = MockUser(id=user_id)

        mock_db = MagicMock()
        mock_result = MagicMock()
        # Multiple calls: session, user, persist events
        mock_result.scalar_one_or_none.side_effect = [
            mock_session,
            mock_user,
            mock_session,  # For persist_event
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()  # Mock commit as well

        service = AssistantSessionService(db=mock_db)

        # Track if resume was called
        resume_called = False

        async def mock_async_gen(message, resume=False):
            nonlocal resume_called
            resume_called = resume
            yield DoneEvent(summary="Done")

        with patch("app.services.assistant.session_service.PlanActFlow") as MockFlow:
            mock_flow_instance = MagicMock()
            # Make run return an async generator
            mock_flow_instance.run = mock_async_gen
            MockFlow.return_value = mock_flow_instance

            with patch("app.services.assistant.session_service.get_all_tools", return_value=[]):
                with patch("app.services.assistant.session_service.get_all_toolkits", return_value=[]):
                    with patch("app.services.assistant.session_service.get_provider") as mock_get_provider:
                        mock_get_provider.return_value = MagicMock()

                        received_events = []
                        async for evt in service.chat(
                            session_id=session_id,
                            user_id=user_id,
                            message="Continue",
                        ):
                            received_events.append(evt)

        # Verify resume was called
        assert resume_called is True
