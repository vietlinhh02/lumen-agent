"""Tools: open_pdf_page, grep_pdf — sandbox PDF inspection.

These let the agent read a single page or search across an already-
downloaded PDF inside /workspace. Useful for Q&A on a paper without
going through the full RAG pipeline.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from app.services.assistant_tools._sandbox_bridge import call_sandbox_tool

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def open_page(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    path = args.get("path", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    page = int(args.get("page", 1))
    if page < 1:
        return {"ok": False, "error": "page must be >= 1"}
    max_chars = int(args.get("max_chars", 20_000))
    project_id = runner.project_id if runner else None
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"📄 open_pdf_page: {path} page={page}",
                }
            )
    return await call_sandbox_tool(
        "open_pdf_page",
        {"path": path, "page": page, "max_chars": max_chars},
        runner,
        project_id,
        db,
        user,
    )


async def grep(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    path = args.get("path", "")
    pattern = args.get("pattern", "")
    if not path:
        return {"ok": False, "error": "path is required"}
    if not pattern:
        return {"ok": False, "error": "pattern is required"}
    context = int(args.get("context", 120))
    max_matches = int(args.get("max_matches", 20))
    project_id = runner.project_id if runner else None
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"🔍 grep_pdf: {path} /{pattern}/",
                }
            )
    return await call_sandbox_tool(
        "grep_pdf",
        {
            "path": path,
            "pattern": pattern,
            "context": context,
            "max_matches": max_matches,
        },
        runner,
        project_id,
        db,
        user,
    )
