"""Cross-encoder reranker.

Provider priority:
1. `JINA_API_KEY` set → calls `https://api.jina.ai/v1/rerank`
   (preferred: 100 RPM free tier, multilingual, supports jina-reranker-v3/v2).
2. `COHERE_API_KEY` set → calls `https://api.cohere.com/v2/rerank`
   (legacy fallback: only 10 RPM on the free trial tier).
3. Neither key set → identity fallback (descending index scores).
"""

from __future__ import annotations

import asyncio
import logging
import random

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_rerank_client: httpx.AsyncClient | None = None
_cohere_rate_lock = asyncio.Lock()
_cohere_window_started: float = 0.0
_cohere_window_requests: int = 0
_jina_rerank_rate_lock = asyncio.Lock()
_jina_rerank_window_started: float = 0.0
_jina_rerank_window_requests: int = 0


async def init_rerank_client() -> None:
    """Initialize the shared async HTTP client for reranking."""
    global _rerank_client
    if _rerank_client is not None:
        return
    _rerank_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0),
        limits=httpx.Limits(
            max_keepalive_connections=10,
            max_connections=30,
            keepalive_expiry=30.0,
        ),
    )
    logger.info("Reranker async HTTP client initialized")


async def close_rerank_client() -> None:
    """Close the shared reranker HTTP client."""
    global _rerank_client
    if _rerank_client is not None:
        await _rerank_client.aclose()
        _rerank_client = None
        logger.info("Reranker async HTTP client closed")


async def rerank(
    query: str,
    documents: list[str],
    top_k: int | None = None,
    max_length: int = 512,
) -> list[tuple[int, float]]:
    """Rerank documents by relevance to `query`.

    Args:
        query: The search query.
        documents: List of document texts to rerank.
        top_k: If set, return only top_k results. Otherwise return all.
        max_length: Maximum token length (unused, API handles truncation).

    Returns:
        List of (original_index, score) sorted by score descending.
    """
    if not documents:
        return []
    if not query.strip():
        return [(i, 0.0) for i in range(len(documents))]

    settings = get_settings()

    # Prefer Jina when configured (10x the free-tier throughput of Cohere).
    if settings.jina_api_key:
        result = await _call_jina_rerank(query, documents, settings, top_k)
        if result is not None:
            return result
        logger.warning("Jina rerank failed; falling back to Cohere/identity")

    if settings.cohere_api_key:
        result = await _call_cohere_rerank(query, documents, settings, top_k)
        if result is not None:
            return result

    if not settings.jina_api_key and not settings.cohere_api_key:
        logger.warning(
            "No reranker API key configured (set JINA_API_KEY or COHERE_API_KEY); "
            "using identity fallback"
        )

    fallback = [(i, float(len(documents) - i)) for i in range(len(documents))]
    return fallback[:top_k] if top_k is not None else fallback


# ── Jina (api.jina.ai/v1/rerank) ──────────────────────────────────────────────


async def _call_jina_rerank(
    query: str,
    documents: list[str],
    settings: Settings,
    top_k: int | None,
) -> list[tuple[int, float]] | None:
    """Call Jina rerank endpoint. Returns None on hard failure to allow fallback."""
    client = await _get_client()
    headers = {
        "Authorization": f"Bearer {settings.jina_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, object] = {
        "model": settings.jina_rerank_model,
        "query": query,
        "documents": documents,
        "top_n": top_k if top_k is not None else len(documents),
        "return_documents": False,
    }

    await _respect_jina_rerank_rate_limit(settings)
    for attempt in range(3):
        try:
            resp = await client.post(settings.jina_rerank_url, json=payload, headers=headers)
            if resp.status_code == 429:
                await _sleep_for_retry(attempt, resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            # Jina returns: {"results": [{"index": int, "relevance_score": float}, ...]}
            indexed = [
                (int(r["index"]), float(r["relevance_score"]))
                for r in data.get("results", [])
            ]
            indexed.sort(key=lambda x: x[1], reverse=True)
            return indexed
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Jina rerank HTTP %s: %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            if exc.response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                await _sleep_for_retry(attempt, exc.response)
                continue
            return None
        except Exception as exc:
            logger.error("Jina rerank failed: %s", exc)
            if attempt < 2:
                await _sleep_for_retry(attempt, None)
                continue
            return None
    return None


async def _respect_jina_rerank_rate_limit(settings: Settings) -> None:
    """Throttle Jina rerank calls to N requests / 60s (free tier: 100 RPM)."""
    global _jina_rerank_window_requests, _jina_rerank_window_started

    rpm = max(1, settings.jina_rerank_requests_per_minute)
    while True:
        async with _jina_rerank_rate_lock:
            now = asyncio.get_running_loop().time()
            if now - _jina_rerank_window_started >= 60:
                _jina_rerank_window_started = now
                _jina_rerank_window_requests = 0
            if _jina_rerank_window_requests + 1 <= rpm:
                _jina_rerank_window_requests += 1
                return
            sleep_for = max(1.0, 60 - (now - _jina_rerank_window_started))
        logger.info("Jina rerank rate limit reached; sleeping %.1fs", sleep_for)
        await asyncio.sleep(sleep_for)


# ── Cohere direct (api.cohere.com/v2/rerank) ────────────────────────────────


async def _call_cohere_rerank(
    query: str,
    documents: list[str],
    settings: Settings,
    top_k: int | None,
) -> list[tuple[int, float]] | None:
    """Call Cohere v2 rerank endpoint (free trial tier)."""
    client = await _get_client()
    url = settings.cohere_rerank_url
    headers = {
        "Authorization": f"Bearer {settings.cohere_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, object] = {
        "model": settings.cohere_rerank_model,
        "query": query,
        "documents": [{"text": d} for d in documents],
    }
    if top_k is not None:
        payload["top_n"] = top_k

    await _respect_cohere_rate_limit(settings)
    for attempt in range(3):
        try:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 429:
                await _sleep_for_retry(attempt, resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            # Cohere v2 returns: {"results": [{"index": int, "relevance_score": float}, ...]}
            results = data.get("results", [])
            indexed = [(int(r["index"]), float(r["relevance_score"])) for r in results]
            indexed.sort(key=lambda x: x[1], reverse=True)
            return indexed
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Cohere rerank HTTP %s: %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            if exc.response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                await _sleep_for_retry(attempt, exc.response)
                continue
            return None
        except Exception as exc:
            logger.error("Cohere rerank failed: %s", exc)
            if attempt < 2:
                await _sleep_for_retry(attempt, None)
                continue
            return None
    return None


async def _respect_cohere_rate_limit(settings: Settings) -> None:
    """Throttle Cohere free-tier calls to N requests / 60s."""
    global _cohere_window_requests, _cohere_window_started

    rpm = max(1, settings.cohere_rerank_requests_per_minute)
    while True:
        async with _cohere_rate_lock:
            now = asyncio.get_running_loop().time()
            if now - _cohere_window_started >= 60:
                _cohere_window_started = now
                _cohere_window_requests = 0
            if _cohere_window_requests + 1 <= rpm:
                _cohere_window_requests += 1
                return
            sleep_for = max(1.0, 60 - (now - _cohere_window_started))
        logger.info("Cohere rerank rate limit reached; sleeping %.1fs", sleep_for)
        await asyncio.sleep(sleep_for)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_client() -> httpx.AsyncClient:
    global _rerank_client
    if _rerank_client is None:
        await init_rerank_client()
    assert _rerank_client is not None
    return _rerank_client


async def _sleep_for_retry(attempt: int, response: httpx.Response | None) -> None:
    if response is not None:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                await asyncio.sleep(float(retry_after))
                return
            except ValueError:
                pass
    await asyncio.sleep(min(30.0, 2**attempt + random.random()))
