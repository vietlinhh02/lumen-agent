"""Helpers shared by every sandbox-backed tool handler.

Each sandbox tool (run_python, run_shell, …) is a thin wrapper that:
  1) Validates the LLM-supplied args.
  2) Asks the sandbox router to dispatch the call.
  3) Emits the standard progress / log events so the SSE stream stays
     consistent with the in-process tools.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from app.services.sandbox.router import dispatch

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def call_sandbox_tool(
    tool_name: str,
    args: dict[str, Any],
    runner: AssistantRunner | None,
    project_id,
    db,
    user,
) -> dict[str, Any]:
    """Run a sandbox tool with the standard event lifecycle.

    Returns the sandbox response dict (which may contain 'ok', 'error',
    'stdout', 'stderr', etc.). On infra-level failures we wrap the
    error into a friendly message for the LLM.
    """
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "progress",
                    "step": tool_name,
                    "status": "running",
                    "percent": 5,
                    "label": f"Sandbox: {tool_name}",
                }
            )
    result = await dispatch(
        tool_name,
        db=db,
        user=user,
        args=args,
        runner=runner,
        project_id=project_id,
    )
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "progress",
                    "step": tool_name,
                    "status": "done" if result.get("ok") else "failed",
                    "percent": 100,
                    "label": f"{tool_name}: ok" if result.get("ok") else f"{tool_name}: error",
                }
            )
    return result
