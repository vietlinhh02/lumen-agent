"""Tests for assistant LangGraph nodes."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest

from app.agents.assistant.events import AssistantDeltaEvent, ToolEvent
from app.agents.assistant.graph.nodes import react_loop_node, simple_chat_node
from app.agents.assistant.graph.state import AssistantGraphState
from app.ai.provider import StreamChunk, StreamDone, TextChunk, ToolCallDone


class FakeToolStreamingProvider:
    """Provider that yields a predefined stream_with_tools chunk sequence."""

    def __init__(self, chunks: list[StreamChunk]) -> None:
        self._chunks = chunks

    async def stream_with_tools(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[StreamChunk]:
        del messages, system, max_tokens, tools
        for chunk in self._chunks:
            yield chunk


class FakeTextStreamingProvider:
    """Provider that yields predefined text tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    async def stream(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str]:
        del messages, system, max_tokens
        for token in self._tokens:
            yield token


def _state() -> AssistantGraphState:
    return AssistantGraphState(
        session_id=uuid4(),
        user_id=uuid4(),
        messages=[{"role": "user", "content": "summarize the report"}],
    )


@pytest.mark.asyncio
async def test_simple_chat_streams_visible_tokens_before_final(monkeypatch) -> None:
    """Simple chat emits visible assistant tokens as they arrive."""
    emitted: list[object] = []
    provider = FakeTextStreamingProvider(["Xin chào", ", tôi giúp được gì?"])

    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: emitted.append)
    monkeypatch.setattr("app.ai.provider.get_provider", lambda: provider)

    result = await simple_chat_node(_state())

    deltas = [event for event in emitted if isinstance(event, AssistantDeltaEvent)]
    assert [event.delta for event in deltas] == [
        "Xin chào",
        ", tôi giúp được gì?",
        "",
    ]
    assert deltas[-1].is_final is True
    assert result["messages"] == [
        {"role": "assistant", "content": "Xin chào, tôi giúp được gì?"}
    ]


@pytest.mark.asyncio
async def test_react_loop_does_not_stream_intermediate_tool_text(monkeypatch) -> None:
    """Intermediate ReAct text before a tool call is not a visible chat delta."""
    emitted: list[object] = []
    provider = FakeToolStreamingProvider(
        [
            TextChunk("I need to get the report."),
            ToolCallDone("call-1", "get_report", {"report_id": "r1"}),
            StreamDone(),
        ]
    )

    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: emitted.append)
    monkeypatch.setattr("app.ai.provider.get_provider", lambda: provider)

    result = await react_loop_node(_state())

    assert not any(isinstance(event, AssistantDeltaEvent) for event in emitted)
    assert any(isinstance(event, ToolEvent) for event in emitted)
    assert result["messages"][0]["content"] == "I need to get the report."


@pytest.mark.asyncio
async def test_react_loop_streams_visible_text_when_no_tool_call(monkeypatch) -> None:
    """A no-tool ReAct response is still emitted as the final visible answer."""
    emitted: list[object] = []
    provider = FakeToolStreamingProvider(
        [
            TextChunk("Here is "),
            TextChunk("the final summary."),
            StreamDone(),
        ]
    )

    monkeypatch.setattr("langgraph.config.get_stream_writer", lambda: emitted.append)
    monkeypatch.setattr("app.ai.provider.get_provider", lambda: provider)

    result = await react_loop_node(_state())

    deltas = [event for event in emitted if isinstance(event, AssistantDeltaEvent)]
    assert [event.delta for event in deltas] == ["Here is ", "the final summary.", ""]
    assert deltas[-1].is_final is True
    assert result["messages"] == [
        {"role": "assistant", "content": "Here is the final summary."}
    ]
