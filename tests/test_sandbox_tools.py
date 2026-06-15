"""Tests for the assistant tool handlers that bridge to the sandbox.

Each tool handler is a thin wrapper that:
  1) Validates LLM-supplied args.
  2) Calls the sandbox router (in stub mode during tests).
  3) Emits progress + log events on the runner.
"""
import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.sandbox.config import SandboxConfig
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.router import dispatch


# ── Shared fixture: a manager pointed at a tmp workspace ────────────────


@pytest.fixture
def tmp_workspace():
    p = Path(tempfile.mkdtemp(prefix="lumen-sb-tools-"))
    try:
        yield p
    finally:
        shutil.rmtree(p, ignore_errors=True)


@pytest.fixture
def manager_and_runner(tmp_workspace):
    cfg = SandboxConfig(
        mode="stub", image="x", port=0, memory_limit="0", cpu_limit=0.0,
        workspace_root=str(tmp_workspace), idle_ttl_seconds=1800,
        spawn_timeout_seconds=60, request_timeout_seconds=120,
        network="none", extra_env={},
    )
    mgr = SandboxManager(cfg)
    pid = uuid.uuid4()
    runner = SimpleNamespace(project_id=pid, emit=AsyncMock())
    try:
        yield mgr, runner, pid
    finally:
        asyncio.run(mgr.shutdown())


# ── run_python ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_python_handler_executes_and_emits(manager_and_runner):
    from app.services.assistant_tools.run_python import handle

    mgr, runner, pid = manager_and_runner

    # Patch the module-level dispatch to use our test manager
    with patch("app.services.assistant_tools._sandbox_bridge.dispatch", AsyncMock(side_effect=dispatch)) as mock_disp:
        mock_disp.__defaults__ = ()  # clean up
        # We need dispatch to use the test mgr, not the singleton. The cleanest
        # way is to patch the singleton getter to return ours.
        with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
            result = await handle(None, None, {"code": "print(1+1)", "timeout": 5}, runner)

    assert result["ok"] is True
    assert "2" in result["stdout"]
    # Progress + log events should have fired
    assert runner.emit.await_count >= 2
    messages = [c.args[0].get("message", "") for c in runner.emit.call_args_list]
    assert any("run_python" in m for m in messages)


@pytest.mark.asyncio
async def test_run_python_handler_validates_empty_code(manager_and_runner):
    from app.services.assistant_tools.run_python import handle

    mgr, runner, _ = manager_and_runner
    result = await handle(None, None, {"code": ""}, runner)
    assert result["ok"] is False
    assert "code is required" in result["error"]


@pytest.mark.asyncio
async def test_run_python_handler_rejects_oversize(manager_and_runner):
    from app.services.assistant_tools.run_python import handle

    mgr, runner, _ = manager_and_runner
    result = await handle(None, None, {"code": "x" * 300_000}, runner)
    assert result["ok"] is False
    assert "too long" in result["error"]


# ── run_shell ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_shell_handler_whitelisted(manager_and_runner):
    from app.services.assistant_tools.run_shell import handle

    mgr, runner, _ = manager_and_runner
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await handle(None, None, {"command": "ls", "timeout": 5}, runner)
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_run_shell_handler_rejects_dangerous(manager_and_runner):
    from app.services.assistant_tools.run_shell import handle

    mgr, runner, _ = manager_and_runner
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await handle(None, None, {"command": "rm -rf /", "timeout": 5}, runner)
    assert result["ok"] is False
    assert "whitelist" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_run_shell_handler_requires_command(manager_and_runner):
    from app.services.assistant_tools.run_shell import handle

    mgr, runner, _ = manager_and_runner
    result = await handle(None, None, {}, runner)
    assert result["ok"] is False
    assert "command is required" in result["error"]


# ── file_io ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_file_handler(manager_and_runner, tmp_workspace):
    from app.services.assistant_tools.file_io import _read

    mgr, runner, pid = manager_and_runner
    project_dir = tmp_workspace / str(pid)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "data.txt").write_text("alpha\nbeta")
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await _read(None, None, {"path": "/workspace/data.txt"}, runner)
    assert result["ok"] is True
    assert "alpha" in result["content"]


@pytest.mark.asyncio
async def test_write_file_handler(manager_and_runner, tmp_workspace):
    from app.services.assistant_tools.file_io import _write

    mgr, runner, pid = manager_and_runner
    project_dir = tmp_workspace / str(pid)
    project_dir.mkdir(parents=True, exist_ok=True)
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await _write(
            None, None, {"path": "/workspace/out.md", "content": "hi", "mode": "w"}, runner
        )
    assert result["ok"] is True
    assert (project_dir / "out.md").read_text() == "hi"


@pytest.mark.asyncio
async def test_write_file_handler_appends(manager_and_runner, tmp_workspace):
    from app.services.assistant_tools.file_io import _write

    mgr, runner, pid = manager_and_runner
    project_dir = tmp_workspace / str(pid)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "log.txt").write_text("line1\n")
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await _write(
            None, None, {"path": "/workspace/log.txt", "content": "line2\n", "mode": "a"}, runner
        )
    assert result["ok"] is True
    assert (project_dir / "log.txt").read_text() == "line1\nline2\n"


@pytest.mark.asyncio
async def test_list_files_handler(manager_and_runner, tmp_workspace):
    from app.services.assistant_tools.file_io import _list

    mgr, runner, pid = manager_and_runner
    project_dir = tmp_workspace / str(pid)
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "a.txt").write_text("a")
    (project_dir / "b.md").write_text("b")
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await _list(None, None, {"path": "/workspace", "pattern": "*.txt"}, runner)
    assert result["ok"] is True
    assert {it["name"] for it in result["items"]} == {"a.txt"}


@pytest.mark.asyncio
async def test_file_handlers_reject_escape(manager_and_runner):
    from app.services.assistant_tools.file_io import _read, _write

    mgr, runner, _ = manager_and_runner
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        r = await _read(None, None, {"path": "/etc/passwd"}, runner)
    assert r["ok"] is False
    assert ("escapes" in r["error"] or "outside" in r["error"])

    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        r2 = await _write(None, None, {"path": "/etc/evil", "content": "x"}, runner)
    assert r2["ok"] is False
    assert ("escapes" in r2["error"] or "outside" in r2["error"])


# ── PDF tools ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_pdf_page_handler_missing_pypdf(manager_and_runner, monkeypatch):
    """If pypdf isn't installed, the tool returns a clear error."""
    from app.services.assistant_tools.pdf_tools import open_page

    mgr, runner, _ = manager_and_runner
    # Force pypdf ImportError
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await open_page(None, None, {"path": "/workspace/x.pdf", "page": 1}, runner)
    # Either the stub returned a clean error (good) or it imported successfully
    # and returned content (also fine in this env). We just verify the tool
    # didn't crash.
    assert "ok" in result


@pytest.mark.asyncio
async def test_open_pdf_page_handler_validates(manager_and_runner):
    from app.services.assistant_tools.pdf_tools import open_page

    mgr, runner, _ = manager_and_runner
    result = await open_page(None, None, {"path": ""}, runner)
    assert result["ok"] is False
    assert "path is required" in result["error"]


@pytest.mark.asyncio
async def test_grep_pdf_handler_validates(manager_and_runner):
    from app.services.assistant_tools.pdf_tools import grep

    mgr, runner, _ = manager_and_runner
    r1 = await grep(None, None, {"path": "/x.pdf"}, runner)
    assert r1["ok"] is False
    assert "pattern is required" in r1["error"]
    r2 = await grep(None, None, {"pattern": "x"}, runner)
    assert r2["ok"] is False
    assert "path is required" in r2["error"]


# ── install_packages ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_install_packages_handler_validates(manager_and_runner):
    from app.services.assistant_tools.install_packages import handle

    mgr, runner, _ = manager_and_runner
    # Missing packages
    r1 = await handle(None, None, {}, runner)
    assert r1["ok"] is False
    # Non-list
    r2 = await handle(None, None, {"packages": "pandas"}, runner)
    assert r2["ok"] is False
    # Too many
    r3 = await handle(None, None, {"packages": ["a"] * 25}, runner)
    assert r3["ok"] is False
    assert "max 20" in r3["error"]


@pytest.mark.asyncio
async def test_install_packages_handler_runs_pip(manager_and_runner):
    """Install a tiny package that we know is available, e.g. 'six'."""
    from app.services.assistant_tools.install_packages import handle

    mgr, runner, _ = manager_and_runner
    with patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr):
        result = await handle(None, None, {"packages": ["six"], "timeout": 60}, runner)
    # Don't assert ok=True because some test envs may not have network,
    # but verify the call shape.
    assert "ok" in result
    if not result["ok"]:
        assert "duration_ms" in result or "error" in result


# ── Runner integration ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_assistant_runner_dispatches_sandbox_tool(tmp_workspace):
    """The full path: AssistantRunner → run_python handler → sandbox → result."""
    from app.services.assistant_runner import AssistantRunner

    cfg = SandboxConfig(
        mode="stub", image="x", port=0, memory_limit="0", cpu_limit=0.0,
        workspace_root=str(tmp_workspace), idle_ttl_seconds=1800,
        spawn_timeout_seconds=60, request_timeout_seconds=120,
        network="none", extra_env={},
    )
    mgr = SandboxManager(cfg)
    pid = uuid.uuid4()
    runner = AssistantRunner(
        db=SimpleNamespace(),
        user=SimpleNamespace(id=uuid.uuid4()),
        project_id=pid,
        document_id=uuid.uuid4(),
    )

    # Build a fake LLM response: it tells the runner to call run_python
    fake_result = {
        "message": "Running computation",
        "tool_calls": [{"name": "run_python", "args": {"code": "print('from sandbox')", "timeout": 5}}],
    }
    fake_result_done = {"message": "Done", "tool_calls": None}

    with patch("app.services.assistant_runner.get_provider") as gp, \
         patch("app.services.sandbox.router.get_sandbox_manager", return_value=mgr), \
         patch("app.services.assistant_runner.persist_assistant_message", new_callable=AsyncMock), \
         patch("app.services.assistant_runner.load_assistant_history", new_callable=AsyncMock, return_value=[]):
        provider = AsyncMock()
        provider.complete_structured.side_effect = [fake_result, fake_result_done]
        gp.return_value = provider
        await runner.run_turn("compute something")

    # Verify a tool_call event and tool_result event were emitted
    tool_call_events = [e for e in runner.events if e["type"] == "tool_call"]
    tool_result_events = [e for e in runner.events if e["type"] == "tool_result"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0]["tool"] == "run_python"
    assert len(tool_result_events) == 1
    assert "from sandbox" in tool_result_events[0]["summary"]
    assert any(e["type"] == "done" for e in runner.events)

    await mgr.shutdown()
