"""Tests for the SSE transport (assistant_sse router)."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_user():
    return SimpleNamespace(id=uuid4(), email="a@b.c", role="user", is_active=True)


@pytest.mark.asyncio
async def test_register_and_unregister_runner():
    """The runner registry should track/untrack runners per project_id."""
    from app.services import assistant_runner

    project_id = uuid4()
    runner = SimpleNamespace(stopped=asyncio.Event())
    await assistant_runner.register_runner(project_id, runner)
    assert assistant_runner.get_runner(project_id) is runner
    await assistant_runner.unregister_runner(project_id)
    assert assistant_runner.get_runner(project_id) is None


@pytest.mark.asyncio
async def test_stop_endpoint_signals_running_runner():
    """POST /stop should set the stopped event on the registered runner."""
    from app.routers.assistant_sse import post_stop
    from app.services.assistant_runner import register_runner

    project_id = uuid4()
    user = _make_user()
    fake_runner = SimpleNamespace(stopped=asyncio.Event())
    await register_runner(project_id, fake_runner)

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = SimpleNamespace(
        id=project_id, owner_id=user.id
    )

    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.assistant_sse.async_session_factory") as factory:
        factory.return_value = ctx
        result = await post_stop(
            body=SimpleNamespace(project_id=str(project_id)),
            user=user,
        )

    assert result == {"stopped": True}
    assert fake_runner.stopped.is_set()
    await register_runner.__self__ if hasattr(register_runner, '__self__') else None
    # Clean up
    from app.services import assistant_runner
    await assistant_runner.unregister_runner(project_id)


@pytest.mark.asyncio
async def test_stop_endpoint_is_idempotent_when_no_runner():
    """Calling /stop with no active run should return stopped=False, not error."""
    from app.routers.assistant_sse import post_stop
    from app.services import assistant_runner

    project_id = uuid4()
    user = _make_user()
    # Ensure no runner is registered for this project
    await assistant_runner.unregister_runner(project_id)

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = SimpleNamespace(
        id=project_id, owner_id=user.id
    )

    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.assistant_sse.async_session_factory") as factory:
        factory.return_value = ctx
        result = await post_stop(
            body=SimpleNamespace(project_id=str(project_id)),
            user=user,
        )

    assert result == {"stopped": False, "reason": "no active run"}


@pytest.mark.asyncio
async def test_stop_endpoint_treats_new_session_as_noop():
    """Stopping an unpersisted new session should not produce a 400."""
    from app.routers.assistant_sse import post_stop

    result = await post_stop(
        body=SimpleNamespace(project_id="new"),
        user=_make_user(),
    )

    assert result == {"stopped": False, "reason": "no persisted session"}


@pytest.mark.asyncio
async def test_stop_endpoint_rejects_non_owned_project():
    """Calling /stop for a project the user doesn't own should 404."""
    from fastapi import HTTPException

    from app.routers.assistant_sse import post_stop

    project_id = uuid4()
    user = _make_user()

    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None  # not found / not owned

    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.assistant_sse.async_session_factory") as factory:
        factory.return_value = ctx
        with pytest.raises(HTTPException) as exc:
            await post_stop(
                body=SimpleNamespace(project_id=str(project_id)),
                user=user,
            )
    assert exc.value.status_code == 404


def test_sse_format_produces_valid_wire_bytes():
    """_sse_format should emit 'event: ...\\ndata: ...\\n\\n' per the SSE spec."""
    from app.routers.assistant_sse import _sse_format

    payload = _sse_format({"type": "log", "level": "info", "message": "hi"})
    text = payload.decode("utf-8")
    # Two leading fields, then blank-line terminator
    lines = text.split("\n")
    assert lines[0].startswith("event: log")
    assert lines[1].startswith("data: ")
    data = json.loads(lines[1][len("data: "):])
    assert data == {"type": "log", "level": "info", "message": "hi"}
    # Must end with a blank line so SSE parsers flush the event
    assert text.endswith("\n\n")


@pytest.mark.asyncio
async def test_runner_emits_to_queue_and_ws_send():
    """emit() should fan out to event_queue (and ws_send if present)."""
    from app.services.assistant_runner import AssistantRunner

    db = AsyncMock()
    runner = AssistantRunner(
        db=db,
        user=SimpleNamespace(id=uuid4()),
        project_id=uuid4(),
        document_id=uuid4(),
        ws_send=AsyncMock(),
        event_queue=asyncio.Queue(),
    )
    event = {"type": "log", "level": "info", "message": "test"}
    await runner.emit(event)

    assert runner.events == [event]
    assert runner.ws_send.await_count == 1
    queued = await asyncio.wait_for(runner.event_queue.get(), timeout=1.0)
    assert queued == event


@pytest.mark.asyncio
async def test_runner_start_runs_turn_in_background():
    """start() should run run_turn as a task and wait_done() should await it."""
    from app.services.assistant_runner import AssistantRunner

    db = AsyncMock()
    db.execute.return_value.scalars.return_value.all.return_value = []

    runner = AssistantRunner(
        db=db,
        user=SimpleNamespace(id=uuid4()),
        project_id=None,
        document_id=None,
        ws_send=None,
    )

    # Patch run_turn to be a no-op coroutine that records it was called
    called = {"n": 0}

    async def fake_run_turn(msg):
        called["n"] += 1

    runner.run_turn = fake_run_turn  # type: ignore
    task = runner.start("hi")
    await runner.wait_done()
    assert called["n"] == 1
    assert task.done()
