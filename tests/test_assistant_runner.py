"""Tests for AssistantRunner — ReAct loop and WS event emission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.assistant_runner import AssistantRunner


@pytest.mark.asyncio
async def test_runner_emits_done_when_no_tool_calls():
    runner = AssistantRunner(
        db=AsyncMock(),
        user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(),
        document_id=uuid4(),
        ws_send=AsyncMock(),
    )
    runner.history = [{"role": "user", "content": "hi"}]

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "Hello!",
            "tool_calls": None,
        }
        mock_get_provider.return_value = mock_provider

        with (
            patch(
                "app.services.assistant_runner.persist_assistant_message",
                new_callable=AsyncMock,
            ),
            patch("app.services.assistant_runner.load_assistant_history", new_callable=AsyncMock),
        ):
            await runner.run_turn("hi")

    assert any(e["type"] == "done" for e in runner.events)


@pytest.mark.asyncio
async def test_runner_executes_tool_and_loops():
    runner = AssistantRunner(
        db=AsyncMock(),
        user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(),
        document_id=uuid4(),
        ws_send=AsyncMock(),
    )

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = [
            {
                "message": "Searching…",
                "tool_calls": [{"name": "search_papers", "args": {"query": "RAG"}}],
            },
            {"message": "Done", "tool_calls": None},
        ]
        mock_get_provider.return_value = mock_provider

        with patch("app.services.assistant_runner.TOOL_REGISTRY") as mock_registry:
            mock_handler = AsyncMock(return_value={"papers_found": 3})
            mock_registry.get.return_value = mock_handler
            with (
                patch(
                    "app.services.assistant_runner.persist_assistant_message",
                    new_callable=AsyncMock,
                ),
                patch(
                    "app.services.assistant_runner.load_assistant_history",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
            ):
                await runner.run_turn("find papers on RAG")

    tool_call_events = [e for e in runner.events if e["type"] == "tool_call"]
    tool_result_events = [e for e in runner.events if e["type"] == "tool_result"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0]["tool"] == "search_papers"
    assert len(tool_result_events) == 1
    assert any(e["type"] == "done" for e in runner.events)


@pytest.mark.asyncio
async def test_runner_stops_on_max_iterations():
    runner = AssistantRunner(
        db=AsyncMock(),
        user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(),
        document_id=uuid4(),
        ws_send=AsyncMock(),
        max_iterations=3,
    )

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "x",
            "tool_calls": [{"name": "search_papers", "args": {"query": "x"}}],
        }
        mock_get_provider.return_value = mock_provider

        with patch("app.services.assistant_runner.TOOL_REGISTRY") as mock_registry:
            mock_registry.get.return_value = AsyncMock(return_value={})
            with (
                patch(
                    "app.services.assistant_runner.persist_assistant_message",
                    new_callable=AsyncMock,
                ),
                patch(
                    "app.services.assistant_runner.load_assistant_history",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
            ):
                await runner.run_turn("loop forever")

    done_events = [e for e in runner.events if e["type"] == "done"]
    assert done_events
    assert done_events[0].get("reason") == "max_iterations"


@pytest.mark.asyncio
async def test_runner_stopped_flag_halts_loop():
    runner = AssistantRunner(
        db=AsyncMock(),
        user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(),
        document_id=uuid4(),
        ws_send=AsyncMock(),
    )
    runner.stopped.set()

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "x",
            "tool_calls": [{"name": "search_papers", "args": {}}],
        }
        mock_get_provider.return_value = mock_provider

        with patch(
            "app.services.assistant_runner.load_assistant_history",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await runner.run_turn("stop test")

    stopped_events = [e for e in runner.events if e["type"] == "stopped"]
    assert stopped_events


@pytest.mark.asyncio
async def test_runner_loads_persisted_history_before_new_turn():
    runner = AssistantRunner(
        db=AsyncMock(),
        user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(),
        document_id=uuid4(),
        ws_send=AsyncMock(),
    )

    previous = [
        {"role": "user", "content": "ai trong y tế"},
        {"role": "assistant", "content": "Bạn muốn câu hỏi nghiên cứu nào?"},
    ]
    expected_previous = [item.copy() for item in previous]

    with patch("app.services.assistant_runner.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "message": "Tôi sẽ dùng câu hỏi về chẩn đoán ung thư.",
            "tool_calls": None,
        }
        mock_get_provider.return_value = mock_provider

        with (
            patch(
                "app.services.assistant_runner.load_assistant_history",
                new_callable=AsyncMock,
                return_value=previous,
            ),
            patch(
                "app.services.assistant_runner.persist_assistant_message",
                new_callable=AsyncMock,
            ),
        ):
            await runner.run_turn("AI cải thiện chẩn đoán ung thư như thế nào?")

    sent_messages = mock_provider.complete_structured.call_args.kwargs["messages"]
    assert sent_messages[:2] == expected_previous
    assert sent_messages[2]["content"] == "AI cải thiện chẩn đoán ung thư như thế nào?"
