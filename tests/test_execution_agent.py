"""
Tests for the ExecutionAgent.

Uses mock provider + 1 real tool to test:
- ToolEvent emission in order
- Final MessageEvent emission
- Unknown tool handling
- ask_user_clarification handling
- Max tool calls limit
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.agents.assistant.agents.execution import MAX_TOOL_CALLS_PER_STEP, ExecutionAgent
from langchain_core.tools import BaseTool, tool

from app.agents.assistant.events import (
    ErrorEvent,
    MessageEvent,
    PlanEvent,
    PlanStep,
    StepEvent,
    ToolEvent,
    WaitEvent,
)

# ── Mock Tools ────────────────────────────────────────────────────────────────


@tool
def mock_search_papers(query: str, limit: int = 10) -> dict[str, Any]:
    """
    Mock search papers tool for testing.

    Returns a list of mock papers.
    """
    return {
        "ok": True,
        "message": f"Found {limit} papers",
        "data": {
            "papers": [
                {"id": "1", "title": f"Paper {i}", "authors": ["Author"]}
                for i in range(limit)
            ]
        }
    }


@tool
def mock_get_project(project_id: str) -> dict[str, Any]:
    """
    Mock get project tool for testing.
    """
    return {
        "ok": True,
        "message": f"Project: {project_id}",
        "data": {"project": {"id": project_id, "name": "Test Project"}}
    }


@tool
def mock_ask_user_clarification(question: str, options: list[str] | None = None) -> dict[str, Any]:
    """
    Mock ask user clarification tool for testing.
    """
    return {
        "ok": True,
        "status": "waiting",
        "question": question,
        "options": options,
        "message": "Waiting for user response",
    }


# ── Mock LLM Response Helpers ──────────────────────────────────────────────────


class MockToolCall:
    """Mock tool call object."""

    def __init__(self, name: str, arguments: dict[str, Any], id: str = "call_1"):
        self.function = type("obj", (object,), {"name": name, "arguments": json.dumps(arguments) if isinstance(arguments, dict) else arguments})()
        self.id = id


class MockMessage:
    """Mock LLM message response."""

    def __init__(self, content: str = "", tool_calls: list[MockToolCall] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockProvider:
    """Mock LLM provider for testing."""

    def __init__(self, responses: list[MockMessage]):
        self.responses = responses
        self.call_count = 0

    async def complete(
        self,
        messages: list,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        response = self.responses[self.call_count] if self.call_count < len(self.responses) else MockMessage("Done")
        self.call_count += 1
        return response.content


def create_mock_llm_response(
    content: str = "",
    tool_calls: list[dict[str, Any]] | None = None
) -> MockMessage:
    """Helper to create mock LLM responses."""
    calls = []
    if tool_calls:
        for tc in tool_calls:
            calls.append(MockToolCall(
                name=tc["name"],
                arguments=tc["arguments"],
                id=tc.get("id", "call_1")
            ))
    return MockMessage(content=content, tool_calls=calls)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_provider() -> MockProvider:
    """Create a mock LLM provider."""
    return MockProvider([])


@pytest.fixture
def tools() -> list[BaseTool]:
    """Create a list of mock tools for testing."""
    return [mock_search_papers, mock_get_project, mock_ask_user_clarification]


@pytest.fixture
def sample_plan() -> PlanEvent:
    """Create a sample plan for testing."""
    return PlanEvent(
        plan_id="plan-1",
        title="Test Plan",
        language="en",
        steps=[
            PlanStep(
                id="step_1",
                description="Search for papers on RAG",
                expected_tool="mock_search_papers",
                status="pending",
            ),
            PlanStep(
                id="step_2",
                description="Get project details",
                expected_tool="mock_get_project",
                status="pending",
            ),
        ],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execution_agent_initialization(mock_provider, tools):
    """Test ExecutionAgent initializes correctly."""
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    assert agent.provider is mock_provider
    assert len(agent._tools) == 3
    assert "mock_search_papers" in agent._tool_map
    assert "mock_get_project" in agent._tool_map
    assert "mock_ask_user_clarification" in agent._tool_map


@pytest.mark.asyncio
async def test_execution_agent_no_tools():
    """Test ExecutionAgent works with no tools."""
    mock_provider = MockProvider([create_mock_llm_response("No tools available")])
    agent = ExecutionAgent(provider=mock_provider, tools=[])
    
    assert len(agent._tools) == 0
    assert len(agent._tool_map) == 0


@pytest.mark.asyncio
async def test_step_started_event_emitted(tools, sample_plan):
    """Test that StepEvent with 'running' status is emitted first."""
    mock_provider = MockProvider([create_mock_llm_response("Done")])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    # Patch _call_llm_with_tools to use mock provider
    agent._call_llm_with_tools = AsyncMock(return_value=mock_provider.responses[0])
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # First event should be StepEvent with status "running"
    assert len(events) > 0
    assert isinstance(events[0], StepEvent)
    assert events[0].status == "running"
    assert events[0].step_id == step.id


@pytest.mark.asyncio
async def test_final_message_event_emitted(tools, sample_plan):
    """Test that MessageEvent is emitted after tool execution."""
    mock_provider = MockProvider([create_mock_llm_response("Done")])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    agent._call_llm_with_tools = AsyncMock(return_value=mock_provider.responses[0])
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have MessageEvent
    message_events = [e for e in events if isinstance(e, MessageEvent)]
    assert len(message_events) >= 1
    
    # Last MessageEvent should have content
    last_message = message_events[-1]
    assert last_message.role == "assistant"


@pytest.mark.asyncio
async def test_step_completed_event_emitted(tools, sample_plan):
    """Test that StepEvent with 'completed' status is emitted at the end."""
    mock_provider = MockProvider([create_mock_llm_response("Done")])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    agent._call_llm_with_tools = AsyncMock(return_value=mock_provider.responses[0])
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have StepEvent with "completed" status
    step_events = [e for e in events if isinstance(e, StepEvent)]
    completed_events = [e for e in step_events if e.status == "completed"]
    
    assert len(completed_events) >= 1
    completed = completed_events[-1]
    assert completed.step_id == step.id


@pytest.mark.asyncio
async def test_tool_call_event_sequence(tools, sample_plan):
    """Test that ToolEvent 'calling' and 'called' are emitted in order."""
    # Mock provider returns a tool call followed by final response
    responses = [
        create_mock_llm_response(
            content="Found papers",
            tool_calls=[{"name": "mock_search_papers", "arguments": {"query": "RAG", "limit": 10}}]
        ),
        create_mock_llm_response(content="Done")  # Final response after tool result
    ]
    mock_provider = MockProvider(responses)
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    # Patch to return mock responses in order
    async def mock_llm_call(messages, tools):
        response = mock_provider.responses[len(messages) // 2]  # Approximate based on message count
        return response
    
    call_idx = [0]
    async def mock_llm_call_indexed(messages, tools):
        idx = min(call_idx[0], len(mock_provider.responses) - 1)
        call_idx[0] += 1
        return mock_provider.responses[idx]
    
    agent._call_llm_with_tools = mock_llm_call_indexed
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have ToolEvent with "calling" status
    calling_events = [e for e in events if isinstance(e, ToolEvent) and e.status == "calling"]
    assert len(calling_events) >= 1
    
    # Should have ToolEvent with "called" status
    called_events = [e for e in events if isinstance(e, ToolEvent) and e.status == "called"]
    assert len(called_events) >= 1
    
    # Calling should come before called
    calling_idx = events.index(calling_events[0])
    called_idx = events.index(called_events[0])
    assert calling_idx < called_idx


@pytest.mark.asyncio
async def test_unknown_tool_yields_error(tools, sample_plan):
    """Test that calling an unknown tool yields ErrorEvent."""
    # Mock provider returns a call to unknown tool
    mock_provider = MockProvider([
        create_mock_llm_response(
            content="Unknown tool",
            tool_calls=[{"name": "nonexistent_tool", "arguments": {}}]
        ),
    ])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    agent._call_llm_with_tools = AsyncMock(return_value=mock_provider.responses[0])
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have ErrorEvent
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(error_events) >= 1
    assert error_events[0].code == "UNKNOWN_TOOL"
    
    # Step should be marked as failed
    step_events = [e for e in events if isinstance(e, StepEvent)]
    failed_events = [e for e in step_events if e.status == "failed"]
    assert len(failed_events) >= 1


@pytest.mark.asyncio
async def test_ask_user_clarification_yields_wait_event(tools, sample_plan):
    """Test that ask_user_clarification tool yields WaitEvent."""
    # Create a tool with the exact name "ask_user_clarification"
    @tool
    def ask_user_clarification(question: str, options: list[str] | None = None) -> dict[str, Any]:
        """Ask user clarification tool."""
        return {
            "ok": True,
            "status": "waiting",
            "question": question,
            "options": options,
            "message": "Waiting for user response",
        }

    test_tools = [mock_search_papers, mock_get_project, ask_user_clarification]

    # Mock provider returns ask_user_clarification call
    mock_provider = MockProvider([
        create_mock_llm_response(
            content="Need clarification",
            tool_calls=[{
                "name": "ask_user_clarification",
                "arguments": {
                    "question": "Which project should I use?",
                    "options": ["Project A", "Project B"]
                }
            }]
        ),
    ])
    agent = ExecutionAgent(provider=mock_provider, tools=test_tools)
    agent._call_llm_with_tools = AsyncMock(return_value=mock_provider.responses[0])

    step = sample_plan.steps[0]

    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)

    # Should have WaitEvent
    wait_events = [e for e in events if isinstance(e, WaitEvent)]
    assert len(wait_events) >= 1
    assert "Which project should I use?" in wait_events[0].question
    assert wait_events[0].options == ["Project A", "Project B"]

    # Should have ToolEvent for the clarification call
    tool_events = [e for e in events if isinstance(e, ToolEvent)]
    assert len(tool_events) >= 1


@pytest.mark.asyncio
async def test_max_tool_calls_limit(tools, sample_plan):
    """Test that exceeding max tool calls yields error."""
    # Create responses that keep returning tool calls
    responses = []
    for i in range(MAX_TOOL_CALLS_PER_STEP + 5):
        responses.append(create_mock_llm_response(
            content="",
            tool_calls=[{"name": "mock_search_papers", "arguments": {"query": f"query_{i}", "limit": 10}}]
        ))
    responses.append(create_mock_llm_response(content="Done"))
    
    mock_provider = MockProvider(responses)
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    # Track call count
    call_count = [0]
    async def mock_llm_calls(messages, tools):
        idx = min(call_count[0], len(mock_provider.responses) - 1)
        call_count[0] += 1
        return mock_provider.responses[idx]
    
    agent._call_llm_with_tools = mock_llm_calls
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have ErrorEvent for max tool calls
    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    max_error = [e for e in error_events if e.code == "MAX_TOOL_CALLS_REACHED"]
    assert len(max_error) >= 1
    
    # Step should be marked as failed
    step_events = [e for e in events if isinstance(e, StepEvent)]
    failed_events = [e for e in step_events if e.status == "failed"]
    assert len(failed_events) >= 1


@pytest.mark.asyncio
async def test_tool_results_appended_exactly_once(tools, sample_plan):
    """Test that tool results are appended to context exactly once."""
    call_log = []
    
    # Create a mock tool that logs calls
    @tool
    def logged_tool(query: str) -> dict[str, Any]:
        """Log tool call for testing."""
        call_log.append({"name": "logged_tool", "query": query})
        return {"ok": True, "message": f"Logged: {query}"}
    
    test_tools = [logged_tool]
    
    responses = [
        create_mock_llm_response(
            content="First call",
            tool_calls=[{"name": "logged_tool", "arguments": {"query": "first"}}]
        ),
        create_mock_llm_response(
            content="Second call",
            tool_calls=[{"name": "logged_tool", "arguments": {"query": "second"}}]
        ),
        create_mock_llm_response(content="Done")
    ]
    mock_provider = MockProvider(responses)
    agent = ExecutionAgent(provider=mock_provider, tools=test_tools)
    
    call_idx = [0]
    async def mock_llm_call(messages, tools):
        idx = min(call_idx[0], len(mock_provider.responses) - 1)
        call_idx[0] += 1
        return mock_provider.responses[idx]
    
    agent._call_llm_with_tools = mock_llm_call
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Tool should be called exactly 2 times
    assert len(call_log) == 2
    assert call_log[0]["query"] == "first"
    assert call_log[1]["query"] == "second"
    
    # Should have 2 ToolEvent for each call (calling + called)
    tool_events = [e for e in events if isinstance(e, ToolEvent)]
    calling_count = len([e for e in tool_events if e.status == "calling"])
    called_count = len([e for e in tool_events if e.status == "called"])
    
    assert calling_count == 2
    assert called_count == 2


@pytest.mark.asyncio
async def test_format_tools_for_prompt(tools):
    """Test that tools are formatted correctly for the prompt."""
    mock_provider = MockProvider([])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    formatted = agent._format_tools_for_prompt()
    
    assert "mock_search_papers" in formatted
    assert "mock_get_project" in formatted
    assert "mock_ask_user_clarification" in formatted


@pytest.mark.asyncio
async def test_build_tool_map(tools):
    """Test that tool map is built correctly."""
    mock_provider = MockProvider([])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    assert len(agent._tool_map) == 3
    assert "mock_search_papers" in agent._tool_map
    assert agent._tool_map["mock_search_papers"].name == "mock_search_papers"


@pytest.mark.asyncio
async def test_convert_langchain_tools_to_openai_format(tools):
    """Test that LangChain tools are converted to OpenAI format."""
    mock_provider = MockProvider([])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    openai_tools = agent._convert_langchain_tools_to_openai_format()
    
    assert len(openai_tools) == 3
    for opt in openai_tools:
        assert opt["type"] == "function"
        assert "function" in opt
        assert "name" in opt["function"]
        assert "description" in opt["function"]
        assert "parameters" in opt["function"]


@pytest.mark.asyncio
async def test_build_messages(sample_plan):
    """Test message building for LLM call."""
    mock_provider = MockProvider([])
    agent = ExecutionAgent(provider=mock_provider, tools=[])
    
    step = sample_plan.steps[0]
    messages = agent._build_messages(sample_plan, step, "test message")
    
    assert len(messages) >= 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Test Plan" in messages[0]["content"]
    assert "step_1" in messages[0]["content"]
    assert "Search for papers" in messages[1]["content"]


@pytest.mark.asyncio
async def test_summarize_step(tools):
    """Test step summarization."""
    mock_provider = MockProvider([MockMessage("Summary: Task completed successfully.")])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    step = PlanStep(
        id="step_1",
        description="Test step",
        expected_tool="mock_tool",
        status="completed",
    )
    
    tool_results = [
        {"name": "mock_tool", "result": {"ok": True, "message": "Done"}}
    ]
    
    summary = await agent.summarize_step(step, tool_results)
    
    assert "completed" in summary.lower() or "summary" in summary.lower()


@pytest.mark.asyncio
async def test_multiple_tool_calls_sequence(tools, sample_plan):
    """Test sequence of multiple tool calls in one step."""
    responses = [
        create_mock_llm_response(
            content="First result",
            tool_calls=[{"name": "mock_search_papers", "arguments": {"query": "RAG", "limit": 5}}]
        ),
        create_mock_llm_response(
            content="Second result",
            tool_calls=[{"name": "mock_get_project", "arguments": {"project_id": "proj-123"}}]
        ),
        create_mock_llm_response(content="All done!")
    ]
    mock_provider = MockProvider(responses)
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    call_idx = [0]
    async def mock_llm_call(messages, tools):
        idx = min(call_idx[0], len(mock_provider.responses) - 1)
        call_idx[0] += 1
        return mock_provider.responses[idx]
    
    agent._call_llm_with_tools = mock_llm_call
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have 2 ToolEvent pairs
    tool_events = [e for e in events if isinstance(e, ToolEvent)]
    calling_events = [e for e in tool_events if e.status == "calling"]
    called_events = [e for e in tool_events if e.status == "called"]
    
    assert len(calling_events) == 2
    assert len(called_events) == 2
    
    # Verify tool names in order
    assert calling_events[0].name == "mock_search_papers"
    assert calling_events[1].name == "mock_get_project"


@pytest.mark.asyncio
async def test_tool_execution_error_handling(tools, sample_plan):
    """Test handling of tool execution errors."""
    # Create a tool that raises an error
    @tool
    def error_tool() -> dict[str, Any]:
        """Tool that always fails."""
        raise ValueError("Tool execution failed")
    
    test_tools = [error_tool]
    
    responses = [
        create_mock_llm_response(
            content="Error occurred",
            tool_calls=[{"name": "error_tool", "arguments": {}}]
        ),
        create_mock_llm_response(content="After error")
    ]
    mock_provider = MockProvider(responses)
    agent = ExecutionAgent(provider=mock_provider, tools=test_tools)
    
    call_idx = [0]
    async def mock_llm_call(messages, tools):
        idx = min(call_idx[0], len(mock_provider.responses) - 1)
        call_idx[0] += 1
        return mock_provider.responses[idx]
    
    agent._call_llm_with_tools = mock_llm_call
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Should have ToolEvent with "failed" status
    failed_tool_events = [e for e in events if isinstance(e, ToolEvent) and e.status == "failed"]
    assert len(failed_tool_events) >= 1
    assert "error" in failed_tool_events[0].error.lower() or "failed" in failed_tool_events[0].error.lower()


# ── Event Order Tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_order_no_tools(tools, sample_plan):
    """Test event order when LLM responds without tool calls."""
    mock_provider = MockProvider([create_mock_llm_response("Done without tools")])
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    agent._call_llm_with_tools = AsyncMock(return_value=mock_provider.responses[0])
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Expected order:
    # 1. StepEvent(running)
    # 2. MessageEvent(final)
    # 3. StepEvent(completed)
    
    # StepEvent(running) should be first
    assert events[0].type == "step"
    assert events[0].status == "running"
    
    # StepEvent(completed) should be last
    assert events[-1].type == "step"
    assert events[-1].status == "completed"


@pytest.mark.asyncio
async def test_event_order_with_tool_calls(tools, sample_plan):
    """Test event order when LLM makes tool calls."""
    responses = [
        create_mock_llm_response(
            content="Calling tool",
            tool_calls=[{"name": "mock_search_papers", "arguments": {"query": "test"}}]
        ),
        create_mock_llm_response(content="After tool")
    ]
    mock_provider = MockProvider(responses)
    agent = ExecutionAgent(provider=mock_provider, tools=tools)
    
    call_idx = [0]
    async def mock_llm_call(messages, tools):
        idx = min(call_idx[0], len(mock_provider.responses) - 1)
        call_idx[0] += 1
        return mock_provider.responses[idx]
    
    agent._call_llm_with_tools = mock_llm_call
    
    step = sample_plan.steps[0]
    
    events = []
    async for event in agent.execute_step(sample_plan, step, "test message"):
        events.append(event)
    
    # Expected order:
    # 1. StepEvent(running)
    # 2. ToolEvent(calling)
    # 3. ToolEvent(called)
    # 4. MessageEvent(final)
    # 5. StepEvent(completed)
    
    # Find indices
    step_running_idx = None
    tool_calling_idx = None
    tool_called_idx = None
    message_idx = None
    step_completed_idx = None
    
    for i, event in enumerate(events):
        if isinstance(event, StepEvent) and event.status == "running":
            step_running_idx = i
        elif isinstance(event, ToolEvent) and event.status == "calling":
            tool_calling_idx = i
        elif isinstance(event, ToolEvent) and event.status == "called":
            tool_called_idx = i
        elif isinstance(event, MessageEvent):
            message_idx = i
        elif isinstance(event, StepEvent) and event.status == "completed":
            step_completed_idx = i
    
    # Verify order
    assert step_running_idx is not None
    assert step_running_idx < tool_calling_idx
    assert tool_calling_idx < tool_called_idx
    assert tool_called_idx < message_idx
    assert message_idx < step_completed_idx


# ── Extract Tool Calls Tests ──────────────────────────────────────────────────


def test_extract_tool_calls_from_response():
    """Test _extract_tool_calls handles different response formats."""
    mock_provider = MockProvider([])
    agent = ExecutionAgent(provider=mock_provider, tools=[])
    
    # Test with OpenAI-style response
    response = create_mock_llm_response(
        tool_calls=[{"name": "test_tool", "arguments": {"arg1": "value1"}}]
    )
    
    tool_calls = agent._extract_tool_calls(response)
    
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "test_tool"
    assert tool_calls[0]["arguments"] == {"arg1": "value1"}


def test_extract_content_from_response():
    """Test _extract_content handles different response formats."""
    mock_provider = MockProvider([])
    agent = ExecutionAgent(provider=mock_provider, tools=[])
    
    # Test with content
    response = create_mock_llm_response(content="Hello world")
    content = agent._extract_content(response)
    assert content == "Hello world"
    
    # Test with empty content
    response = create_mock_llm_response(content="")
    content = agent._extract_content(response)
    assert content == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
