"""Embedding service backed by NVIDIA Nemotron via OpenRouter API."""

from __future__ import annotations

import asyncio
import logging
import math

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_EMBEDDING_CACHE: dict[str, list[float]] = {}
_CACHE_MAX = 512

_client: httpx.AsyncClient | None = None
_client_loop: int | None = None  # id of the event loop that created _client


def get_embedding_dimension() -> int:
    """Return configured embedding vector dimension."""
    return get_settings().embedding_dimension


def get_embedding_model_name() -> str:
    """Return configured embedding model name."""
    return get_settings().embedding_model


async def init_async_client() -> None:
    """Initialize the shared async HTTP client for embeddings."""
    global _client
    if _client is not None:
        return
    _client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0),
        limits=httpx.Limits(
            max_keepalive_connections=20,
            max_connections=50,
            keepalive_expiry=30.0,
        ),
    )
    logger.info("Embedding async HTTP client initialized")


async def close_async_client() -> None:
    """Close the shared async HTTP client."""
    global _client, _client_loop
    if _client is not None:
        await _client.aclose()
        _client = None
        _client_loop = None
        logger.info("Embedding async HTTP client closed")


async def encode_text(text: str, use_cache: bool = False) -> list[float]:
    """Encode a single text string into a normalized embedding vector."""
    if not text.strip():
        return [0.0] * get_embedding_dimension()
    if use_cache and text in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[text]
    result = (await _call_embedding_api([text]))[0]
    if use_cache and len(_EMBEDDING_CACHE) < _CACHE_MAX:
        _EMBEDDING_CACHE[text] = result
    return result


async def encode_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Encode text strings into normalized embedding vectors."""
    if not texts:
        return []
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_embeddings.extend(await _call_embedding_api(batch))
    return all_embeddings


async def _call_embedding_api(texts: list[str]) -> list[list[float]]:
    """Call OpenRouter embedding API for a batch of texts."""
    global _client, _client_loop

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Embeddings require a valid API key. "
            "Set OPENROUTER_API_KEY in your .env file."
        )

    current_loop_id = id(asyncio.get_running_loop())
    if _client is None or _client_loop != current_loop_id:
        if _client is not None:
            await _client.aclose()
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=30.0,
            ),
        )
        _client_loop = current_loop_id
    client = _client

    url = f"{settings.embedding_base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.embedding_model,
        "input": texts,
        "encoding_format": "float",
    }

    try:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        embeddings = []
        for item in data.get("data", []):
            vec = item.get("embedding", [])
            target_dim = settings.embedding_dimension
            if len(vec) > target_dim:
                vec = vec[:target_dim]
            embeddings.append(_normalize(vec))

        if embeddings and len(embeddings[0]) != settings.embedding_dimension:
            logger.info(
                "Embedding dimension mismatch: config=%d, actual=%d. Using actual.",
                settings.embedding_dimension,
                len(embeddings[0]),
            )

        while len(embeddings) < len(texts):
            embeddings.append([0.0] * settings.embedding_dimension)

        return embeddings

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Embedding API HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        raise RuntimeError(f"Embedding API returned HTTP {exc.response.status_code}") from exc
    except Exception as exc:
        logger.error("Embedding API call failed: %s", exc)
        raise RuntimeError(f"Embedding API call failed: {exc}") from exc


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize an embedding vector for cosine similarity."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
