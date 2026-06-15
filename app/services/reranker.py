"""Cross-encoder reranker using NVIDIA Nemotron via OpenRouter /v1/rerank API."""

from __future__ import annotations

import logging

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_rerank_client: httpx.AsyncClient | None = None


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
    """Rerank documents by relevance to query via OpenRouter rerank API.

    Uses NVIDIA Nemotron reranker (free) through OpenRouter's /v1/rerank
    endpoint. Falls back to identity ordering if no API key is set.

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
    if not settings.openrouter_api_key:
        logger.warning("OPENROUTER_API_KEY not set, skipping reranking")
        fallback = [(i, float(len(documents) - i)) for i in range(len(documents))]
        return fallback[:top_k] if top_k is not None else fallback

    result = await _call_rerank_api(query, documents, settings, top_k)
    if result is not None:
        return result

    fallback = [(i, float(len(documents) - i)) for i in range(len(documents))]
    return fallback[:top_k] if top_k is not None else fallback


async def _call_rerank_api(
    query: str,
    documents: list[str],
    settings: Settings,
    top_k: int | None,
) -> list[tuple[int, float]] | None:
    """Call OpenRouter /v1/rerank endpoint with Nemotron model."""
    global _rerank_client

    if _rerank_client is None:
        _rerank_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=30,
                keepalive_expiry=30.0,
            ),
        )
    client = _rerank_client

    url = "https://openrouter.ai/api/v1/rerank"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
        "query": query,
        "documents": documents,
    }
    if top_k is not None:
        payload["top_n"] = top_k

    try:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        indexed = [(r["index"], float(r["relevance_score"])) for r in results]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Rerank API HTTP %s: %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return None
    except Exception as exc:
        logger.error("Rerank API failed: %s", exc)
        return None
