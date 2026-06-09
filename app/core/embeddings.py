"""Embedding service backed by Gemini Embedding."""

from __future__ import annotations

import logging
import math
import time
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
_GEMINI_BATCH_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
)
_REQUEST_TIMEOUT_SECONDS = 45.0
_MAX_RETRIES = 3
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def get_embedding_dimension() -> int:
    """Return configured embedding vector dimension."""
    return get_settings().gemini_embedding_dimension


def get_embedding_model_name() -> str:
    """Return configured embedding model name."""
    return get_settings().gemini_embedding_model


@lru_cache(maxsize=256)
def _cached_encode(text: str) -> tuple[float, ...]:
    """Cache embeddings for repeated text."""
    return tuple(_embed_gemini(text))


def encode_text(text: str, use_cache: bool = False) -> list[float]:
    """Encode a single text string into a normalized embedding vector."""
    if use_cache:
        return list(_cached_encode(text))
    return _embed_gemini(text)


def encode_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Encode text strings into normalized embedding vectors."""
    embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        embeddings.extend(_embed_gemini_batch(texts[start : start + batch_size]))
    return embeddings


def _embed_gemini(text: str) -> list[float]:
    """Call Gemini embedContent and return a normalized vector."""
    settings = get_settings()
    if settings.embedding_provider != "gemini":
        raise RuntimeError(f"Unsupported embedding provider: {settings.embedding_provider}")
    if not settings.google_api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY for Gemini embeddings.")
    if not text.strip():
        return [0.0] * settings.gemini_embedding_dimension

    url = _GEMINI_EMBED_URL.format(model=settings.gemini_embedding_model)
    payload = {
        "model": f"models/{settings.gemini_embedding_model}",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": settings.gemini_embedding_dimension,
    }
    response = _post_gemini(url, payload)
    values = response.json().get("embedding", {}).get("values")
    return _parse_embedding_values({"values": values})


def _embed_gemini_batch(texts: list[str]) -> list[list[float]]:
    """Call Gemini batchEmbedContents and return normalized vectors."""
    if not texts:
        return []

    settings = get_settings()
    if settings.embedding_provider != "gemini":
        raise RuntimeError(f"Unsupported embedding provider: {settings.embedding_provider}")
    if not settings.google_api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY for Gemini embeddings.")

    requests = []
    empty_indices: set[int] = set()
    for index, text in enumerate(texts):
        if not text.strip():
            empty_indices.add(index)
            continue
        requests.append(
            {
                "model": f"models/{settings.gemini_embedding_model}",
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": settings.gemini_embedding_dimension,
            }
        )

    if not requests:
        return [[0.0] * settings.gemini_embedding_dimension for _ in texts]

    url = _GEMINI_BATCH_EMBED_URL.format(model=settings.gemini_embedding_model)
    response = _post_gemini(url, {"requests": requests})
    raw_embeddings = response.json().get("embeddings")
    if not isinstance(raw_embeddings, list):
        raise RuntimeError("Gemini batch embedding response did not include embeddings.")

    normalized = [_parse_embedding_values(item) for item in raw_embeddings]
    output: list[list[float]] = []
    normalized_index = 0
    for index in range(len(texts)):
        if index in empty_indices:
            output.append([0.0] * settings.gemini_embedding_dimension)
            continue
        output.append(normalized[normalized_index])
        normalized_index += 1
    return output


def _parse_embedding_values(item: Any) -> list[float]:
    """Parse and normalize one Gemini embedding item."""
    settings = get_settings()
    values = item.get("values") if isinstance(item, dict) else None
    if not isinstance(values, list):
        raise RuntimeError("Gemini embedding item did not include values.")
    vector = [float(value) for value in values]
    if len(vector) != settings.gemini_embedding_dimension:
        raise RuntimeError(
            "Gemini embedding dimension mismatch: "
            f"expected {settings.gemini_embedding_dimension}, got {len(vector)}."
        )
    return _normalize(vector)


def _post_gemini(url: str, payload: dict) -> httpx.Response:
    """POST to Gemini with bounded retries and sanitized failures."""
    settings = get_settings()
    last_detail = ""
    for attempt in range(_MAX_RETRIES):
        try:
            response = httpx.post(
                url,
                params={"key": settings.google_api_key},
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            last_detail = str(exc)
            if attempt == _MAX_RETRIES - 1:
                raise RuntimeError(f"Gemini embedding request failed: {last_detail}") from None
            time.sleep(2**attempt)
            continue

        if response.status_code not in _RETRY_STATUS_CODES:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                detail = _response_detail(response)
                raise RuntimeError(f"Gemini embedding request failed: {detail}") from None
            return response

        last_detail = _response_detail(response)
        if attempt < _MAX_RETRIES - 1:
            time.sleep(2**attempt)

    raise RuntimeError(f"Gemini embedding request failed: {last_detail}")


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize an embedding vector for cosine similarity."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _response_detail(response: httpx.Response) -> str:
    """Extract a compact API error message without leaking request parameters."""
    try:
        body: Any = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    message = body.get("error", {}).get("message") if isinstance(body, dict) else None
    return f"HTTP {response.status_code}: {message or str(body)[:200]}"
