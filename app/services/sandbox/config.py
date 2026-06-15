"""Sandbox configuration.

Reads from environment / Settings. Defaults are tuned for local dev:
sandbox mode "stub" means "run subprocesses in-process" — no Docker
required. Set ``LUMEN_SANDBOX_MODE=docker`` for production.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxConfig:
    mode: str  # "docker" | "stub" | "disabled"
    image: str  # docker image name
    port: int  # container port
    memory_limit: str  # docker -m flag
    cpu_limit: float  # docker --cpus flag
    workspace_root: str  # host path for per-project workspaces
    idle_ttl_seconds: int  # reap containers idle longer than this
    spawn_timeout_seconds: int  # how long to wait for /health
    request_timeout_seconds: float  # HTTP client timeout
    network: str  # docker --network flag
    extra_env: dict  # extra env vars injected into the container

    @classmethod
    def from_env(cls) -> SandboxConfig:
        return cls(
            mode=os.environ.get("LUMEN_SANDBOX_MODE", "stub").lower(),
            image=os.environ.get("LUMEN_SANDBOX_IMAGE", "lumen-sandbox:latest"),
            port=int(os.environ.get("LUMEN_SANDBOX_PORT", "9090")),
            memory_limit=os.environ.get("LUMEN_SANDBOX_MEMORY", "512m"),
            cpu_limit=float(os.environ.get("LUMEN_SANDBOX_CPUS", "1.0")),
            workspace_root=os.environ.get("LUMEN_SANDBOX_WORKSPACE_ROOT", "data/sandboxes"),
            idle_ttl_seconds=int(os.environ.get("LUMEN_SANDBOX_IDLE_TTL", "1800")),
            spawn_timeout_seconds=int(os.environ.get("LUMEN_SANDBOX_SPAWN_TIMEOUT", "60")),
            request_timeout_seconds=float(os.environ.get("LUMEN_SANDBOX_REQUEST_TIMEOUT", "120")),
            network=os.environ.get("LUMEN_SANDBOX_NETWORK", "bridge"),
            extra_env={},
        )

    @property
    def enabled(self) -> bool:
        return self.mode in {"docker", "stub"}


_cached: SandboxConfig | None = None


def get_sandbox_config() -> SandboxConfig:
    global _cached
    if _cached is None:
        _cached = SandboxConfig.from_env()
    return _cached
