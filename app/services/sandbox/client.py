"""HTTP client for talking to a sandbox container.

The client is intentionally tiny: one ``post()`` for endpoints, one
``get_health()`` for liveness. We use ``httpx.AsyncClient`` because the
Lumen backend already uses it everywhere and we get connection pooling
for free.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SandboxClient:
    """Async HTTP client wrapping one sandbox container."""

    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(max_keepalive_connections=2, max_connections=4),
        )

    async def get_health(self) -> dict | None:
        try:
            r = await self._client.get("/health")
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Sandbox health check failed for %s: %s", self.base_url, exc)
            return None

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.post(path, json=payload)
        r.raise_for_status()
        return r.json()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def wait_ready(self, timeout: float = 60.0) -> bool:
        """Poll /health until ok or timeout."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if await self.get_health() is not None:
                return True
            await asyncio.sleep(0.5)
        return False
