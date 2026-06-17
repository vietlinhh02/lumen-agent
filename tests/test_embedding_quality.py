"""Tests for embedding service (API-based NVIDIA Nemotron via OpenRouter)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

from app.core.embeddings import _normalize, encode_batch, encode_text, get_embedding_dimension


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
