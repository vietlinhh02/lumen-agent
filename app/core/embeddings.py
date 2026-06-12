"""Embedding service backed by NVIDIA Nemotron via OpenRouter API."""

from __future__ import annotations

import logging
import math

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_EMBEDDING_CACHE: dict[str, list[float]] = {}
_CACHE_MAX = 512


def get_embedding_dimension() -> int:
    """Return configured embedding vector dimension."""
    return get_settings().embedding_dimension


def get_embedding_model_name() -> str:
    """Return configured embedding model name."""
    return get_settings().embedding_model


def encode_text(text: str, use_cache: bool = False) -> list[float]:
    """Encode a single text string into a normalized embedding vector."""
    if not text.strip():
        return [0.0] * get_embedding_dimension()
    if use_cache and text in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[text]
    result = _call_embedding_api([text])[0]
    if use_cache and len(_EMBEDDING_CACHE) < _CACHE_MAX:
        _EMBEDDING_CACHE[text] = result
    return result


def encode_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Encode text strings into normalized embedding vectors."""
    if not texts:
        return []
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_embeddings.extend(_call_embedding_api(batch))
    return all_embeddings


def _call_embedding_api(texts: list[str]) -> list[list[float]]:
    """Call OpenRouter embedding API for a batch of texts."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        logger.warning("OPENROUTER_API_KEY not set, returning zero vectors")
        return [[0.0] * settings.embedding_dimension for _ in texts]

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
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        embeddings = []
        for item in data.get("data", []):
            vec = item.get("embedding", [])
            embeddings.append(_normalize(vec))

        # Update dimension from first response if different from config
        if embeddings and len(embeddings[0]) != settings.embedding_dimension:
            logger.info(
                "Embedding dimension mismatch: config=%d, actual=%d. Using actual.",
                settings.embedding_dimension,
                len(embeddings[0]),
            )

        # Pad if API returned fewer results than requested
        while len(embeddings) < len(texts):
            embeddings.append([0.0] * settings.embedding_dimension)

        return embeddings

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Embedding API HTTP error %s: %s", exc.response.status_code, exc.response.text[:300]
        )
        return [[0.0] * settings.embedding_dimension for _ in texts]
    except Exception as exc:
        logger.error("Embedding API call failed: %s", exc)
        return [[0.0] * settings.embedding_dimension for _ in texts]


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize an embedding vector for cosine similarity."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
