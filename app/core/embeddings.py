"""Embedding service for full-text retrieval vectors."""

from __future__ import annotations

import asyncio
import logging
import math
import random

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_EMBEDDING_CACHE: dict[str, list[float]] = {}
_CACHE_MAX = 512

_client: httpx.AsyncClient | None = None
_client_loop: int | None = None  # id of the event loop that created _client
_gemini_rate_lock = asyncio.Lock()
_gemini_window_started: float = 0.0
_gemini_window_requests: int = 0
_gemini_window_tokens: int = 0
_jina_rate_lock = asyncio.Lock()
_jina_window_started: float = 0.0
_jina_window_requests: int = 0


def get_embedding_dimension() -> int:
    """Return configured embedding vector dimension."""
    return get_settings().embedding_dimension


def get_embedding_model_name() -> str:
    """Return configured embedding model name."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "gemini":
        return settings.gemini_embedding_model
    if provider == "jina":
        return settings.jina_embedding_model
    return settings.embedding_model


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


async def encode_text(
    text: str,
    use_cache: bool = False,
    task: str | None = None,
) -> list[float]:
    """Encode a single text string into a normalized embedding vector.

    Args:
        text: Text to embed.
        use_cache: Reuse in-process LRU for repeated queries.
        task: Jina LoRA task adapter (e.g. ``"retrieval.query"`` vs
            ``"retrieval.passage"``). Ignored by other providers.
    """
    if not text.strip():
        return [0.0] * get_embedding_dimension()
    if use_cache and text in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[text]
    result = (await _call_embedding_api([text], task=task))[0]
    if use_cache and len(_EMBEDDING_CACHE) < _CACHE_MAX:
        _EMBEDDING_CACHE[text] = result
    return result


async def encode_batch(
    texts: list[str],
    batch_size: int = 32,
    task: str | None = None,
) -> list[list[float]]:
    """Encode text strings into normalized embedding vectors.

    Args:
        texts: List of strings to embed.
        batch_size: Maximum texts per API request.
        task: Jina LoRA task adapter. Defaults to ``"retrieval.passage"``
            when using Jina (best for documents being indexed). Ignored by
            other providers.
    """
    if not texts:
        return []
    all_embeddings: list[list[float]] = []
    settings = get_settings()
    if settings.embedding_provider.lower() == "gemini":
        batch_size = min(batch_size, 16)
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_embeddings.extend(await _call_embedding_api(batch, task=task))
    return all_embeddings


async def _call_embedding_api(
    texts: list[str],
    task: str | None = None,
) -> list[list[float]]:
    """Call the configured embedding API for a batch of texts."""
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "gemini":
        return await _call_gemini_embedding_api(texts)
    if provider == "openrouter":
        return await _call_openrouter_embedding_api(texts)
    if provider == "jina":
        return await _call_jina_embedding_api(texts, task=task)
    raise RuntimeError(
        f"Unsupported EMBEDDING_PROVIDER '{settings.embedding_provider}'. "
        "Use 'jina', 'gemini', or 'openrouter'."
    )


async def _get_client() -> httpx.AsyncClient:
    """Return an event-loop-local shared HTTP client."""
    global _client, _client_loop

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
    return _client


async def _call_openrouter_embedding_api(texts: list[str]) -> list[list[float]]:
    """Call OpenRouter embedding API for a batch of texts."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Embeddings require a valid API key. "
            "Set OPENROUTER_API_KEY in your .env file."
        )

    client = await _get_client()
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


async def _call_jina_embedding_api(
    texts: list[str],
    task: str | None = None,
) -> list[list[float]]:
    """Call Jina Embeddings v3/v4 via https://api.jina.ai/v1/embeddings.

    Uses Matryoshka Representation Learning (MRL) to truncate the output
    dimension to ``min(jina_embedding_dimension, embedding_dimension)``.
    Pass ``task="retrieval.query"`` for search queries and the default
    ``"retrieval.passage"`` for documents being indexed.
    """
    settings = get_settings()
    if not settings.jina_api_key:
        raise RuntimeError(
            "JINA_API_KEY is not set. Jina embeddings require a valid API key. "
            "Set JINA_API_KEY in your .env file (https://jina.ai/api-dashboard/embedding)."
        )

    # Resolve LoRA adapter task (default to passage for batch indexing).
    effective_task = task or settings.jina_embedding_task_passage

    # Cap output dim by both pgvector column and Jina MRL ceiling.
    target_dim = min(settings.jina_embedding_dimension, settings.embedding_dimension)

    await _respect_jina_rate_limit(settings)

    client = await _get_client()
    headers = {
        "Authorization": f"Bearer {settings.jina_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": settings.jina_embedding_model,
        "input": texts,
        "task": effective_task,
        "dimensions": target_dim,
        "normalized": True,         # server-side L2 norm → skip client _normalize
        "truncate": True,           # auto-truncate input over context window
        "encoding_format": "float", # explicit float (not base64) for clarity
    }

    for attempt in range(4):
        try:
            resp = await client.post(
                settings.jina_embedding_url, json=payload, headers=headers,
            )
            if resp.status_code == 429:
                await _sleep_for_retry(attempt, resp)
                continue
            resp.raise_for_status()
            data = resp.json()

            raw_embeddings = [
                item.get("embedding", []) for item in data.get("data", [])
            ]
            # Pad with zero vectors for any texts the API dropped.
            while len(raw_embeddings) < len(texts):
                raw_embeddings.append([0.0] * settings.embedding_dimension)

            # ``normalized=true`` returns L2-unit vectors, so client-side
            # _normalize is a no-op but kept as a safety belt (matches the
            # behaviour of the other providers).
            return [_fit_dimension(_normalize(v)) for v in raw_embeddings]

        except httpx.HTTPStatusError as exc:
            logger.error(
                "Jina embedding API HTTP %s: %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            if exc.response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                await _sleep_for_retry(attempt, exc.response)
                continue
            raise RuntimeError(
                f"Jina embedding API returned HTTP {exc.response.status_code}"
            ) from exc
        except Exception as exc:
            logger.error("Jina embedding API call failed: %s", exc)
            if attempt < 3:
                await _sleep_for_retry(attempt, None)
                continue
            raise RuntimeError(f"Jina embedding API call failed: {exc}") from exc

    return [[0.0] * settings.embedding_dimension for _ in texts]


async def _respect_jina_rate_limit(settings) -> None:
    """Throttle Jina embedding calls to N requests / 60s (free tier: 100 RPM)."""
    global _jina_window_requests, _jina_window_started

    rpm = max(1, settings.jina_embedding_requests_per_minute)
    while True:
        async with _jina_rate_lock:
            now = asyncio.get_running_loop().time()
            if now - _jina_window_started >= 60:
                _jina_window_started = now
                _jina_window_requests = 0
            if _jina_window_requests + 1 <= rpm:
                _jina_window_requests += 1
                return
            sleep_for = max(1.0, 60 - (now - _jina_window_started))
        logger.info("Jina embedding rate limit reached; sleeping %.1fs", sleep_for)
        await asyncio.sleep(sleep_for)


async def _call_gemini_embedding_api(texts: list[str]) -> list[list[float]]:
    """Call Gemini batchEmbedContents with basic free-tier rate limiting."""
    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Gemini embeddings require a valid API key."
        )

    model = settings.gemini_embedding_model
    model_path = model if model.startswith("models/") else f"models/{model}"
    # Ask Gemini for its native dim (e.g. 768) instead of storage dim
    # (2000) — saves tokens on the free tier. _fit_dimension will pad up
    # to settings.embedding_dimension for the pgvector(2000) column.
    output_dim = min(settings.gemini_embedding_dimension, settings.embedding_dimension)
    await _respect_gemini_rate_limit(texts)

    client = await _get_client()
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:batchEmbedContents"
    params = {"key": settings.google_api_key}
    payload = {
        "requests": [
            {
                "model": model_path,
                "content": {"parts": [{"text": text}]},
                "outputDimensionality": output_dim,
            }
            for text in texts
        ]
    }

    for attempt in range(4):
        try:
            resp = await client.post(url, params=params, json=payload)
            if resp.status_code == 429:
                await _sleep_for_retry(attempt, resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            embeddings = [
                _fit_dimension(_normalize(item.get("values", [])))
                for item in data.get("embeddings", [])
            ]
            while len(embeddings) < len(texts):
                embeddings.append([0.0] * settings.embedding_dimension)
            return embeddings
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Gemini embedding API HTTP error %s: %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            if exc.response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                await _sleep_for_retry(attempt, exc.response)
                continue
            raise RuntimeError(
                f"Gemini embedding API returned HTTP {exc.response.status_code}"
            ) from exc
        except Exception as exc:
            logger.error("Gemini embedding API call failed: %s", exc)
            if attempt < 3:
                await _sleep_for_retry(attempt, None)
                continue
            raise RuntimeError(f"Gemini embedding API call failed: {exc}") from exc

    return [[0.0] * settings.embedding_dimension for _ in texts]


async def _respect_gemini_rate_limit(texts: list[str]) -> None:
    """Throttle Gemini embedding calls for the configured free-tier limits."""
    global _gemini_window_requests, _gemini_window_started, _gemini_window_tokens

    settings = get_settings()
    estimated_tokens = sum(_estimate_tokens(text) for text in texts)
    while True:
        async with _gemini_rate_lock:
            now = asyncio.get_running_loop().time()
            if now - _gemini_window_started >= 60:
                _gemini_window_started = now
                _gemini_window_requests = 0
                _gemini_window_tokens = 0

            requests_ok = (
                _gemini_window_requests + 1
                <= max(1, settings.gemini_embedding_requests_per_minute)
            )
            tokens_ok = (
                _gemini_window_tokens + estimated_tokens
                <= max(1, settings.gemini_embedding_tokens_per_minute)
            )
            if requests_ok and tokens_ok:
                _gemini_window_requests += 1
                _gemini_window_tokens += estimated_tokens
                return

            sleep_for = max(1.0, 60 - (now - _gemini_window_started))
        logger.info("Gemini embedding rate limit reached; sleeping %.1fs", sleep_for)
        await asyncio.sleep(sleep_for)


def _estimate_tokens(text: str) -> int:
    """Cheap token estimate for rate limiting; biased slightly high."""
    return max(1, len(text) // 3)


async def _sleep_for_retry(attempt: int, response: httpx.Response | None) -> None:
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        try:
            await asyncio.sleep(float(retry_after))
            return
        except ValueError:
            pass
    await asyncio.sleep(min(30.0, 2**attempt + random.random()))


def _fit_dimension(vector: list[float]) -> list[float]:
    """Pad or truncate vectors to the pgvector storage dimension."""
    target_dim = get_settings().embedding_dimension
    if len(vector) > target_dim:
        return vector[:target_dim]
    if len(vector) < target_dim:
        return vector + [0.0] * (target_dim - len(vector))
    return vector


def _normalize(vector: list[float]) -> list[float]:
    """L2-normalize an embedding vector for cosine similarity."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
