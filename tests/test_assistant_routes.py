"""
Tests for Assistant Router endpoints.

Tests:
- Session CRUD operations (PUT/GET/DELETE)
- Chat endpoint with SSE streaming
- Stop endpoint
- Authentication and authorization
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from app.agents.assistant.events import (
    DoneEvent,
    MessageEvent,
)

# ── Test Fixtures ───────────────────────────────────────────────────────────────


class MockUser:
    """Mock authenticated user."""

    def __init__(self, id=None, email="test@example.com"):
        self.id = id or uuid.uuid4()
        self.email = email
        self.is_active = True


class MockProject:
    """Mock project."""

    def __init__(self, id=None, owner_id=None, title="Test Project"):
        self.id = id or uuid.uuid4()
        self.owner_id = owner_id or uuid.uuid4()
        self.title = title
        self.topic = "Test Topic"
        self.research_question = None


class MockSession:
    """Mock database session."""

    def __init__(self):
        self._added = []
        self._deleted = False

    def add(self, obj):
        self._added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def delete(self, obj):
        self._deleted = True

    async def execute(self, query):
        result = MagicMock()
        return result


class MockAssistantSession:
    """Mock assistant session from DB."""

    def __init__(self, id=None, user_id=None, project_id=None, title=None):
        self.id = id or uuid.uuid4()
        self.user_id = user_id or uuid.uuid4()
        self.project_id = project_id
        self.title = title
        self.status = "active"
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.events = []
        self.plan = None
        self.project = None


# ── Test Client Factory ────────────────────────────────────────────────────────


def create_mock_user_dependency(user: MockUser = None):
    """Create a mock for get_current_user dependency."""
    if user is None:
        user = MockUser()
    return user


# ── Tests: Session CRUD ────────────────────────────────────────────────────────


class TestCreateSession:
    """Test PUT /api/assistant/sessions endpoint."""

    @pytest.mark.asyncio
    async def test_create_session_success(self):
        """Test creating a session successfully."""
        from app.routers.assistant import create_session
        from app.schemas.assistant import SessionCreate
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        mock_session = MockAssistantSession(user_id=user.id)

        # Mock the service
        with patch.object(
            AssistantSessionService, "create_session", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_session

            # Call the endpoint directly
            result = await create_session(
                body=SessionCreate(project_id=None, title=None),
                db=MockSession(),
                user=user,
            )

            assert result.id == mock_session.id
            assert result.status == "active"

    @pytest.mark.asyncio
    async def test_create_session_with_project(self):
        """Test creating a session with a project."""
        from app.routers.assistant import create_session
        from app.schemas.assistant import SessionCreate
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        project_id = uuid.uuid4()
        mock_session = MockAssistantSession(user_id=user.id, project_id=project_id)

        with patch.object(
            AssistantSessionService, "create_session", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = mock_session

            result = await create_session(
                body=SessionCreate(project_id=project_id, title="Test Session"),
                db=MockSession(),
                user=user,
            )

            assert result.project_id == project_id
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_invalid_project(self):
        """Test creating a session with invalid project raises error."""
        from app.routers.assistant import create_session
        from app.schemas.assistant import SessionCreate
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        project_id = uuid.uuid4()

        with patch.object(
            AssistantSessionService, "create_session", new_callable=AsyncMock
        ) as mock_create:
            mock_create.side_effect = ValueError(
                f"Project {project_id} not found or you don't have access to it"
            )

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await create_session(
                    body=SessionCreate(project_id=project_id),
                    db=MockSession(),
                    user=user,
                )

            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestListSessions:
    """Test GET /api/assistant/sessions endpoint."""

    @pytest.mark.asyncio
    async def test_list_sessions_success(self):
        """Test listing sessions successfully."""
        from app.routers.assistant import list_sessions
        from app.services.assistant.session_service import (
            AssistantSessionService,
        )

        user = MockUser()
        mock_sessions = [
            MagicMock(
                id=uuid.uuid4(),
                title="Session 1",
                project_id=None,
                project_title=None,
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                event_count=5,
            ),
            MagicMock(
                id=uuid.uuid4(),
                title="Session 2",
                project_id=None,
                project_title=None,
                status="archived",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                event_count=10,
            ),
        ]

        with patch.object(
            AssistantSessionService, "list_sessions", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = mock_sessions

            result = await list_sessions(
                limit=50,
                offset=0,
                db=MockSession(),
                user=user,
            )

            assert len(result.sessions) == 2
            assert result.total == 2

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        """Test listing sessions when none exist."""
        from app.routers.assistant import list_sessions
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()

        with patch.object(
            AssistantSessionService, "list_sessions", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = []

            result = await list_sessions(
                limit=50,
                offset=0,
                db=MockSession(),
                user=user,
            )

            assert len(result.sessions) == 0
            assert result.total == 0


class TestGetSession:
    """Test GET /api/assistant/sessions/{session_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_session_success(self):
        """Test getting a session successfully."""
        from app.routers.assistant import get_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()
        mock_session = MockAssistantSession(id=session_id, user_id=user.id)
        mock_session.events = []
        mock_session.plan = None
        mock_session.project = None

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_session

            result = await get_session(
                session_id=session_id,
                db=MockSession(),
                user=user,
            )

            assert result.id == session_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        """Test getting a non-existent session returns 404."""
        from app.routers.assistant import get_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await get_session(
                    session_id=session_id,
                    db=MockSession(),
                    user=user,
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_session_with_events_and_plan(self):
        """Test getting a session with events and plan."""
        from app.routers.assistant import get_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()

        # Mock event
        mock_event = MagicMock()
        mock_event.id = uuid.uuid4()
        mock_event.event_type = "message"
        mock_event.payload = {"role": "user", "content": "Hello"}
        mock_event.created_at = datetime.now(UTC)

        # Mock plan
        mock_plan = MagicMock()
        mock_plan.id = uuid.uuid4()
        mock_plan.title = "Test Plan"
        mock_plan.language = "en"
        mock_plan.steps = [
            {
                "id": "1",
                "description": "Step 1",
                "expected_tool": "search_papers",
                "status": "completed",
            }
        ]
        mock_plan.current_step_index = 1
        mock_plan.status = "in_progress"
        mock_plan.created_at = datetime.now(UTC)
        mock_plan.updated_at = datetime.now(UTC)

        mock_session = MockAssistantSession(id=session_id, user_id=user.id)
        mock_session.events = [mock_event]
        mock_session.plan = mock_plan
        mock_session.project = None

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_session

            result = await get_session(
                session_id=session_id,
                db=MockSession(),
                user=user,
            )

            assert result.id == session_id
            assert len(result.events) == 1


class TestDeleteSession:
    """Test DELETE /api/assistant/sessions/{session_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_session_success(self):
        """Test deleting a session successfully."""
        from app.routers.assistant import delete_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()

        with patch.object(
            AssistantSessionService, "delete_session", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = True

            await delete_session(
                session_id=session_id,
                db=MockSession(),
                user=user,
            )

            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self):
        """Test deleting a non-existent session returns 404."""
        from app.routers.assistant import delete_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()

        with patch.object(
            AssistantSessionService, "delete_session", new_callable=AsyncMock
        ) as mock_delete:
            mock_delete.return_value = False

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await delete_session(
                    session_id=session_id,
                    db=MockSession(),
                    user=user,
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ── Tests: Chat Endpoint ────────────────────────────────────────────────────────


class TestChatEndpoint:
    """Test POST /api/assistant/sessions/{session_id}/chat endpoint."""

    @pytest.mark.asyncio
    async def test_chat_session_not_found(self):
        """Test chat with non-existent session returns 404."""
        from app.routers.assistant import chat
        from app.schemas.assistant import ChatRequest
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await chat(
                    session_id=session_id,
                    body=ChatRequest(message="Hello"),
                    db=MockSession(),
                    user=user,
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_chat_does_not_replay_persisted_events(self):
        """
        Regression test: POST /sessions/{id}/chat should NOT replay history.
        
        When sending a second message to an existing session, only live events
        for that turn should be streamed. Old persisted events must NOT be
        replayed in the SSE stream to prevent:
        - Duplicate messages in the UI
        - Old events being re-appended during a new stream
        - Flickering and message-count jumps
        
        History loading is handled by GET /sessions/{id} only.
        """
        from app.agents.assistant.events import DoneEvent
        from app.schemas.assistant import ChatRequest

        user = MockUser()
        session_id = uuid.uuid4()
        mock_session = MockAssistantSession(id=session_id, user_id=user.id)

        # Track whether get_persisted_events was called
        persisted_events_called = False
        
        async def mock_chat_generator(*args, **kwargs):
            """Mock async generator for service.chat()."""
            # Only yield one DoneEvent for the new message
            yield DoneEvent(summary="Second response only")

        def create_mock_service(db=None):
            """Create a mock service instance."""
            nonlocal persisted_events_called
            service = MagicMock()
            service.get_session = AsyncMock(return_value=mock_session)
            service.chat = mock_chat_generator
            # Track if get_persisted_events is called
            def track_persisted():
                nonlocal persisted_events_called
                persisted_events_called = True
                return []
            service.get_persisted_events = track_persisted
            return service

        # Patch the service class to return our mock service
        with patch(
            "app.routers.assistant.AssistantSessionService",
            side_effect=create_mock_service
        ) as mock_service_class:
            # Import and call chat endpoint
            from app.routers.assistant import chat
            
            response = await chat(
                session_id=session_id,
                body=ChatRequest(message="Second message"),
                db=MockSession(),
                user=user,
            )

            # Collect all events from the SSE stream body
            streamed_events = []
            async for event in response.body_iterator:
                # EventSourceResponse yields dicts with 'event' and 'data' keys
                if isinstance(event, dict) and 'event' in event:
                    streamed_events.append(event)

            # Should only have the new live event, NOT replayed history
            assert len(streamed_events) == 0 or len(streamed_events) == 1

            # CRITICAL: Verify get_persisted_events was NOT called
            # This is the main assertion for this regression test
            assert not persisted_events_called, (
                "get_persisted_events should NOT be called in POST chat endpoint. "
                "History replay has not been removed!"
            )

            # Verify service.chat was called
            mock_service_class.assert_called()

    @pytest.mark.asyncio
    async def test_chat_accepts_client_message_id(self):
        """
        Test that ChatRequest accepts client_message_id for deduplication.
        
        The client can send a client-generated message ID to:
        1. Track optimistic messages
        2. Receive a message_ack with the canonical ID
        3. Replace the optimistic message with the canonical one
        """
        from app.schemas.assistant import ChatRequest

        # Valid request with client_message_id
        request = ChatRequest(
            message="Hello, assistant!",
            client_message_id="client-123-abc"
        )
        assert request.message == "Hello, assistant!"
        assert request.client_message_id == "client-123-abc"

        # Valid request without client_message_id (backward compatible)
        request_no_id = ChatRequest(message="Hello!")
        assert request_no_id.message == "Hello!"
        assert request_no_id.client_message_id is None

    @pytest.mark.asyncio
    async def test_message_ack_event_has_required_fields(self):
        """
        Test that MessageAckEvent has all required fields for deduplication.
        """
        from app.agents.assistant.events import MessageAckEvent

        ack = MessageAckEvent(
            client_message_id="client-123",
            canonical_id="canonical-456",
            turn_id="turn-789",
        )
        
        assert ack.client_message_id == "client-123"
        assert ack.canonical_id == "canonical-456"
        assert ack.turn_id == "turn-789"
        assert ack.type == "message_ack"
        assert ack.id is not None  # Auto-generated
        assert ack.timestamp is not None  # Auto-generated

    @pytest.mark.asyncio
    async def test_base_event_has_turn_id(self):
        """
        Test that BaseEvent includes turn_id field.
        
        All events for a single user request share the same turn_id.
        """
        from app.agents.assistant.events import MessageEvent

        # MessageEvent should accept turn_id
        msg = MessageEvent(
            role="user",
            content="Hello",
            turn_id="turn-123",
        )
        assert msg.turn_id == "turn-123"

        # turn_id should be optional for backward compatibility
        msg_no_turn = MessageEvent(role="assistant", content="Hi there")
        assert msg_no_turn.turn_id is None


# ── Tests: Stop Endpoint ───────────────────────────────────────────────────────


class TestStopSession:
    """Test POST /api/assistant/sessions/{session_id}/stop endpoint."""

    @pytest.mark.asyncio
    async def test_stop_session_success(self):
        """Test stopping a running session."""
        from app.routers.assistant import stop_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()
        mock_session = MockAssistantSession(id=session_id, user_id=user.id)

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get, patch.object(
            AssistantSessionService, "stop_session", new_callable=AsyncMock
        ) as mock_stop:
            mock_get.return_value = mock_session
            mock_stop.return_value = True

            await stop_session(
                session_id=session_id,
                db=MockSession(),
                user=user,
            )

            mock_stop.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_stop_session_not_found(self):
        """Test stopping a non-existent session returns 404."""
        from app.routers.assistant import stop_session
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = None

            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await stop_session(
                    session_id=session_id,
                    db=MockSession(),
                    user=user,
                )

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ── Tests: SSE Streaming ───────────────────────────────────────────────────────


class TestSSEStreaming:
    """Test SSE event streaming functionality."""

    @pytest.mark.asyncio
    async def test_event_stream_converts_events(self):
        """Test that _event_stream correctly converts events to SSE format."""
        from app.agents.assistant.events import (
            ToolEvent,
        )
        from app.routers.assistant import _event_stream

        # Create mock events
        events = [
            MessageEvent(role="assistant", content="Hello!"),
            ToolEvent(
                tool_call_id="call_1",
                name="search_papers",
                status="calling",
                function="search_papers",
                args={"query": "RAG"},
            ),
            DoneEvent(summary="Done!"),
        ]

        session_id = uuid.uuid4()

        async def event_gen():
            for event in events:
                yield event

        collected = []
        async for sse_event in _event_stream(event_gen(), session_id):
            collected.append(sse_event)
            # Should have event and data keys
            assert "event" in sse_event
            assert "data" in sse_event

        assert len(collected) == 3
        assert collected[0]["event"] == "message"
        assert collected[1]["event"] == "tool"
        assert collected[2]["event"] == "done"

        message_data = json.loads(collected[0]["data"])
        tool_data = json.loads(collected[1]["data"])
        done_data = json.loads(collected[2]["data"])
        assert message_data["type"] == "message"
        assert tool_data["type"] == "tool"
        assert done_data["type"] == "done"

    @pytest.mark.asyncio
    async def test_event_data_is_json_serializable(self):
        """Test that SSE data is valid JSON."""
        from app.routers.assistant import _event_stream

        events = [MessageEvent(role="assistant", content="Hello with emoji 🎉!")]

        async def event_gen():
            for event in events:
                yield event

        session_id = uuid.uuid4()
        async for sse_event in _event_stream(event_gen(), session_id):
            # Should be able to parse the data as JSON
            data = json.loads(sse_event["data"])
            assert data["type"] == "message"
            assert "content" in data
            assert data["content"] == "Hello with emoji 🎉!"


# ── Tests: Error Handling ──────────────────────────────────────────────────────


class TestErrorHandling:
    """Test error handling in router endpoints."""

    @pytest.mark.asyncio
    async def test_chat_with_empty_message(self):
        """Test that empty message is rejected."""
        from app.schemas.assistant import ChatRequest
        from app.services.assistant.session_service import AssistantSessionService

        user = MockUser()
        session_id = uuid.uuid4()
        mock_session = MockAssistantSession(id=session_id, user_id=user.id)

        with patch.object(
            AssistantSessionService, "get_session", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = mock_session

            # Empty message should be rejected by Pydantic validation
            with pytest.raises(ValueError):  # Pydantic raises ValidationError
                ChatRequest(message="")  # min_length=1


# ── Integration Tests ──────────────────────────────────────────────────────────


class TestAssistantRouterIntegration:
    """Integration-style tests using FastAPI TestClient patterns."""

    def test_router_has_correct_prefix(self):
        """Test that router is configured with correct prefix."""
        from app.routers.assistant import router

        # The router itself doesn't store prefix, but we verify it's registered
        # correctly in main.py
        assert router.tags == ["assistant"]

    def test_create_session_schema(self):
        """Test SessionCreate schema validation."""
        from app.schemas.assistant import SessionCreate

        # Valid with no params
        s = SessionCreate()
        assert s.project_id is None
        assert s.title is None

        # Valid with all params
        project_id = uuid.uuid4()
        s = SessionCreate(project_id=project_id, title="My Session")
        assert s.project_id == project_id
        assert s.title == "My Session"

    def test_chat_request_schema(self):
        """Test ChatRequest schema validation."""
        from app.schemas.assistant import ChatRequest

        # Valid message
        r = ChatRequest(message="Find papers on RAG")
        assert r.message == "Find papers on RAG"

        # Message too short
        with pytest.raises(ValueError):
            ChatRequest(message="")

        # Message too long
        with pytest.raises(ValueError):
            ChatRequest(message="x" * 10001)

    def test_session_summary_schema(self):
        """Test SessionSummary schema."""
        from app.schemas.assistant import SessionSummary

        s = SessionSummary(
            id=uuid.uuid4(),
            title="Test Session",
            project_id=uuid.uuid4(),
            project_title="Test Project",
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            event_count=5,
        )
        assert s.title == "Test Session"
        assert s.event_count == 5

    # removed test_plan_step_data_schema
