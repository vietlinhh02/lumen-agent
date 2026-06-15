"""Sandbox configuration.

Reads from the process env first, then falls back to the project-root
``.env`` file. This means a user running ``uvicorn app.main:app`` from
a terminal where ``.env`` wasn't sourced still gets the right config;
and the ``/api/sandbox/reload`` endpoint can pick up edits made to
``.env`` while the backend is running.

Defaults are tuned for local dev: ``mode=stub`` means "run subprocesses
in-process" — no Docker required. Set ``LUMEN_SANDBOX_MODE=docker`` for
real per-project container isolation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

_PREFIX = "LUMEN_SANDBOX_"
# A tiny allowlist of LUMEN_SANDBOX_* keys we know about, so we never
# pick up an unrelated future var.
_KNOWN_KEYS = (
    "LUMEN_SANDBOX_MODE",
    "LUMEN_SANDBOX_IMAGE",
    "LUMEN_SANDBOX_PORT",
    "LUMEN_SANDBOX_MEMORY",
    "LUMEN_SANDBOX_CPUS",
    "LUMEN_SANDBOX_WORKSPACE_ROOT",
    "LUMEN_SANDBOX_IDLE_TTL",
    "LUMEN_SANDBOX_SPAWN_TIMEOUT",
    "LUMEN_SANDBOX_REQUEST_TIMEOUT",
    "LUMEN_SANDBOX_NETWORK",
)


def _load_env_file_into_environ() -> None:
    """Read the project .env once and overlay LUMEN_SANDBOX_* into os.environ.

    Order of precedence (highest first):
      1. Already-set os.environ values
      2. The project .env file (next to where the app is launched)
      3. Hard-coded defaults inside ``from_env``
    """
    # The Settings class knows the project root via its env_file path.
    try:
        env_path = Path(get_settings().model_config["env_file"])  # type: ignore[index]
    except Exception:
        env_path = Path(".env")
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in _KNOWN_KEYS:
            continue
        # Don't clobber a value the parent shell already set explicitly.
        os.environ.setdefault(key, value)


def _env(key: str, default: str) -> str:
    return os.environ.get(key) or default


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
        _load_env_file_into_environ()
        return cls(
            mode=_env("LUMEN_SANDBOX_MODE", "stub").lower(),
            image=_env("LUMEN_SANDBOX_IMAGE", "lumen-sandbox:latest"),
            port=int(_env("LUMEN_SANDBOX_PORT", "9090")),
            memory_limit=_env("LUMEN_SANDBOX_MEMORY", "512m"),
            cpu_limit=float(_env("LUMEN_SANDBOX_CPUS", "1.0")),
            workspace_root=_env("LUMEN_SANDBOX_WORKSPACE_ROOT", "data/sandboxes"),
            idle_ttl_seconds=int(_env("LUMEN_SANDBOX_IDLE_TTL", "1800")),
            spawn_timeout_seconds=int(_env("LUMEN_SANDBOX_SPAWN_TIMEOUT", "60")),
            request_timeout_seconds=float(_env("LUMEN_SANDBOX_REQUEST_TIMEOUT", "120")),
            network=_env("LUMEN_SANDBOX_NETWORK", "bridge"),
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


def reload_sandbox_config() -> SandboxConfig:
    """Re-read the environment (incl. .env) and return the new config.

    Useful when LUMEN_SANDBOX_* vars are changed at runtime — the
    admin endpoint /api/sandbox/reload calls this so the UI reflects
    the new mode without restarting the backend.
    """
    global _cached
    # Force a fresh read of the .env file by clearing the overlay for
    # the known keys, then re-read via from_env.
    for k in _KNOWN_KEYS:
        # Only clear if the value was sourced from .env (i.e. we set it
        # in _load_env_file_into_environ). We can't tell that here, so
        # we only clear if it's not set in the parent shell (heuristic:
        # if the value matches what from_env would default to, drop it).
        # Simpler & safe: drop any LUMEN_SANDBOX_* we set previously.
        os.environ.pop(k, None)
    _cached = SandboxConfig.from_env()
    return _cached
