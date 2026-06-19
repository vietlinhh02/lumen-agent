"""Tests for the PlannerAgent."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestPlanOutputSchema:
    """Test PlanOutput and StepOutput schemas."""

    def test_step_output_valid(self):
        """Test valid StepOutput creation."""
        from app.ai.structured_outputs import StepOutput

        step = StepOutput(
            id="step_1",
            description="Search for papers on RAG",
            expected_tool="search_papers",
        )
        assert step.id == "step_1"
        assert step.description == "Search for papers on RAG"
        assert step.expected_tool == "search_papers"

    def test_step_output_empty_tool_rejected(self):
        """Test that empty tool name is rejected."""
        from pydantic import ValidationError

        from app.ai.structured_outputs import StepOutput

        with pytest.raises(ValidationError):
            StepOutput(
                id="step_1",
                description="Test step",
                expected_tool="",
            )

    def test_plan_output_valid(self):
        """Test valid PlanOutput creation."""
        from app.ai.structured_outputs import PlanOutput, StepOutput

        plan = PlanOutput(
            title="Research Workflow",
            language="en",
            steps=[
                StepOutput(
                    id="step_1",
                    description="Search papers",
                    expected_tool="search_papers",
                ),
                StepOutput(
                    id="step_2",
                    description="Save papers",
                    expected_tool="save_paper_to_project",
                ),
            ],
        )
        assert plan.title == "Research Workflow"
        assert plan.language == "en"
        assert len(plan.steps) == 2

    def test_plan_output_empty_steps_rejected(self):
        """Test that empty steps list is rejected."""
        from pydantic import ValidationError

        from app.ai.structured_outputs import PlanOutput

        with pytest.raises(ValidationError):
            PlanOutput(
                title="Empty Plan",
                language="en",
                steps=[],
            )

    def test_plan_output_default_language(self):
        """Test that default language is 'en'."""
        from app.ai.structured_outputs import PlanOutput, StepOutput

        plan = PlanOutput(
            title="Test",
            steps=[
                StepOutput(id="1", description="Test", expected_tool="test_tool"),
            ],
        )
        assert plan.language == "en"


class TestPlannerPrompts:
    """Test that planner prompts are defined correctly."""

    def test_planner_system_prompt_exists(self):
        """Test that PLANNER_SYSTEM_PROMPT is defined."""
        from app.ai.prompts import PLANNER_SYSTEM_PROMPT

        assert PLANNER_SYSTEM_PROMPT is not None
        assert len(PLANNER_SYSTEM_PROMPT) > 100
        assert "tool" in PLANNER_SYSTEM_PROMPT.lower()

    def test_create_plan_prompt_exists(self):
        """Test that CREATE_PLAN_PROMPT is defined."""
        from app.ai.prompts import CREATE_PLAN_PROMPT

        assert CREATE_PLAN_PROMPT is not None
        assert "{message}" in CREATE_PLAN_PROMPT
        assert "{tool_list}" in CREATE_PLAN_PROMPT

    def test_update_plan_prompt_exists(self):
        """Test that UPDATE_PLAN_PROMPT is defined."""
        from app.ai.prompts import UPDATE_PLAN_PROMPT

        assert UPDATE_PLAN_PROMPT is not None
        assert "{current_plan}" in UPDATE_PLAN_PROMPT
        assert "{step_id}" in UPDATE_PLAN_PROMPT


class TestPlannerAgentInit:
    """Test PlannerAgent initialization."""

    def test_init_with_provider(self):
        """Test that PlannerAgent can be initialized with a provider."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)

        assert agent.provider is mock_provider
        assert agent._tools == []
        assert agent._tool_names == []

    def test_init_with_tools(self):
        """Test that PlannerAgent extracts tool names."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        mock_tool1 = MagicMock()
        mock_tool1.name = "search_papers"
        mock_tool2 = MagicMock()
        mock_tool2.name = "save_paper_to_project"

        agent = PlannerAgent(provider=mock_provider, tools=[mock_tool1, mock_tool2])

        assert len(agent._tool_names) == 2
        assert "search_papers" in agent._tool_names
        assert "save_paper_to_project" in agent._tool_names

    def test_init_with_dict_tools(self):
        """Test that PlannerAgent handles dict-style tools."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        tools = [{"name": "list_projects"}, {"name": "get_project"}]

        agent = PlannerAgent(provider=mock_provider, tools=tools)  # type: ignore

        assert len(agent._tool_names) == 2
        assert "list_projects" in agent._tool_names

    def test_init_with_string_tools(self):
        """Test that PlannerAgent handles string tools."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        tools = ["search_papers", "generate_matrix"]

        agent = PlannerAgent(provider=mock_provider, tools=tools)  # type: ignore

        assert len(agent._tool_names) == 2


class TestPlannerAgentFormatTools:
    """Test tool formatting methods."""

    def test_format_tool_list(self):
        """Test that tool list is formatted correctly."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        tools = ["search_papers", "save_paper_to_project", "generate_matrix"]

        agent = PlannerAgent(provider=mock_provider, tools=tools)  # type: ignore
        formatted = agent._format_tool_list()

        assert "search_papers" in formatted
        assert "save_paper_to_project" in formatted
        assert "generate_matrix" in formatted

    def test_format_tool_list_empty(self):
        """Test formatting with no tools."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)
        formatted = agent._format_tool_list()

        assert "No tools available" in formatted


@pytest.mark.asyncio
class TestPlannerAgentCreatePlan:
    """Test PlannerAgent.create_plan method."""

    async def test_create_plan_missing_context(self):
        """Test that missing context fields raise ValueError."""
        from app.agents.assistant.agents.planner import PlannerAgent

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)

        # Collect all events - the ValueError is raised inside the generator
        # before any events are yielded
        events = []
        errors = []
        try:
            async for event in agent.create_plan(
                message="Find papers on RAG",
                project_context={"project_name": "Test", "topic": "RAG"},
            ):
                events.append(event)
        except ValueError as e:
            errors.append(e)

        # The ValueError should be raised before yielding any events
        assert len(errors) == 1
        assert "Missing required context fields" in str(errors[0])
        assert len(events) == 0

    async def test_create_plan_yields_reasoning_event(self):
        """Test that create_plan yields a reasoning MessageEvent first."""
        from app.agents.assistant.agents.planner import PlannerAgent

        from app.agents.assistant.events import MessageEvent

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)

        events = []
        async for event in agent.create_plan(
            message="Find papers on RAG",
            project_context={
                "project_id": str(uuid4()),
                "project_name": "RAG Research",
                "topic": "Retrieval Augmented Generation",
            },
        ):
            events.append(event)

        # First event should be a reasoning message
        assert len(events) >= 1
        assert isinstance(events[0], MessageEvent)
        assert events[0].role == "assistant"
        assert "Analyzing" in events[0].content

    async def test_create_plan_with_mock_llm(self):
        """Test create_plan with a mock LLM response."""
        from app.agents.assistant.agents.planner import PlannerAgent

        from app.agents.assistant.events import PlanEvent
        from app.ai.structured_outputs import PlanOutput, StepOutput

        # Create mock provider
        mock_provider = MagicMock()
        mock_plan = PlanOutput(
            title="Research Plan",
            language="en",
            steps=[
                StepOutput(
                    id="step_1",
                    description="Search for RAG papers",
                    expected_tool="search_papers",
                ),
            ],
        )
        mock_provider.acomplete_structured = AsyncMock(return_value=mock_plan)

        agent = PlannerAgent(provider=mock_provider, tools=["search_papers"])
        events = []

        async for event in agent.create_plan(
            message="Find papers on RAG",
            project_context={
                "project_id": str(uuid4()),
                "project_name": "RAG Research",
                "topic": "Retrieval Augmented Generation",
            },
        ):
            events.append(event)

        # Should have reasoning message and plan event
        assert len(events) == 2
        assert isinstance(events[1], PlanEvent)
        assert events[1].title == "Research Plan"
        assert len(events[1].steps) == 1
        assert events[1].steps[0].expected_tool == "search_papers"


@pytest.mark.asyncio
class TestPlannerAgentUpdatePlan:
    """Test PlannerAgent.update_plan method."""

    async def test_update_plan_already_complete(self):
        """Test that update_plan returns early if plan is complete."""
        from app.agents.assistant.agents.planner import PlannerAgent

        from app.agents.assistant.events import MessageEvent, PlanEvent, PlanStep

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)

        # Create a plan where all steps are completed
        current_plan = PlanEvent(
            plan_id=str(uuid4()),
            title="Complete Plan",
            language="en",
            steps=[
                PlanStep(
                    id="step_1",
                    description="Search papers",
                    expected_tool="search_papers",
                    status="completed",
                ),
            ],
        )

        events = []
        async for event in agent.update_plan(
            current_plan=current_plan,
            last_step_id="step_1",
            step_result={"ok": True, "message": "Found 10 papers"},
        ):
            events.append(event)

        # Should yield a message saying no update needed and the plan
        assert len(events) == 2
        assert isinstance(events[0], MessageEvent)
        assert "already complete" in events[0].content.lower()

    async def test_update_plan_step_success(self):
        """Test update_plan when step succeeds - marks step completed."""
        from app.agents.assistant.agents.planner import PlannerAgent

        from app.agents.assistant.events import MessageEvent, PlanEvent, PlanStep

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)

        # Create a plan with pending steps
        current_plan = PlanEvent(
            plan_id=str(uuid4()),
            title="Plan",
            language="en",
            steps=[
                PlanStep(
                    id="step_1",
                    description="Search papers",
                    expected_tool="search_papers",
                    status="completed",
                ),
                PlanStep(
                    id="step_2",
                    description="Save papers",
                    expected_tool="save_paper_to_project",
                    status="pending",
                ),
            ],
        )

        events = []
        async for event in agent.update_plan(
            current_plan=current_plan,
            last_step_id="step_1",
            step_result={"ok": True, "message": "Found papers"},
        ):
            events.append(event)

        # Should yield messages about progress and updated plan
        assert len(events) >= 2
        # At least one message should mention completion or continuing
        message_contents = [e.content.lower() for e in events if isinstance(e, MessageEvent)]
        assert any("continues" in c or "completed" in c for c in message_contents)

    async def test_update_plan_step_failed(self):
        """Test update_plan when step fails."""
        from app.agents.assistant.agents.planner import PlannerAgent

        from app.agents.assistant.events import MessageEvent, PlanEvent, PlanStep

        mock_provider = MagicMock()
        agent = PlannerAgent(provider=mock_provider)

        current_plan = PlanEvent(
            plan_id=str(uuid4()),
            title="Plan",
            language="en",
            steps=[
                PlanStep(
                    id="step_1",
                    description="Search papers",
                    expected_tool="search_papers",
                    status="pending",
                ),
                PlanStep(
                    id="step_2",
                    description="Save papers",
                    expected_tool="save_paper_to_project",
                    status="pending",
                ),
            ],
        )

        events = []
        async for event in agent.update_plan(
            current_plan=current_plan,
            last_step_id="step_1",
            step_result={
                "ok": False,
                "error_code": "SEARCH_FAILED",
                "message": "Search timed out",
            },
        ):
            events.append(event)

        # Should indicate failure
        assert len(events) >= 1
        # At least one message should mention failure
        message_events = [e for e in events if isinstance(e, MessageEvent)]
        assert any("failed" in e.content.lower() for e in message_events)


class TestPlannerEventTypes:
    """Test that planner emits correct event types."""

    def test_plan_event_structure(self):
        """Test PlanEvent has correct structure."""
        from app.agents.assistant.events import PlanEvent, PlanStep

        plan = PlanEvent(
            plan_id="plan-123",
            title="Test Plan",
            language="en",
            steps=[
                PlanStep(
                    id="step_1",
                    description="Test step",
                    expected_tool="test_tool",
                ),
            ],
        )

        assert plan.type == "plan"
        assert plan.plan_id == "plan-123"
        assert plan.title == "Test Plan"
        assert len(plan.steps) == 1
        assert plan.steps[0].id == "step_1"
        assert plan.steps[0].status == "pending"

    def test_plan_step_statuses(self):
        """Test PlanStep status values."""
        from app.agents.assistant.events import PlanStep

        for status in ["pending", "running", "completed", "failed"]:
            step = PlanStep(
                id="test",
                description="Test",
                expected_tool="tool",
                status=status,
            )
            assert step.status == status
