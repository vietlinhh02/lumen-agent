"""Tool: run_shell — run a whitelisted shell command in the sandbox.

The sandbox enforces a command whitelist (ls, cat, grep, wc, jq, …).
Anything else is rejected before it ever runs. Use this for quick
inspection of files in /workspace.
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
    command = args.get("command", "")
    if not command:
        return {"ok": False, "error": "command is required"}
    timeout = int(args.get("timeout", 30))
    project_id = runner.project_id if runner else None
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"💻 run_shell: {command[:120]!r}",
                }
            )
    return await call_sandbox_tool(
        "run_shell", {"command": command, "timeout": timeout}, runner, project_id, db, user
    )
