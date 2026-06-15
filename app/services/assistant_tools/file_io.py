"""Tools: read_file, write_file, list_files — sandbox file I/O.

All paths are relative to /workspace inside the sandbox (or the
per-project host directory in stub mode). The sandbox rejects paths
that escape the workspace.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from app.services.assistant_tools._sandbox_bridge import call_sandbox_tool

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def _read(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    path = args.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    max_bytes = int(args.get("max_bytes", 200_000))
    project_id = runner.project_id if runner else None
    return await call_sandbox_tool(
        "read_file",
        {"path": path, "max_bytes": max_bytes},
        runner,
        project_id,
        db,
        user,
    )


async def _write(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    path = args.get("path", "")
    content = args.get("content", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    mode = args.get("mode", "w")
    if mode not in {"w", "a"}:
        return {"ok": False, "error": "mode must be 'w' or 'a'"}
    if len(content) > 5 * 1024 * 1024:
        return {"ok": False, "error": "content too large (>5MiB)"}
    project_id = runner.project_id if runner else None
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"📝 write_file: {path} ({len(content)} bytes, mode={mode})",
                }
            )
    return await call_sandbox_tool(
        "write_file",
        {"path": path, "content": content, "mode": mode},
        runner,
        project_id,
        db,
        user,
    )


async def _list(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    path = args.get("path", "/workspace")
    pattern = args.get("pattern")
    project_id = runner.project_id if runner else None
    return await call_sandbox_tool(
        "list_files",
        {"path": path, "pattern": pattern},
        runner,
        project_id,
        db,
        user,
    )
