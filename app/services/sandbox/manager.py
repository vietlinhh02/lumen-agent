"""SandboxManager — owns one sandbox per project_id.

Lifecycle:
* :meth:`get_or_create` returns an existing live handle or spins up a new one
  (Docker container in ``docker`` mode, just registers a workspace path in
  ``stub`` mode).
* :meth:`reap_idle` (called periodically by a background task) tears down
  containers whose ``last_used`` is older than ``idle_ttl_seconds``.
* :meth:`destroy` removes a single handle and (in docker mode) ``docker rm -f``s
  the container.

We never block the event loop on Docker operations: ``docker run`` is invoked
in ``asyncio.to_thread`` so the FastAPI server stays responsive.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.sandbox import stub
from app.services.sandbox.client import SandboxClient
from app.services.sandbox.config import SandboxConfig, get_sandbox_config

logger = logging.getLogger(__name__)


@dataclass
class SandboxHandle:
    """One sandbox for one project."""

    project_id: uuid.UUID
    mode: str  # "docker" | "stub"
    container_id: str | None  # docker container id (None in stub mode)
    base_url: str | None  # http://...  (None in stub mode)
    workspace_root: Path  # per-project host directory
    last_used: float = field(default_factory=time.time)
    client: SandboxClient | None = None  # only in docker mode

    def touch(self) -> None:
        self.last_used = time.time()

    def is_alive(self) -> bool:
        return (time.time() - self.last_used) < 24 * 3600

    def is_idle(self, ttl_seconds: int) -> bool:
        return (time.time() - self.last_used) > ttl_seconds


class SandboxManager:
    """Per-project sandbox registry + spawn/reap logic."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or get_sandbox_config()
        self._instances: dict[uuid.UUID, SandboxHandle] = {}
        self._lock = asyncio.Lock()
        self._reaper_task: asyncio.Task | None = None
        # Base path for stub workspaces (also used for docker bind-mounts)
        self._host_root = Path(self.config.workspace_root).resolve()
        self._host_root.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────

    async def get_or_create(self, project_id: uuid.UUID) -> SandboxHandle:
        async with self._lock:
            existing = self._instances.get(project_id)
            if existing and existing.is_alive():
                existing.touch()
                return existing
            handle = await self._spawn(project_id)
            self._instances[project_id] = handle
            return handle

    async def destroy(self, project_id: uuid.UUID) -> bool:
        async with self._lock:
            handle = self._instances.pop(project_id, None)
            if handle is None:
                return False
            await self._teardown(handle)
            return True

    async def reap_idle(self) -> int:
        """Tear down handles idle longer than ``idle_ttl_seconds``."""
        async with self._lock:
            victims = [
                h for h in self._instances.values() if h.is_idle(self.config.idle_ttl_seconds)
            ]
            for h in victims:
                self._instances.pop(h.project_id, None)
                await self._teardown(h)
        if victims:
            logger.info("Reaped %d idle sandbox(es)", len(victims))
        return len(victims)

    def start_reaper(self, interval_seconds: int = 60) -> None:
        """Start a background task that calls reap_idle periodically."""
        if self._reaper_task is not None and not self._reaper_task.done():
            return
        self._reaper_task = asyncio.create_task(self._reaper_loop(interval_seconds))

    async def stop_reaper(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper_task

    async def shutdown(self) -> None:
        await self.stop_reaper()
        async with self._lock:
            handles = list(self._instances.values())
            self._instances.clear()
        for h in handles:
            await self._teardown(h)

    def get(self, project_id: uuid.UUID) -> SandboxHandle | None:
        h = self._instances.get(project_id)
        if h:
            h.touch()
        return h

    def snapshot(self) -> list[SandboxHandle]:
        """Return a list of all currently-alive handles (read-only)."""
        return list(self._instances.values())

    # ── Execute endpoint (router uses this) ───────────────────────────

    async def execute(
        self,
        handle: SandboxHandle,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a sandbox endpoint, either in docker (HTTP) or stub (in-proc)."""
        handle.touch()
        if handle.mode == "stub" or handle.client is None:
            return await self._execute_stub(handle, endpoint, payload)
        try:
            return await handle.client.post(endpoint, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Sandbox HTTP %s failed: %s; falling back to stub",
                endpoint,
                exc,
            )
            return await self._execute_stub(handle, endpoint, payload)

    # ── Internals ──────────────────────────────────────────────────────

    async def _spawn(self, project_id: uuid.UUID) -> SandboxHandle:
        workspace = self._host_root / str(project_id)
        workspace.mkdir(parents=True, exist_ok=True)
        if self.config.mode == "docker":
            return await self._spawn_docker(project_id, workspace)
        # stub mode
        return SandboxHandle(
            project_id=project_id,
            mode="stub",
            container_id=None,
            base_url=None,
            workspace_root=workspace,
        )

    async def _spawn_docker(self, project_id: uuid.UUID, workspace: Path) -> SandboxHandle:
        if not shutil.which("docker"):
            logger.warning("Sandbox mode=docker but docker CLI not found; falling back to stub")
            return SandboxHandle(
                project_id=project_id,
                mode="stub",
                container_id=None,
                base_url=None,
                workspace_root=workspace,
            )
        container_name = f"lumen-sb-{project_id}"
        # docker run flags:
        #   --rm           auto-cleanup if we miss a teardown
        #   -d             detached
        #   --name         deterministic name so we can reattach
        #   --network none by default; opt-in via LUMEN_SANDBOX_NETWORK
        #   -m / --cpus    resource limits
        #   -v workspace:/workspace:rw  per-project bind mount
        # We use -P (--publish-all) so docker maps the image's EXPOSE 9090
        # to a random host port. We then discover it via docker inspect.
        # `--network none` is the secure default (no net); switch to
        # `host` for dev if the agent needs to talk to localhost services.
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "-m",
            self.config.memory_limit,
            "--cpus",
            str(self.config.cpu_limit),
            "--network",
            self.config.network,
            "-v",
            f"{workspace}:/workspace:rw",
            "-P",  # publish all EXPOSEd ports to random host ports
            self.config.image,
        ]
        try:
            container_id = (await asyncio.to_thread(_run_cmd, cmd)).strip()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to spawn sandbox container")
            raise RuntimeError(f"docker run failed: {exc}") from exc
        # Discover the mapped port (we asked for random)
        port = await asyncio.to_thread(_discover_port, container_id, self.config.port)
        if port is None:
            await asyncio.to_thread(_run_cmd, ["docker", "rm", "-f", container_id])
            raise RuntimeError("could not discover mapped port for sandbox")
        base_url = f"http://127.0.0.1:{port}"
        client = SandboxClient(base_url, timeout=self.config.request_timeout_seconds)
        if not await client.wait_ready(self.config.spawn_timeout_seconds):
            await asyncio.to_thread(_run_cmd, ["docker", "rm", "-f", container_id])
            await client.aclose()
            raise RuntimeError("sandbox failed health check within timeout")
        logger.info("Spawned sandbox %s on %s (workspace=%s)", container_name, base_url, workspace)
        return SandboxHandle(
            project_id=project_id,
            mode="docker",
            container_id=container_id,
            base_url=base_url,
            workspace_root=workspace,
            client=client,
        )

    async def _teardown(self, handle: SandboxHandle) -> None:
        if handle.client is not None:
            with contextlib.suppress(Exception):
                await handle.client.aclose()
        if handle.container_id:
            try:
                await asyncio.to_thread(_run_cmd, ["docker", "rm", "-f", handle.container_id])
            except Exception as exc:  # noqa: BLE001
                logger.debug("docker rm failed for %s: %s", handle.container_id, exc)

    async def _execute_stub(
        self, handle: SandboxHandle, endpoint: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        ws = handle.workspace_root
        if endpoint == "/python":
            code = payload.get("code", "")
            timeout = int(payload.get("timeout", 30))
            return await stub.run_python(ws, code, timeout)
        if endpoint == "/shell":
            command = payload.get("command", "")
            timeout = int(payload.get("timeout", 30))
            return await stub.run_shell(ws, command, timeout)
        if endpoint == "/file/read":
            path = payload.get("path", "")
            max_bytes = int(payload.get("max_bytes", 200_000))
            return await stub.file_read(ws, path, max_bytes)
        if endpoint == "/file/write":
            return await stub.file_write(
                ws,
                payload.get("path", ""),
                payload.get("content", ""),
                payload.get("mode", "w"),
            )
        if endpoint == "/file/list":
            return await stub.file_list(
                ws, payload.get("path", "/workspace"), payload.get("pattern")
            )
        if endpoint == "/pdf/page":
            return await stub.pdf_page(
                ws,
                payload.get("path", ""),
                int(payload.get("page", 1)),
                int(payload.get("max_chars", 20_000)),
            )
        if endpoint == "/pdf/grep":
            return await stub.pdf_grep(
                ws,
                payload.get("path", ""),
                payload.get("pattern", ""),
                int(payload.get("context", 120)),
                int(payload.get("max_matches", 20)),
            )
        if endpoint == "/package/install":
            return await stub.pip_install(
                payload.get("packages", []), int(payload.get("timeout", 120))
            )
        if endpoint == "/health":
            return await stub.health(ws)
        return {"ok": False, "error": f"unknown endpoint: {endpoint}"}

    async def _reaper_loop(self, interval: int) -> None:
        while True:
            try:
                await asyncio.sleep(interval)
                await self.reap_idle()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                logger.exception("Reaper loop crashed; will retry")


# ── Module-level singleton + helpers ───────────────────────────────────────


def _run_cmd(cmd: list[str]) -> str:
    import subprocess

    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _discover_port(container_id: str, container_port: int) -> int | None:
    """Find the host port docker mapped to *container_port*/tcp.

    We use docker inspect's NetworkSettings.Ports map. If the container
    runs with `--network host`, the container port == host port.
    """
    import json
    import subprocess

    try:
        out = subprocess.run(
            [
                "docker",
                "inspect",
                container_id,
                "--format",
                "{{json .NetworkSettings.Ports}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        logger.debug("docker inspect failed: %s", exc)
        return None
    if not out.strip():
        return None
    try:
        ports = json.loads(out)
    except json.JSONDecodeError:
        return None
    key = f"{container_port}/tcp"
    bindings = ports.get(key)
    if bindings:
        try:
            return int(bindings[0]["HostPort"])
        except (KeyError, IndexError, ValueError):
            pass
    # Fallback: maybe host network → ports is empty, assume same port
    return container_port


_singleton: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    global _singleton
    if _singleton is None:
        _singleton = SandboxManager()
    return _singleton


async def reset_sandbox_manager() -> None:
    """Used by tests to reset module state between runs."""
    global _singleton
    if _singleton is not None:
        await _singleton.shutdown()
    _singleton = None
