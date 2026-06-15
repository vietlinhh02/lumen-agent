"""Tool router — every tool is either a local in-process handler or a
remote sandbox call. The assistant runner looks up tools through this
router so tool dispatch is uniform regardless of where the code runs.

LOCAL TOOLS (fast path):
  - create_project, search_papers, save_paper_to_project, save_papers_batch,
    trigger_normalization, generate_matrix, detect_gaps, detect_conflicts,
    generate_report, edit_report_section, qa_search_papers

SANDBOX TOOLS (sandbox path):
  - run_python, run_shell, read_file, write_file, list_files, open_pdf_page,
    grep_pdf, install_packages
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from typing import Any

from app.services.sandbox.config import get_sandbox_config
from app.services.sandbox.manager import SandboxManager, get_sandbox_manager

logger = logging.getLogger(__name__)


# Map tool name → (kind, ref) where ref is a dotted import path for local
# tools, or a sandbox endpoint for sandbox tools.
TOOL_REGISTRY: dict[str, tuple[str, str]] = {
    # Local fast path
    "create_project": ("local", "app.services.assistant_tools.create_project.handle"),
    "search_papers": ("local", "app.services.assistant_tools.search_papers.handle"),
    "save_paper_to_project": ("local", "app.services.assistant_tools.save_paper.handle"),
    "save_papers_batch": ("local", "app.services.assistant_tools.save_papers_batch.handle"),
    "generate_matrix": ("local", "app.services.assistant_tools.generate_matrix.handle"),
    "trigger_normalization": ("local", "app.services.assistant_tools.trigger_normalization.handle"),
    "detect_gaps": ("local", "app.services.assistant_tools.detect_gaps.handle"),
    "detect_conflicts": ("local", "app.services.assistant_tools.detect_conflicts.handle"),
    "generate_report": ("local", "app.services.assistant_tools.generate_report.handle"),
    "edit_report_section": ("local", "app.services.assistant_tools.edit_report_section.handle"),
    "qa_search_papers": ("local", "app.services.assistant_tools.qa_search_papers.handle"),
    # Sandbox path
    "run_python": ("sandbox", "/python"),
    "run_shell": ("sandbox", "/shell"),
    "read_file": ("sandbox", "/file/read"),
    "write_file": ("sandbox", "/file/write"),
    "list_files": ("sandbox", "/file/list"),
    "open_pdf_page": ("sandbox", "/pdf/page"),
    "grep_pdf": ("sandbox", "/pdf/grep"),
    "install_packages": ("sandbox", "/package/install"),
}


_LOCAL_CACHE: dict[str, Any] = {}


def _resolve_local(ref: str):
    if ref in _LOCAL_CACHE:
        return _LOCAL_CACHE[ref]
    module_path, _, attr = ref.rpartition(".")
    import importlib

    mod = importlib.import_module(module_path)
    handler = getattr(mod, attr)
    _LOCAL_CACHE[ref] = handler
    return handler


def is_known_tool(name: str) -> bool:
    return name in TOOL_REGISTRY


def list_tools() -> list[str]:
    return list(TOOL_REGISTRY.keys())


def path_for(name: str) -> str:
    """Return 'local' or 'sandbox' for the given tool."""
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        raise KeyError(f"unknown tool: {name}")
    return entry[0]


async def dispatch(
    name: str,
    *,
    db,
    user,
    args: dict[str, Any],
    runner,
    project_id: uuid.UUID | None,
    manager: SandboxManager | None = None,
) -> dict[str, Any]:
    """Dispatch a tool call to either a local handler or the sandbox.

    The signature matches what ``AssistantRunner`` already passes to
    local handlers (``db, user, args, runner``). Sandbox tools ignore
    ``db/user`` and instead use ``project_id`` to find the right sandbox.
    """
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return {"error": f"unknown tool: {name}"}
    kind, ref = entry
    if kind == "local":
        handler = _resolve_local(ref)
        return await handler(db, user, args, runner)
    # sandbox
    cfg = get_sandbox_config()
    if not cfg.enabled:
        return {
            "error": (
                "sandbox is disabled (set LUMEN_SANDBOX_MODE=docker or "
                "LUMEN_SANDBOX_MODE=stub to enable)"
            ),
            "tool": name,
        }
    if project_id is None:
        return {
            "error": (
                f"sandbox tool '{name}' requires an active project. "
                "Create a project first (create_project)."
            ),
        }
    mgr = manager or get_sandbox_manager()
    handle = await mgr.get_or_create(project_id)
    # Translate assistant args → sandbox endpoint payload
    payload = _args_to_payload(name, args)
    if runner is not None:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "progress",
                    "step": name,
                    "status": "running",
                    "percent": 5,
                    "label": f"Sandbox: {name}",
                }
            )
    result = await mgr.execute(handle, ref, payload)
    if runner is not None:
        with contextlib.suppress(Exception):
            await runner.emit(
                {
                    "type": "progress",
                    "step": name,
                    "status": "done" if result.get("ok") else "failed",
                    "percent": 100,
                    "label": f"{name}: ok" if result.get("ok") else f"{name}: error",
                }
            )
    return result


def _args_to_payload(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Translate LLM-facing tool args into the sandbox endpoint schema.

    Keeping this map local to the router means each tool handler stays
    tiny — it just unpacks ``args`` and emits a sandbox-shaped payload.
    """
    if tool_name == "run_python":
        return {"code": args.get("code", ""), "timeout": int(args.get("timeout", 30))}
    if tool_name == "run_shell":
        cmd = args.get("command", "")
        timeout = int(args.get("timeout", 30))
        return {"command": cmd, "timeout": timeout}
    if tool_name == "read_file":
        return {
            "path": args.get("path", ""),
            "max_bytes": int(args.get("max_bytes", 200_000)),
        }
    if tool_name == "write_file":
        return {
            "path": args.get("path", ""),
            "content": args.get("content", ""),
            "mode": args.get("mode", "w"),
        }
    if tool_name == "list_files":
        return {
            "path": args.get("path", "/workspace"),
            "pattern": args.get("pattern"),
        }
    if tool_name == "open_pdf_page":
        return {
            "path": args.get("path", ""),
            "page": int(args.get("page", 1)),
            "max_chars": int(args.get("max_chars", 20_000)),
        }
    if tool_name == "grep_pdf":
        return {
            "path": args.get("path", ""),
            "pattern": args.get("pattern", ""),
            "context": int(args.get("context", 120)),
            "max_matches": int(args.get("max_matches", 20)),
        }
    if tool_name == "install_packages":
        return {
            "packages": args.get("packages", []),
            "timeout": int(args.get("timeout", 120)),
        }
    return dict(args)
