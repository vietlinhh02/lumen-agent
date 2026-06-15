"""Tool: run_python — execute Python code in the per-project sandbox.

Use this for ad-hoc analysis, parsing, computations, etc. The code runs
in a subprocess inside the sandbox container (or the local stub if the
sandbox is in stub mode). stdout/stderr are returned in the result.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from app.services.assistant_tools._sandbox_bridge import call_sandbox_tool

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    code = args.get("code", "")
    if not code:
        return {"ok": False, "error": "code is required"}
    if len(code) > 200_000:
        return {"ok": False, "error": "code too long (>200K chars)"}
    timeout = int(args.get("timeout", 30))
    project_id = runner.project_id if runner else None
    if runner:
        with contextlib.suppress(Exception):
            preview = code.splitlines()[0][:80] if code.splitlines() else ""
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"🐍 run_python: {preview!r} (timeout={timeout}s)",
                }
            )
    result = await call_sandbox_tool(
        "run_python", {"code": code, "timeout": timeout}, runner, project_id, db, user
    )
    if result.get("ok") and result.get("stdout") and runner:
        with contextlib.suppress(Exception):
            stdout = result["stdout"]
            preview = stdout if len(stdout) <= 400 else stdout[:400] + "…[truncated]"
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"   stdout: {preview}",
                }
            )
    return result
