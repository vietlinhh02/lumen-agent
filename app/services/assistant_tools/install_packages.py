"""Tool: install_packages — pip-install Python packages in the sandbox.

The agent should only use this when an analysis task genuinely needs a
package that isn't pre-installed (e.g. pandas, scikit-learn, requests).
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
    packages = args.get("packages", [])
    if not packages:
        return {"ok": False, "error": "packages list is required"}
    if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
        return {"ok": False, "error": "packages must be a list of strings"}
    if len(packages) > 20:
        return {"ok": False, "error": "too many packages (max 20 per call)"}
    timeout = int(args.get("timeout", 120))
    project_id = runner.project_id if runner else None
    if runner:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "log",
                    "level": "info",
                    "message": f"📦 install_packages: {packages}",
                }
            )
    return await call_sandbox_tool(
        "install_packages",
        {"packages": packages, "timeout": timeout},
        runner,
        project_id,
        db,
        user,
    )
