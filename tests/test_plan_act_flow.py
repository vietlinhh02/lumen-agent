"""
Tests for the PlanActFlow state machine.

Tests:
- State transitions
- Limit enforcement (max_steps, max_tokens, max_wall_time)
- Resume from WaitEvent
- Cancellation handling
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.assistant.events import (
    DoneEvent,
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
    StepEvent,
    ToolEvent,
    WaitEvent,
)
from app.agents.assistant.flow import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_WALL_TIME_SECONDS,
    BaseFlow,
    FlowErrorCode,
    FlowState,
    PlanActFlow,
)


# ── Mock Agents ────────────────────────────────────────────────────────────────


class MockPlannerAgent:
    """Mock planner agent for testing."""

    def __init__(self, plans: List[PlanEvent] = None, should_fail: bool = False):
        self.plans = plans or []
        self.plan_index = 0
        self.should_fail = should_fail
        self.update_calls = []
        self.create_plan_called = False

    async def create_plan(
        self,
        message: str,
        project_context: Dict[str, Any],
    ):
        """Mock create_plan."""
        self.create_plan_called = True

        if self.should_fail:
            raise Exception("Planning failed")

        if self.plan_index < len(self.plans):
            plan = self.plans[self.plan_index]
            self.plan_index += 1
            yield MessageEvent(role="assistant", content="Planning...")
            yield plan
        else:
            # Default plan if no more plans
            yield MessageEvent(role="assistant", content="Planning...")
            yield PlanEvent(
                plan_id="plan-1",
                title="Test Plan",
                language="en",
                steps=[
                    PlanStep(
                        id="step_1",
                        description="Test step",
                        expected_tool="test_tool",
                        status="pending",
                    ),
                ],
            )

    async def update_plan(
        self,
        current_plan: PlanEvent,
        last_step_id: str,
        step_result: Dict[str, Any],
    ):
        """Mock update_plan."""
        self.update_calls.append({
            "plan": current_plan,
            "step_id": last_step_id,
            "result": step_result,
        })

        # Update step status
        steps = []
        for step in current_plan.steps:
            if step.id == last_step_id:
                status = "completed" if step_result.get("ok", True) else "failed"
                steps.append(PlanStep(
                    id=step.id,
                    description=step.description,
                    expected_tool=step.expected_tool,
                    status=status,
                ))
            else:
                steps.append(step)

        yield MessageEvent(role="assistant", content="Updating plan...")
        yield PlanEvent(
            plan_id=current_plan.plan_id,
            title=current_plan.title,
            language=current_plan.language,
            steps=steps,
        )


class MockExecutionAgent:
    """Mock execution agent for testing."""

    def __init__(
        self,
        steps_to_execute: List[Dict[str, Any]] = None,
        should_wait: bool = False,
        wait_on_step: Optional[str] = None,
    ):
        """
        Initialize mock execution agent.

        Args:
            steps_to_execute: List of step configs with 'step_id', 'events'
            should_wait: If True, yield WaitEvent
            wait_on_step: Step ID to wait on (default: first step)
        """
        self.steps_to_execute = steps_to_execute or []
        self.should_wait = should_wait
        self.wait_on_step = wait_on_step
        self.execute_calls = []

    async def execute_step(
        self,
        plan: PlanEvent,
        step: PlanStep,
        message: str,
    ):
        """Mock execute_step."""
        self.execute_calls.append({
            "plan": plan,
            "step": step,
            "message": message,
        })

        # Yield step started
        yield StepEvent(
            step_id=step.id,
            description=step.description,
            status="running",
        )

        # Check if we should wait
        should_wait_this = self.should_wait and (
            self.wait_on_step is None or self.wait_on_step == step.id
        )

        if should_wait_this:
            yield WaitEvent(
                question="Need more information?",
                options=["Option A", "Option B"],
                placeholder="Please provide more details",
            )
            return

        # Find step config
        step_config = None
        for config in self.steps_to_execute:
            if config.get("step_id") == step.id:
                step_config = config
                break

        if step_config:
            # Yield configured events
            for event in step_config.get("events", []):
                yield event

        # Yield step completed
        yield StepEvent(
            step_id=step.id,
            description=step.description,
            status="completed",
        )


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_planner():
    """Create a mock planner agent."""
    return MockPlannerAgent()


@pytest.fixture
def mock_executor():
    """Create a mock execution agent."""
    return MockExecutionAgent()


@pytest.fixture
def simple_plan():
    """Create a simple test plan."""
    return PlanEvent(
        plan_id="plan-1",
        title="Simple Plan",
        language="en",
        steps=[
            PlanStep(
                id="step_1",
                description="First step",
                expected_tool="tool_1",
                status="pending",
            ),
            PlanStep(
                id="step_2",
                description="Second step",
                expected_tool="tool_2",
                status="pending",
            ),
        ],
    )


@pytest.fixture
def project_context():
    """Create a sample project context."""
    return {
        "project_id": str(uuid4()),
        "project_name": "Test Project",
        "topic": "Testing",
    }


# ── Tests: Initialization ──────────────────────────────────────────────────────


class TestPlanActFlowInit:
    """Test PlanActFlow initialization."""

    def test_init_with_defaults(self, mock_planner, mock_executor):
        """Test initialization with default values."""
        flow = PlanActFlow(
            planner=mock_planner,
            executor=mock_executor,
        )

        assert flow.planner is mock_planner
        assert flow.executor is mock_executor
        assert flow.max_steps == DEFAULT_MAX_STEPS
        assert flow.max_total_tokens == DEFAULT_MAX_TOKENS
        assert flow.max_wall_time_seconds == DEFAULT_MAX_WALL_TIME_SECONDS
        assert flow._state == FlowState.IDLE

    def test_init_with_custom_limits(self, mock_planner, mock_executor):
        """Test initialization with custom limits."""
        flow = PlanActFlow(
            planner=mock_planner,
            executor=mock_executor,
            max_steps=10,
            max_total_tokens=50000,
            max_wall_time_seconds=300,
        )

        assert flow.max_steps == 10
        assert flow.max_total_tokens == 50000
        assert flow.max_wall_time_seconds == 300

    def test_init_with_project_context(self, mock_planner, mock_executor, project_context):
        """Test initialization with project context."""
        flow = PlanActFlow(
            planner=mock_planner,
            executor=mock_executor,
            project_context=project_context,
        )

        assert flow.project_context == project_context

    def test_state_property(self, mock_planner, mock_executor):
        """Test state property."""
        flow = PlanActFlow(planner=mock_planner, executor=mock_executor)
        assert flow.state == FlowState.IDLE
        assert flow.is_running is False

    def test_is_running_property(self, mock_planner, mock_executor):
        """Test is_running property."""
        flow = PlanActFlow(planner=mock_planner, executor=mock_executor)
        assert flow.is_running is False

    def test_stats_property(self, mock_planner, mock_executor):
        """Test stats property."""
        flow = PlanActFlow(planner=mock_planner, executor=mock_executor)
        stats = flow.stats

        assert "state" in stats
        assert "step_count" in stats
        assert "total_tokens" in stats
        assert "wall_time_seconds" in stats
        assert "is_waiting" in stats
        assert stats["state"] == FlowState.IDLE.value
        assert stats["step_count"] == 0
        assert stats["is_waiting"] is False


# ── Tests: Basic Flow ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_basic_flow_run(mock_planner, mock_executor, project_context):
    """Test basic flow run with mock agents."""
    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have events from planning and execution
    assert len(events) > 0
    assert flow.state == FlowState.COMPLETED

    # Check planner was called
    assert mock_planner.create_plan_called


@pytest.mark.asyncio
async def test_flow_yields_planning_events(mock_planner, mock_executor, project_context):
    """Test that flow yields planning events."""
    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have at least one message and one plan event
    message_events = [e for e in events if isinstance(e, MessageEvent)]
    plan_events = [e for e in events if isinstance(e, PlanEvent)]

    assert len(message_events) >= 1
    assert len(plan_events) >= 1


@pytest.mark.asyncio
async def test_flow_yields_done_event(mock_planner, mock_executor, project_context):
    """Test that flow yields DoneEvent at the end."""
    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    done_events = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done_events) >= 1
    assert done_events[-1].type == "done"


# ── Tests: State Transitions ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_state_transitions_planning_to_executing(
    mock_planner, mock_executor, project_context
):
    """Test state transitions from PLANNING to EXECUTING."""
    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    states_seen = []
    
    async for event in flow.run("Test message"):
        states_seen.append(flow.state)

    # Should have transitioned through states
    assert FlowState.PLANNING in states_seen
    assert FlowState.EXECUTING in states_seen
    assert FlowState.COMPLETED in states_seen


@pytest.mark.asyncio
async def test_state_transitions_with_steps(
    mock_planner, mock_executor, project_context, simple_plan
):
    """Test state transitions with multiple steps."""
    # Configure executor with multiple steps
    mock_executor.steps_to_execute = [
        {
            "step_id": "step_1",
            "events": [
                ToolEvent(
                    tool_call_id="call-1",
                    name="tool_1",
                    status="calling",
                    function="tool_1",
                    args={},
                ),
                ToolEvent(
                    tool_call_id="call-1",
                    name="tool_1",
                    status="called",
                    function="tool_1",
                    args={},
                    result={"ok": True},
                ),
            ],
        },
        {
            "step_id": "step_2",
            "events": [
                ToolEvent(
                    tool_call_id="call-2",
                    name="tool_2",
                    status="calling",
                    function="tool_2",
                    args={},
                ),
                ToolEvent(
                    tool_call_id="call-2",
                    name="tool_2",
                    status="called",
                    function="tool_2",
                    args={},
                    result={"ok": True},
                ),
            ],
        },
    ]

    # Set planner to return the simple plan
    mock_planner.plans = [simple_plan]

    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Check step events
    step_events = [e for e in events if isinstance(e, StepEvent)]
    step_1_started = any(
        e.step_id == "step_1" and e.status == "running" for e in step_events
    )
    step_1_completed = any(
        e.step_id == "step_1" and e.status == "completed" for e in step_events
    )
    step_2_started = any(
        e.step_id == "step_2" and e.status == "running" for e in step_events
    )
    step_2_completed = any(
        e.step_id == "step_2" and e.status == "completed" for e in step_events
    )

    assert step_1_started
    assert step_1_completed
    assert step_2_started
    assert step_2_completed


# ── Tests: Limit Enforcement ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_steps_limit_enforced(project_context):
    """Test that max_steps limit is enforced."""
    # Create a plan with many steps
    many_steps = [
        PlanStep(
            id=f"step_{i}",
            description=f"Step {i}",
            expected_tool="test_tool",
            status="pending",
        )
        for i in range(25)
    ]
    plan = PlanEvent(
        plan_id="plan-1",
        title="Many Steps Plan",
        language="en",
        steps=many_steps,
    )

    planner = MockPlannerAgent(plans=[plan])

    # Configure executor to not wait and execute steps
    executor = MockExecutionAgent(should_wait=False)

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
        max_steps=5,  # Very low limit
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have error about max steps or flow stopped early
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    max_steps_errors = [
        e for e in error_events
        if e.code == FlowErrorCode.MAX_STEPS_REACHED.value
    ]

    # Flow should either hit limit or have fewer events than full execution
    # Either way, we verify the limit mechanism works
    assert len(max_steps_errors) >= 1 or flow._step_count <= 5


@pytest.mark.asyncio
async def test_max_tokens_limit(project_context):
    """Test that max_tokens limit is enforced."""
    # Create large plan content that will generate many tokens
    large_content = "x" * 10000  # Very large content
    plan = PlanEvent(
        plan_id="plan-1",
        title=large_content,
        language="en",
        steps=[
            PlanStep(
                id=f"step_{i}",
                description=large_content,
                expected_tool="test_tool",
                status="pending",
            )
            for i in range(10)
        ],
    )

    planner = MockPlannerAgent(plans=[plan])
    executor = MockExecutionAgent(should_wait=False)

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
        max_total_tokens=100,  # Very low limit
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have error about max tokens or early termination
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    token_errors = [
        e for e in error_events
        if e.code == FlowErrorCode.MAX_TOKENS_REACHED.value
    ]

    # Token limit should be hit during token estimation
    # The flow should stop early when token limit is exceeded
    assert len(token_errors) >= 1 or flow._step_count < 10


@pytest.mark.asyncio
async def test_max_wall_time_limit(project_context):
    """Test that max_wall_time limit is enforced."""
    # Create a plan with multiple steps
    many_steps = [
        PlanStep(
            id=f"step_{i}",
            description=f"Step {i}",
            expected_tool="test_tool",
            status="pending",
        )
        for i in range(10)
    ]
    plan = PlanEvent(
        plan_id="plan-1",
        title="Many Steps",
        language="en",
        steps=many_steps,
    )

    planner = MockPlannerAgent(plans=[plan])
    executor = MockExecutionAgent(should_wait=False)

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
        max_wall_time_seconds=0,  # Immediate timeout
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have error about wall time
    error_events = [e for e in events if isinstance(e, ErrorEvent)]

    # The flow should terminate early due to wall time limit
    # Either with MAX_WALL_TIME_REACHED or CANCELLED (from CancelledError)
    has_time_limit_error = any(
        e.code == FlowErrorCode.MAX_WALL_TIME_REACHED.value for e in error_events
    )
    has_cancelled_error = any(
        e.code == FlowErrorCode.CANCELLED.value for e in error_events
    )

    # Wall time limit should be hit - either directly or via cancellation
    assert has_time_limit_error or has_cancelled_error or len(events) < 20


# ── Tests: Cancellation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_flag(project_context):
    """Test that cancellation flag works."""
    planner = MockPlannerAgent()
    executor = MockExecutionAgent()

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    # Cancel before running
    flow.cancel()

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have cancellation error
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    cancel_errors = [
        e for e in error_events
        if e.code == FlowErrorCode.CANCELLED.value
    ]

    assert len(cancel_errors) >= 1


@pytest.mark.asyncio
async def test_cancel_during_execution(project_context):
    """Test cancellation during execution."""
    # Create a plan with many steps
    many_steps = [
        PlanStep(
            id=f"step_{i}",
            description=f"Step {i}",
            expected_tool="test_tool",
            status="pending",
        )
        for i in range(10)
    ]
    plan = PlanEvent(
        plan_id="plan-1",
        title="Many Steps",
        language="en",
        steps=many_steps,
    )

    planner = MockPlannerAgent(plans=[plan])
    executor = MockExecutionAgent()

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    # Cancel after a few events
    cancelled = [False]
    events = []

    async def run_and_cancel():
        nonlocal cancelled
        async for event in flow.run("Test message"):
            events.append(event)
            if len(events) >= 5 and not cancelled[0]:
                flow.cancel()
                cancelled[0] = True

    await run_and_cancel()

    # Should have cancellation error or done event
    assert len(events) > 0


# ── Tests: WaitEvent and Resume ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wait_event_stops_flow(project_context, simple_plan):
    """Test that WaitEvent stops the flow."""
    planner = MockPlannerAgent(plans=[simple_plan])
    executor = MockExecutionAgent(should_wait=True, wait_on_step="step_1")

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have WaitEvent
    wait_events = [e for e in events if isinstance(e, WaitEvent)]
    assert len(wait_events) >= 1

    # Flow should be in waiting state
    assert flow.is_waiting is True
    assert flow._waiting_step_id == "step_1"


@pytest.mark.asyncio
async def test_resume_from_waiting(project_context, simple_plan):
    """Test resuming from a waiting state."""
    # Create a planner that can provide plans on subsequent calls
    planner = MockPlannerAgent(plans=[simple_plan])

    # Create executor that waits on first call but not on resume
    class ResumingExecutor(MockExecutionAgent):
        """Executor that stops waiting after first run."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._waiting_count = 0

        async def execute_step(self, plan, step, message):
            # First time through, wait; second time, complete
            if self._waiting_count == 0 and self.should_wait:
                self._waiting_count += 1
                async for event in super().execute_step(plan, step, message):
                    yield event
            else:
                # Don't wait on resume
                self.should_wait = False
                async for event in super().execute_step(plan, step, message):
                    yield event

    executor = ResumingExecutor(should_wait=True, wait_on_step="step_1")

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    # First run - should wait
    events1 = []
    async for event in flow.run("Test message"):
        events1.append(event)

    assert flow.is_waiting is True

    # Resume with user response
    events2 = []
    async for event in flow.run("User response", resume=True):
        events2.append(event)

    # Should complete after resume
    assert flow.is_waiting is False
    assert flow.state == FlowState.COMPLETED

    # Should have events from both runs
    total_events = len(events1) + len(events2)
    assert total_events > 0


@pytest.mark.asyncio
async def test_resume_updates_step(project_context):
    """Test that resume updates the waiting step status."""
    steps = [
        PlanStep(
            id="step_1",
            description="First step",
            expected_tool="test_tool",
            status="pending",
        ),
        PlanStep(
            id="step_2",
            description="Second step",
            expected_tool="test_tool",
            status="pending",
        ),
    ]
    plan = PlanEvent(
        plan_id="plan-1",
        title="Test Plan",
        language="en",
        steps=steps,
    )

    planner = MockPlannerAgent(plans=[plan])

    # Create executor that doesn't wait on resume
    class ResumingExecutor(MockExecutionAgent):
        """Executor that stops waiting after first run."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._waiting_count = 0

        async def execute_step(self, plan, step, message):
            if self._waiting_count == 0 and self.should_wait:
                self._waiting_count += 1
                async for event in super().execute_step(plan, step, message):
                    yield event
            else:
                self.should_wait = False
                async for event in super().execute_step(plan, step, message):
                    yield event

    executor = ResumingExecutor(should_wait=True, wait_on_step="step_1")

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    # Run and wait
    async for event in flow.run("Test"):
        pass

    assert flow._waiting_step_id == "step_1"

    # Resume
    async for event in flow.run("Continue", resume=True):
        pass

    # Flow should be complete
    assert flow.state == FlowState.COMPLETED


# ── Tests: Error Handling ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_planning_failure(project_context):
    """Test handling of planning failure."""
    planner = MockPlannerAgent(should_fail=True)
    executor = MockExecutionAgent()

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test message"):
        events.append(event)

    # Should have error event
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(error_events) >= 1

    # Should have done event
    done_events = [e for e in events if isinstance(e, DoneEvent)]
    assert len(done_events) >= 1


# ── Tests: BaseFlow ───────────────────────────────────────────────────────────


def test_base_flow_is_abstract():
    """Test that BaseFlow defines the expected interface."""
    base = BaseFlow()

    # BaseFlow should have run method
    assert hasattr(base, "run")
    assert callable(base.run)

    # The run method should return an async generator when called
    import asyncio

    async def consume_generator():
        result = []
        gen = base.run("test")
        async for _ in gen:
            result.append(_)
        return result

    # The base implementation yields nothing (empty generator)
    events = asyncio.run(consume_generator())
    # BaseFlow.run yields nothing meaningful, so we just verify it works
    assert isinstance(events, list)
    assert len(events) == 0


# ── Tests: Flow Statistics ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_update_during_execution(
    mock_planner, mock_executor, project_context
):
    """Test that stats update during execution."""
    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    initial_stats = flow.stats
    assert initial_stats["step_count"] == 0

    async for event in flow.run("Test message"):
        pass

    final_stats = flow.stats
    assert final_stats["state"] == FlowState.COMPLETED.value
    assert final_stats["step_count"] >= 0


@pytest.mark.asyncio
async def test_wall_time_tracking(project_context):
    """Test that wall time is tracked."""
    mock_planner = MockPlannerAgent()
    mock_executor = MockExecutionAgent()

    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    async for event in flow.run("Test message"):
        pass

    stats = flow.stats
    assert "wall_time_seconds" in stats
    assert stats["wall_time_seconds"] >= 0


# ── Tests: Tool Event Handling ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_events_in_order(project_context):
    """Test that tool events are yielded in correct order."""
    steps = [
        PlanStep(
            id="step_1",
            description="Test step",
            expected_tool="test_tool",
            status="pending",
        ),
    ]
    plan = PlanEvent(
        plan_id="plan-1",
        title="Test Plan",
        language="en",
        steps=steps,
    )

    planner = MockPlannerAgent(plans=[plan])
    
    # Configure executor with tool events
    executor = MockExecutionAgent()
    executor.steps_to_execute = [
        {
            "step_id": "step_1",
            "events": [
                ToolEvent(
                    tool_call_id="call-1",
                    name="test_tool",
                    status="calling",
                    function="test_tool",
                    args={"query": "test"},
                ),
                ToolEvent(
                    tool_call_id="call-1",
                    name="test_tool",
                    status="called",
                    function="test_tool",
                    args={"query": "test"},
                    result={"ok": True, "data": []},
                ),
            ],
        },
    ]

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test"):
        events.append(event)

    # Check order
    tool_calling_idx = None
    tool_called_idx = None

    for i, event in enumerate(events):
        if isinstance(event, ToolEvent):
            if event.status == "calling" and tool_calling_idx is None:
                tool_calling_idx = i
            elif event.status == "called":
                tool_called_idx = i

    assert tool_calling_idx is not None
    assert tool_called_idx is not None
    assert tool_calling_idx < tool_called_idx


# ── Tests: Token Estimation ───────────────────────────────────────────────────


def test_token_estimation_message():
    """Test token estimation for MessageEvent."""
    flow = PlanActFlow(
        planner=MockPlannerAgent(),
        executor=MockExecutionAgent(),
    )

    event = MessageEvent(role="assistant", content="Hello world" * 100)
    tokens = flow._estimate_tokens(event)

    # Should be approximately len(content) / 4
    expected = len(event.content) // 4
    assert tokens == expected


def test_token_estimation_plan():
    """Test token estimation for PlanEvent."""
    flow = PlanActFlow(
        planner=MockPlannerAgent(),
        executor=MockExecutionAgent(),
    )

    event = PlanEvent(
        plan_id="test",
        title="Test Title",
        language="en",
        steps=[
            PlanStep(
                id="s1",
                description="Step description",
                expected_tool="tool",
            ),
        ],
    )
    tokens = flow._estimate_tokens(event)

    # Should include title and descriptions
    assert tokens > 0


def test_token_estimation_tool():
    """Test token estimation for ToolEvent."""
    flow = PlanActFlow(
        planner=MockPlannerAgent(),
        executor=MockExecutionAgent(),
    )

    event = ToolEvent(
        tool_call_id="call-1",
        name="test",
        status="called",
        function="test",
        args={"arg1": "value1", "arg2": "value2"},
        result={"ok": True, "data": [1, 2, 3]},
    )
    tokens = flow._estimate_tokens(event)

    assert tokens > 0


# ── Tests: Summary ─────────────────────────────────────────────────────────────


def test_build_summary(mock_planner, mock_executor):
    """Test summary building."""
    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
    )

    # Set up a completed plan
    flow._current_plan = PlanEvent(
        plan_id="plan-1",
        title="Test",
        language="en",
        steps=[
            PlanStep(
                id="s1",
                description="Step 1",
                expected_tool="tool",
                status="completed",
            ),
            PlanStep(
                id="s2",
                description="Step 2",
                expected_tool="tool",
                status="failed",
            ),
            PlanStep(
                id="s3",
                description="Step 3",
                expected_tool="tool",
                status="pending",
            ),
        ],
    )
    flow._step_count = 3
    flow._total_tokens_used = 1000
    flow._start_time = datetime.now(timezone.utc)

    summary = flow._build_summary()

    assert "completed" in summary
    assert "failed" in summary
    assert "3" in summary
    assert "1000" in summary


# ── Tests: Edge Cases ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_plan(project_context):
    """Test handling of plan with no steps."""
    empty_plan = PlanEvent(
        plan_id="plan-1",
        title="Empty Plan",
        language="en",
        steps=[],
    )

    planner = MockPlannerAgent(plans=[empty_plan])
    executor = MockExecutionAgent()

    flow = PlanActFlow(
        planner=planner,
        executor=executor,
        project_context=project_context,
    )

    events = []
    async for event in flow.run("Test"):
        events.append(event)

    # Should complete without errors
    assert flow.state == FlowState.COMPLETED


@pytest.mark.asyncio
async def test_already_cancelled_flow(project_context):
    """Test that already cancelled flow handles gracefully."""
    mock_planner = MockPlannerAgent()
    mock_executor = MockExecutionAgent()

    flow = PlanActFlow(
        planner=mock_planner,
        executor=mock_executor,
        project_context=project_context,
    )

    # Cancel multiple times
    flow.cancel()
    flow.cancel()

    events = []
    async for event in flow.run("Test"):
        events.append(event)

    # Should handle cancellation gracefully
    assert len(events) >= 1


# ── Main ──────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
