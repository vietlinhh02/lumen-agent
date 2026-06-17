"""
Tests for assistant event schemas.

Verifies:
- Serialization round-trip (event -> JSON -> event)
- Type discrimination via Pydantic Union parsing
- EventMapper.event_to_sse_event() returns correct shape
- All events have required fields
"""

import json
from datetime import UTC, datetime

import pytest

from app.agents.assistant.event_mapper import EventMapper
from app.agents.assistant.events import (
    AssistantEvent,
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
    StepEvent,
    TitleEvent,
    ToolEvent,
    WaitEvent,
)


class TestMessageEvent:
    """Tests for MessageEvent."""

    def test_create_message_event(self):
        """Can create a MessageEvent with required fields."""
        event = MessageEvent(role="user", content="Hello, assistant!")
        assert event.role == "user"
        assert event.content == "Hello, assistant!"
        assert event.type == "message"
        assert event.id  # auto-generated
        assert isinstance(event.timestamp, datetime)

    def test_message_event_serialization_roundtrip(self):
        """MessageEvent serializes and deserializes correctly."""
        original = MessageEvent(role="assistant", content="Here are your papers.")
        json_str = original.model_dump_json()
        restored = MessageEvent.model_validate_json(json_str)
        assert restored.id == original.id
        assert restored.role == original.role
        assert restored.content == original.content
        assert restored.type == original.type

    def test_message_event_with_attachments(self):
        """MessageEvent can include attachments."""
        attachments = [{"name": "paper.pdf", "type": "application/pdf"}]
        event = MessageEvent(
            role="user",
            content="Here's a paper",
            attachments=attachments,
        )
        assert event.attachments == attachments
        json_str = event.model_dump_json()
        restored = MessageEvent.model_validate_json(json_str)
        assert restored.attachments == attachments


class TestTitleEvent:
    """Tests for TitleEvent."""

    def test_create_title_event(self):
        """Can create a TitleEvent."""
        event = TitleEvent(title="RAG Research Session")
        assert event.title == "RAG Research Session"
        assert event.type == "title"

    def test_title_event_roundtrip(self):
        """TitleEvent serializes and deserializes correctly."""
        original = TitleEvent(title="My Research")
        json_str = original.model_dump_json()
        restored = TitleEvent.model_validate_json(json_str)
        assert restored.title == original.title


class TestPlanEvent:
    """Tests for PlanEvent."""

    def test_create_plan_event(self):
        """Can create a PlanEvent with steps."""
        steps = [
            PlanStep(
                id="step-1",
                description="Search for papers",
                expected_tool="search_papers",
            ),
            PlanStep(
                id="step-2",
                description="Save papers to project",
                expected_tool="save_paper_to_project",
            ),
        ]
        event = PlanEvent(
            plan_id="plan-123",
            title="Research Plan",
            language="en",
            steps=steps,
        )
        assert event.plan_id == "plan-123"
        assert event.title == "Research Plan"
        assert len(event.steps) == 2
        assert event.steps[0].expected_tool == "search_papers"

    def test_plan_event_from_steps_factory(self):
        """PlanEvent.from_steps creates event correctly."""
        steps = [
            PlanStep(id="s1", description="Do thing", expected_tool="tool_a"),
        ]
        event = PlanEvent.from_steps(
            plan_id="p-1",
            title="Test Plan",
            language="en",
            steps=steps,
        )
        assert event.plan_id == "p-1"
        assert event.language == "en"

    def test_plan_event_roundtrip(self):
        """PlanEvent serializes and deserializes correctly."""
        steps = [
            PlanStep(
                id="step-1",
                description="Search papers",
                expected_tool="search_papers",
            ),
        ]
        original = PlanEvent(
            plan_id="plan-456",
            title="Paper Search",
            steps=steps,
        )
        json_str = original.model_dump_json()
        restored = PlanEvent.model_validate_json(json_str)
        assert restored.plan_id == original.plan_id
        assert len(restored.steps) == 1


class TestStepEvent:
    """Tests for StepEvent."""

    def test_create_step_event(self):
        """Can create a StepEvent."""
        event = StepEvent(
            step_id="step-1",
            description="Running search",
            status="running",
        )
        assert event.step_id == "step-1"
        assert event.status == "running"

    def test_step_event_statuses(self):
        """StepEvent accepts all valid statuses."""
        for status in ["pending", "running", "completed", "failed"]:
            event = StepEvent(
                step_id=f"step-{status}",
                description=f"Step {status}",
                status=status,
            )
            assert event.status == status


class TestToolEvent:
    """Tests for ToolEvent."""

    def test_create_tool_event_calling(self):
        """Can create a ToolEvent for tool call."""
        event = ToolEvent(
            tool_call_id="call-123",
            name="search_papers",
            status="calling",
            function="search_papers",
            args={"query": "RAG", "limit": 10},
        )
        assert event.status == "calling"
        assert event.args["query"] == "RAG"

    def test_tool_event_called_status(self):
        """ToolEvent with called status includes result."""
        event = ToolEvent(
            tool_call_id="call-456",
            name="search_papers",
            status="called",
            function="search_papers",
            args={},
            result={"papers": [{"id": "p1"}]},
        )
        assert event.status == "called"
        assert event.result == {"papers": [{"id": "p1"}]}

    def test_tool_event_failed_status(self):
        """ToolEvent with failed status includes error."""
        event = ToolEvent(
            tool_call_id="call-789",
            name="search_papers",
            status="failed",
            function="search_papers",
            args={},
            error="API rate limit exceeded",
        )
        assert event.status == "failed"
        assert event.error == "API rate limit exceeded"

    def test_tool_event_roundtrip(self):
        """ToolEvent serializes and deserializes correctly."""
        original = ToolEvent(
            tool_call_id="call-abc",
            name="save_paper",
            status="called",
            function="save_paper_to_project",
            args={"project_id": "proj-1"},
            result={"saved": True},
        )
        json_str = original.model_dump_json()
        restored = ToolEvent.model_validate_json(json_str)
        assert restored.tool_call_id == original.tool_call_id
        assert restored.result == original.result


class TestDoneEvent:
    """Tests for DoneEvent."""

    def test_create_done_event(self):
        """Can create a DoneEvent."""
        event = DoneEvent()
        assert event.type == "done"

    def test_done_event_with_summary(self):
        """DoneEvent can include a summary."""
        event = DoneEvent(summary="Found 5 papers and generated matrix.")
        assert event.summary == "Found 5 papers and generated matrix."

    def test_done_event_roundtrip(self):
        """DoneEvent serializes and deserializes correctly."""
        original = DoneEvent(summary="All done!")
        json_str = original.model_dump_json()
        restored = DoneEvent.model_validate_json(json_str)
        assert restored.summary == original.summary


class TestErrorEvent:
    """Tests for ErrorEvent."""

    def test_create_error_event(self):
        """Can create an ErrorEvent."""
        event = ErrorEvent(
            code="PROJECT_NOT_FOUND",
            message="Project with ID xyz not found.",
        )
        assert event.code == "PROJECT_NOT_FOUND"
        assert event.message == "Project with ID xyz not found."
        assert event.type == "error"

    def test_error_event_with_details(self):
        """ErrorEvent can include details."""
        details = {"project_id": "xyz", "user_id": "user-1"}
        event = ErrorEvent(
            code="NOT_FOUND",
            message="Resource not found",
            details=details,
        )
        assert event.details == details

    def test_error_event_roundtrip(self):
        """ErrorEvent serializes and deserializes correctly."""
        original = ErrorEvent(
            code="RATE_LIMIT",
            message="Too many requests",
            details={"retry_after": 60},
        )
        json_str = original.model_dump_json()
        restored = ErrorEvent.model_validate_json(json_str)
        assert restored.code == original.code
        assert restored.details == original.details


class TestWaitEvent:
    """Tests for WaitEvent."""

    def test_create_wait_event(self):
        """Can create a WaitEvent."""
        event = WaitEvent(question="Which project should I use?")
        assert event.question == "Which project should I use?"
        assert event.type == "wait"

    def test_wait_event_with_options(self):
        """WaitEvent can include multiple choice options."""
        options = ["Project A", "Project B", "Create new"]
        event = WaitEvent(
            question="Select a project",
            options=options,
            placeholder="Select project...",
        )
        assert event.options == options
        assert event.placeholder == "Select project..."

    def test_wait_event_roundtrip(self):
        """WaitEvent serializes and deserializes correctly."""
        original = WaitEvent(
            question="Which papers to include?",
            options=["All", "Recent 5", "Selected"],
        )
        json_str = original.model_dump_json()
        restored = WaitEvent.model_validate_json(json_str)
        assert restored.question == original.question
        assert restored.options == original.options


class TestEventMapper:
    """Tests for EventMapper."""

    def test_event_to_sse_event_message(self):
        """event_to_sse_event returns correct shape for MessageEvent."""
        event = MessageEvent(role="user", content="Test message")
        result = EventMapper.event_to_sse_event(event)
        assert "event" in result
        assert "data" in result
        assert result["event"] == "message"
        assert result["data"]["type"] == "message"
        assert result["data"]["role"] == "user"
        assert result["data"]["content"] == "Test message"
        assert "id" in result["data"]
        assert "timestamp" in result["data"]

    def test_event_to_sse_event_plan(self):
        """event_to_sse_event returns correct shape for PlanEvent."""
        steps = [
            PlanStep(id="s1", description="Do thing", expected_tool="tool"),
        ]
        event = PlanEvent(plan_id="p-1", title="Plan", steps=steps)
        result = EventMapper.event_to_sse_event(event)
        assert result["event"] == "plan"
        assert result["data"]["type"] == "plan"
        assert result["data"]["plan_id"] == "p-1"
        assert len(result["data"]["steps"]) == 1

    def test_event_to_sse_event_done(self):
        """event_to_sse_event returns correct shape for DoneEvent."""
        event = DoneEvent(summary="Done!")
        result = EventMapper.event_to_sse_event(event)
        assert result["event"] == "done"
        assert result["data"]["type"] == "done"
        assert result["data"]["summary"] == "Done!"

    def test_event_to_sse_event_error(self):
        """event_to_sse_event returns correct shape for ErrorEvent."""
        event = ErrorEvent(code="ERR", message="Something went wrong")
        result = EventMapper.event_to_sse_event(event)
        assert result["event"] == "error"
        assert result["data"]["type"] == "error"
        assert result["data"]["code"] == "ERR"

    def test_event_to_sse_event_tool(self):
        """event_to_sse_event returns correct shape for ToolEvent."""
        event = ToolEvent(
            tool_call_id="c1",
            name="search",
            status="calling",
            function="search",
            args={"q": "test"},
        )
        result = EventMapper.event_to_sse_event(event)
        assert result["event"] == "tool"
        assert result["data"]["type"] == "tool"
        assert result["data"]["tool_call_id"] == "c1"
        assert result["data"]["status"] == "calling"

    def test_events_to_sse_events(self):
        """events_to_sse_events converts list correctly."""
        events = [
            MessageEvent(role="user", content="Hi"),
            MessageEvent(role="assistant", content="Hello!"),
        ]
        results = EventMapper.events_to_sse_events(events)
        assert len(results) == 2
        assert all("event" in r and "data" in r for r in results)

    def test_parse_event_message(self):
        """parse_event reconstructs MessageEvent correctly."""
        data = {
            "id": "evt-123",
            "timestamp": datetime.now(UTC).isoformat(),
            "role": "assistant",
            "content": "Response",
            "type": "message",
        }
        event = EventMapper.parse_event("message", data)
        assert isinstance(event, MessageEvent)
        assert event.role == "assistant"
        assert event.content == "Response"

    def test_parse_event_plan(self):
        """parse_event reconstructs PlanEvent correctly."""
        data = {
            "id": "evt-456",
            "timestamp": datetime.now(UTC).isoformat(),
            "plan_id": "plan-1",
            "title": "My Plan",
            "language": "en",
            "steps": [
                {"id": "s1", "description": "Step 1", "expected_tool": "tool_a"}
            ],
            "type": "plan",
        }
        event = EventMapper.parse_event("plan", data)
        assert isinstance(event, PlanEvent)
        assert event.plan_id == "plan-1"
        assert len(event.steps) == 1

    def test_parse_event_unknown_type_raises(self):
        """parse_event raises ValueError for unknown event type."""
        with pytest.raises(ValueError, match="Unknown event type"):
            EventMapper.parse_event("unknown_type", {})

    def test_validate_event_success(self):
        """validate_event returns True for valid event."""
        event = MessageEvent(role="user", content="Test")
        assert EventMapper.validate_event(event) is True

    def test_validate_event_empty_type_raises(self):
        """validate_event raises for empty type."""
        event = MessageEvent(role="user", content="Test")
        event.type = ""
        with pytest.raises(ValueError, match="type cannot be empty"):
            EventMapper.validate_event(event)

    def test_validate_event_unknown_type_raises(self):
        """validate_event raises for unknown type."""
        event = MessageEvent(role="user", content="Test")
        event.type = "unknown"
        with pytest.raises(ValueError, match="Unknown event type"):
            EventMapper.validate_event(event)


class TestEventDiscrimination:
    """Tests for Pydantic Union type discrimination."""

    def test_discriminate_message_event(self):
        """Can discriminate a MessageEvent from Union."""
        events: list[AssistantEvent] = [
            MessageEvent(role="user", content="Hi"),
            MessageEvent(role="assistant", content="Hello"),
        ]
        for event in events:
            assert event.type == "message"
            assert isinstance(event, MessageEvent)

    def test_discriminate_all_event_types(self):
        """All event types can be properly discriminated."""
        events: list[AssistantEvent] = [
            MessageEvent(role="user", content="Hi"),
            TitleEvent(title="Session"),
            PlanEvent(plan_id="p1", title="Plan", steps=[]),
            StepEvent(step_id="s1", description="Step", status="running"),
            ToolEvent(
                tool_call_id="c1",
                name="tool",
                status="calling",
                function="tool",
                args={},
            ),
            DoneEvent(),
            ErrorEvent(code="E", message="Error"),
            WaitEvent(question="What?"),
        ]
        assert len(events) == 8
        types = {e.type for e in events}
        assert types == {
            "message",
            "title",
            "plan",
            "step",
            "tool",
            "done",
            "error",
            "wait",
        }


class TestEventSerialization:
    """Tests for JSON serialization behavior."""

    def test_timestamp_isostring_in_json(self):
        """Timestamp is serialized as ISO-8601 string in JSON."""
        event = MessageEvent(role="user", content="Test")
        json_str = event.model_dump_json()
        data = json.loads(json_str)
        # Timestamp should be ISO format string, not a number
        assert isinstance(data["timestamp"], str)
        assert "T" in data["timestamp"]  # ISO format contains 'T'

    def test_nested_plan_steps_serialize(self):
        """Nested PlanSteps serialize correctly."""
        steps = [
            PlanStep(id="s1", description="Step 1", expected_tool="tool_a"),
            PlanStep(id="s2", description="Step 2", expected_tool="tool_b"),
        ]
        event = PlanEvent(plan_id="p1", title="Plan", steps=steps)
        json_str = event.model_dump_json()
        data = json.loads(json_str)
        assert len(data["steps"]) == 2
        assert data["steps"][0]["id"] == "s1"

    def test_include_type_in_data_for_client_dispatch(self):
        """The frontend dispatches SSE payloads by the data.type discriminator."""
        event = MessageEvent(role="user", content="Test")
        result = EventMapper.event_to_sse_event(event)
        assert result["event"] == "message"
        assert result["data"]["type"] == "message"
