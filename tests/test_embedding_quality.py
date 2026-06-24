"""Tests for embedding service (Jina AI / Gemini / OpenRouter)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.embeddings import (
    _normalize,
    encode_batch,
    encode_text,
    get_embedding_dimension,
)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


# ── Basic functionality ──────────────────────────────────────────────────────


def test_embedding_dimension_is_configurable():
    dim = get_embedding_dimension()
    assert dim > 0


@pytest.mark.asyncio
async def test_empty_text_returns_zero_vector():
    result = await encode_text("")
    assert len(result) == get_embedding_dimension()
    assert all(v == 0.0 for v in result)


def test_normalize_l2_normalizes():
    vec = [3.0, 4.0]
    result = _normalize(vec)
    norm = math.sqrt(sum(v * v for v in result))
    assert abs(norm - 1.0) < 1e-6


def test_normalize_zero_vector():
    vec = [0.0, 0.0]
    result = _normalize(vec)
    assert result == [0.0, 0.0]


@pytest.mark.asyncio
async def test_encode_batch_empty():
    result = await encode_batch([])
    assert result == []


# ── API fallback (no key) ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_encode_text_no_api_key_raises():
    """When OPENROUTER_API_KEY is not set, should raise RuntimeError."""
    with patch("app.core.embeddings.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = "openrouter"
        mock_settings.return_value.openrouter_api_key = ""
        mock_settings.return_value.embedding_dimension = 2048
        mock_settings.return_value.embedding_model = "test-model"
        mock_settings.return_value.embedding_base_url = "http://localhost"
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            await encode_text("some text")


@pytest.mark.asyncio
async def test_encode_batch_no_api_key_raises():
    """When OPENROUTER_API_KEY is not set, batch should raise RuntimeError."""
    with patch("app.core.embeddings.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = "openrouter"
        mock_settings.return_value.openrouter_api_key = ""
        mock_settings.return_value.embedding_dimension = 2048
        mock_settings.return_value.embedding_model = "test-model"
        mock_settings.return_value.embedding_base_url = "http://localhost"
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            await encode_batch(["text a", "text b"])


# ── API mock tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_encode_text_api_success():
    """Test successful API call with mocked _call_embedding_api.

    _call_embedding_api returns already-normalized vectors, so encode_text
    passes them through without additional normalization.
    """
    mock_result = [[0.6, 0.8, 0.0]]  # already unit L2-normalized (norm=1.0)
    with patch(
        "app.core.embeddings._call_embedding_api",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await encode_text("test text")

    assert len(result) == 3
    norm = math.sqrt(sum(v * v for v in result))
    assert abs(norm - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_encode_batch_api_success():
    """Test batch API call with mocked _call_embedding_api.

    _call_embedding_api returns already-normalized vectors.
    """
    mock_result = [[0.6, 0.8, 0.0], [0.0, 1.0, 0.0]]  # unit L2-normalized
    with patch(
        "app.core.embeddings._call_embedding_api",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = await encode_batch(["text a", "text b"])

    assert len(result) == 2
    assert all(len(v) == 3 for v in result)
    for v in result:
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_encode_text_api_http_error():
    """Test API HTTP error raises RuntimeError.

    _call_embedding_api catches httpx.HTTPStatusError internally and converts
    it to RuntimeError. We test this by mocking _call_embedding_api to raise
    RuntimeError directly (simulating what the httpx error path produces).
    """
    with (
        patch(
            "app.core.embeddings._call_embedding_api",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Embedding API returned HTTP 429"),
        ),
        pytest.raises(RuntimeError, match="Embedding API"),
    ):
        await encode_text("test text")


# ── Jina AI provider tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_encode_text_jina_no_api_key_raises():
    """When JINA_API_KEY is not set, encode_text raises RuntimeError."""
    with patch("app.core.embeddings.get_settings") as mock_settings:
        mock_settings.return_value.embedding_provider = "jina"
        mock_settings.return_value.jina_api_key = ""
        with pytest.raises(RuntimeError, match="JINA_API_KEY"):
            await encode_text("hello world")


@pytest.mark.asyncio
async def test_jina_provider_payload_includes_task_and_dim():
    """Verify Jina payload uses the retrieval.passage task + dimensions + normalized."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self_inner):
            return {"data": [
                {"embedding": [0.6, 0.8]},
                {"embedding": [0.0, 1.0]},
            ]}

        def raise_for_status(self_inner):
            return None

    async def fake_post(url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _Resp()

    fake_client = MagicMock()
    fake_client.post = fake_post

    mock_settings = MagicMock()
    mock_settings.embedding_provider = "jina"
    mock_settings.jina_api_key = "jina-test"
    mock_settings.jina_embedding_url = "https://api.jina.ai/v1/embeddings"
    mock_settings.jina_embedding_model = "jina-embeddings-v3"
    mock_settings.jina_embedding_dimension = 1024
    mock_settings.embedding_dimension = 1024
    mock_settings.jina_embedding_task_passage = "retrieval.passage"
    mock_settings.jina_embedding_task_query = "retrieval.query"
    mock_settings.jina_embedding_requests_per_minute = 10000

    async def fake_get_client():
        return fake_client

    with (
        patch("app.core.embeddings.get_settings", return_value=mock_settings),
        patch("app.core.embeddings._get_client", side_effect=fake_get_client),
    ):
        await encode_batch(["doc one", "doc two"])

    payload = captured["json"]
    assert payload["model"] == "jina-embeddings-v3"
    assert payload["task"] == "retrieval.passage"
    assert payload["dimensions"] == 1024
    assert payload["normalized"] is True
    assert payload["truncate"] is True
    assert payload["input"] == ["doc one", "doc two"]
    assert captured["headers"]["Authorization"] == "Bearer jina-test"


@pytest.mark.asyncio
async def test_jina_encode_text_passes_query_task():
    """encode_text(text, task='retrieval.query') routes that adapter to Jina."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self_inner):
            return {"data": [{"embedding": [0.0, 0.0, 1.0]}]}

        def raise_for_status(self_inner):
            return None

    async def fake_post(url, json=None, headers=None, **kwargs):
        captured["json"] = json
        return _Resp()

    fake_client = MagicMock()
    fake_client.post = fake_post

    mock_settings = MagicMock()
    mock_settings.embedding_provider = "jina"
    mock_settings.jina_api_key = "k"
    mock_settings.jina_embedding_url = "https://api.jina.ai/v1/embeddings"
    mock_settings.jina_embedding_model = "jina-embeddings-v3"
    mock_settings.jina_embedding_dimension = 3
    mock_settings.embedding_dimension = 3
    mock_settings.jina_embedding_task_passage = "retrieval.passage"
    mock_settings.jina_embedding_task_query = "retrieval.query"
    mock_settings.jina_embedding_requests_per_minute = 10000

    async def fake_get_client():
        return fake_client

    with (
        patch("app.core.embeddings.get_settings", return_value=mock_settings),
        patch("app.core.embeddings._get_client", side_effect=fake_get_client),
    ):
        await encode_text("search query", task="retrieval.query")

    assert captured["json"]["task"] == "retrieval.query"


def test_get_embedding_model_name_jina():
    """get_embedding_model_name() should return Jina model when provider=jina."""
    mock_settings = MagicMock()
    mock_settings.embedding_provider = "jina"
    mock_settings.jina_embedding_model = "jina-embeddings-v3"
    mock_settings.embedding_dimension = 1024
    with patch("app.core.embeddings.get_settings", return_value=mock_settings):
        from app.core.embeddings import get_embedding_model_name

        assert get_embedding_model_name() == "jina-embeddings-v3"
        assert get_embedding_dimension() == 1024
