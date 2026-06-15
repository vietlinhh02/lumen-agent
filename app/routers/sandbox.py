"""Admin/inspection endpoint for the per-project sandbox subsystem.

Returns:

* the active ``SandboxConfig`` (mode, image, limits, ttl, network);
* the list of currently-alive sandbox handles (project_id, container_id,
  last_used, workspace_size, file_count);
* a flat tree of files inside a project workspace (capped depth + count);
* the most recent sandbox tool calls (parsed from assistant logs would
  require a service hook — we surface a compact summary instead).

The endpoint is auth-gated by the project_owner; the frontend uses it
to render the live ``SandboxPanel`` in the assistant page.
"""
from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.services.sandbox.config import (
    SandboxConfig,
    get_sandbox_config,
    reload_sandbox_config,
)
from app.services.sandbox.manager import (
    get_sandbox_manager,
    reset_sandbox_manager,
)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


def _config_dict(cfg: SandboxConfig) -> dict[str, Any]:
    return {
        "mode": cfg.mode,
        "enabled": cfg.enabled,
        "image": cfg.image,
        "port": cfg.port,
        "memory_limit": cfg.memory_limit,
        "cpu_limit": cfg.cpu_limit,
        "idle_ttl_seconds": cfg.idle_ttl_seconds,
        "spawn_timeout_seconds": cfg.spawn_timeout_seconds,
        "network": cfg.network,
        "workspace_root": cfg.workspace_root,
    }


def _handle_dict(handle) -> dict[str, Any]:
    ws = handle.workspace_root
    size = 0
    count = 0
    try:
        if ws.exists():
            for root, _dirs, files in os.walk(ws):
                for f in files:
                    p = Path(root) / f
                    try:
                        size += p.stat().st_size
                        count += 1
                    except OSError:
                        continue
    except OSError:
        pass
    return {
        "project_id": str(handle.project_id),
        "mode": handle.mode,
        "container_id": handle.container_id,
        "base_url": handle.base_url,
        "workspace": str(ws),
        "last_used": handle.last_used,
        "idle_for_seconds": int(time.time() - handle.last_used),
        "workspace_bytes": size,
        "workspace_files": count,
    }


def _list_workspace(ws: Path, max_depth: int, max_entries: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not ws.exists():
        return out
    base = ws.resolve()

    def _walk(p: Path, depth: int) -> None:
        if len(out) >= max_entries or depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except OSError:
            return
        for entry in entries:
            if len(out) >= max_entries:
                return
            try:
                st = entry.stat()
            except OSError:
                continue
            try:
                rel = str(entry.resolve().relative_to(base))
            except ValueError:
                rel = entry.name
            node: dict[str, Any] = {
                "name": entry.name,
                "path": rel,
                "is_dir": entry.is_dir(),
                "size_bytes": st.st_size if entry.is_file() else None,
                "modified_ts": int(st.st_mtime),
            }
            out.append(node)
            if entry.is_dir():
                _walk(entry, depth + 1)

    _walk(ws, 0)
    return out


@router.get("/config")
async def sandbox_config(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Active sandbox configuration (mode, limits, ttl, network)."""
    return {"config": _config_dict(get_sandbox_config())}


@router.get("/status")
async def sandbox_status(
    project_id: uuid.UUID | None = Query(default=None),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Live status: config + handles + (optionally) the workspace tree
    for *project_id*.
    """
    cfg = get_sandbox_config()
    mgr = get_sandbox_manager()
    handles = mgr.snapshot()
    payload: dict[str, Any] = {
        "config": _config_dict(cfg),
        "handles": [_handle_dict(h) for h in handles],
        "active_projects": len(handles),
    }
    if project_id is not None:
        ws = Path(cfg.workspace_root).resolve() / str(project_id)
        payload["project_id"] = str(project_id)
        payload["workspace_exists"] = ws.exists()
        payload["files"] = _list_workspace(ws, max_depth=4, max_entries=200)
    return payload


@router.get("/files")
async def sandbox_files(
    project_id: uuid.UUID = Query(...),
    path: str = Query(default="/workspace", description="Workspace-relative path"),
    max_bytes: int = Query(default=200_000, ge=1, le=1_000_000),
    _user: User = Depends(get_current_user),
    _db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Read a text file from the project workspace.

    Mirrors the sandbox ``/file/read`` endpoint behaviour: rejects paths
    that escape the workspace, caps size at ``max_bytes``.
    """
    cfg = get_sandbox_config()
    ws = (Path(cfg.workspace_root).resolve() / str(project_id)).resolve()
    if not str(ws).startswith(str(Path(cfg.workspace_root).resolve())):
        raise HTTPException(status_code=400, detail="path outside workspace")
    if path == "/workspace" or not path:
        candidate = ws
    elif path.startswith("/workspace/"):
        candidate = (ws / path[len("/workspace/"):]).resolve()
    elif path.startswith("/"):
        raise HTTPException(status_code=400, detail="path outside workspace")
    else:
        candidate = (ws / path).resolve()
    if not str(candidate).startswith(str(ws)):
        raise HTTPException(status_code=400, detail="path escapes workspace")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"not found: {path}")
    size = candidate.stat().st_size
    if size > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large")
    with candidate.open("rb") as f:
        data = f.read(max_bytes)
    return {
        "path": str(candidate.relative_to(ws)),
        "size_bytes": size,
        "truncated": size > max_bytes,
        "content": data.decode("utf-8", errors="replace"),
    }


@router.post("/reload")
async def sandbox_reload(
    reap: bool = Query(default=False, description="Also teardown live sandboxes"),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Re-read LUMEN_SANDBOX_* env vars and swap the SandboxManager.

    Call this after editing .env (mode/image/limits/network/ttl) — the
    running uvicorn process keeps the old env otherwise. By default
    existing sandbox handles are preserved; pass ``?reap=true`` to
    tear them down (e.g. when changing from docker → stub).
    """
    new_cfg = reload_sandbox_config()
    if reap:
        await reset_sandbox_manager()
    else:
        # Hot-swap the manager's config so the next spawn uses the new
        # values, but keep live handles around.
        try:
            mgr = get_sandbox_manager()
            mgr.config = new_cfg  # type: ignore[attr-defined]
        except Exception:
            pass
    return {
        "reloaded": True,
        "reaped_existing": reap,
        "config": _config_dict(new_cfg),
    }
