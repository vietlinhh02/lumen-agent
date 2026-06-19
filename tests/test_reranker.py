"""Tests for cross-encoder reranker (OpenRouter /v1/rerank with Nemotron)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.reranker import rerank

# ── Basic functionality ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_returns_indexed_scores():
    """Without API key, returns fallback indexed scores."""
    docs = ["doc a", "doc b", "doc c"]
    result = await rerank("test query", docs)
    assert len(result) == 3
    indices = [idx for idx, _ in result]
    assert sorted(indices) == [0, 1, 2]


@pytest.mark.asyncio
async def test_rerank_empty_documents():
    result = await rerank("test query", [])
    assert result == []


@pytest.mark.asyncio
async def test_rerank_empty_query():
    docs = ["doc a", "doc b"]
    result = await rerank("", docs)
    assert len(result) == 2
    assert all(score == 0.0 for _, score in result)


@pytest.mark.asyncio
async def test_rerank_top_k():
    docs = ["doc a", "doc b", "doc c", "doc d", "doc e"]
    result = await rerank("test query", docs, top_k=2)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_rerank_no_api_key_returns_fallback():
    """Without OPENROUTER_API_KEY, returns descending index scores."""
    with patch("app.services.reranker.get_settings") as mock_settings:
        mock_settings.return_value.openrouter_api_key = ""
        result = await rerank("query", ["doc a", "doc b", "doc c"])
    assert len(result) == 3
    scores = [s for _, s in result]
    assert scores == sorted(scores, reverse=True)


# ── API mock tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_api_success():
    """Test successful API call with mocked _call_rerank_api."""
    mock_result = [(2, 0.99), (0, 0.85), (1, 0.12)]
    mock_settings = MagicMock()
    mock_settings.openrouter_api_key = "test-key"
    with (
        patch(
            "app.services.reranker._call_rerank_api",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("test query", ["doc a", "doc b", "doc c"])

    assert len(result) == 3
    assert result[0] == (2, 0.99)
    assert result[1] == (0, 0.85)
    assert result[2] == (1, 0.12)


@pytest.mark.asyncio
async def test_rerank_api_success_with_top_k():
    """Test API with top_k filtering."""
    mock_result = [(2, 0.99), (0, 0.85)]
    mock_settings = MagicMock()
    mock_settings.openrouter_api_key = "test-key"
    with (
        patch(
            "app.services.reranker._call_rerank_api",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("test query", ["doc a", "doc b", "doc c"], top_k=2)

    assert len(result) == 2
    assert result[0] == (2, 0.99)
    assert result[1] == (0, 0.85)


@pytest.mark.asyncio
async def test_rerank_api_error_returns_fallback():
    """Test API error returns fallback scores."""
    mock_settings = MagicMock()
    mock_settings.openrouter_api_key = "test-key"
    with (
        patch(
            "app.services.reranker._call_rerank_api",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("test query", ["doc a", "doc b", "doc c"])

    assert len(result) == 3
    scores = [s for _, s in result]
    assert scores == sorted(scores, reverse=True)
