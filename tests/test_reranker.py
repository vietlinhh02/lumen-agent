"""Tests for cross-encoder reranker (Jina AI preferred, Cohere fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.reranker import rerank

# ── Basic functionality ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_returns_indexed_scores():
    """Without any API key, returns fallback indexed scores."""
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
    """Without JINA_API_KEY or COHERE_API_KEY, returns descending index scores."""
    with patch("app.services.reranker.get_settings") as mock_settings:
        mock_settings.return_value.jina_api_key = ""
        mock_settings.return_value.cohere_api_key = ""
        result = await rerank("query", ["doc a", "doc b", "doc c"])
    assert len(result) == 3
    scores = [s for _, s in result]
    assert scores == sorted(scores, reverse=True)


# ── Jina API mock tests (preferred path) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_jina_api_success():
    """Successful Jina call with mocked _call_jina_rerank."""
    mock_result = [(2, 0.88), (0, 0.62), (1, 0.31)]
    mock_settings = MagicMock()
    mock_settings.jina_api_key = "jina-key"
    mock_settings.jina_rerank_url = "https://api.jina.ai/v1/rerank"
    mock_settings.jina_rerank_model = "jina-reranker-v2-base-multilingual"
    mock_settings.jina_rerank_requests_per_minute = 10000
    mock_settings.cohere_api_key = ""
    with (
        patch(
            "app.services.reranker._call_jina_rerank",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("test query", ["doc a", "doc b", "doc c"])

    assert result == mock_result


@pytest.mark.asyncio
async def test_rerank_jina_payload_shape():
    """Jina rerank request uses 'relevance_score' field and 'top_n' cap."""
    captured: dict = {}

    class _Resp:
        status_code = 200

        def json(self_inner):
            return {"results": [
                {"index": 0, "relevance_score": 0.9},
                {"index": 1, "relevance_score": 0.1},
            ]}

        def raise_for_status(self_inner):
            return None

    async def fake_post(url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    fake_client = MagicMock()
    fake_client.post = fake_post

    mock_settings = MagicMock()
    mock_settings.jina_api_key = "k"
    mock_settings.jina_rerank_url = "https://api.jina.ai/v1/rerank"
    mock_settings.jina_rerank_model = "jina-reranker-v2-base-multilingual"
    mock_settings.jina_rerank_requests_per_minute = 10000
    mock_settings.cohere_api_key = ""

    async def fake_get_client():
        return fake_client

    with (
        patch("app.services.reranker.get_settings", return_value=mock_settings),
        patch("app.services.reranker._get_client", side_effect=fake_get_client),
    ):
        result = await rerank("q", ["a", "b"], top_k=2)

    assert captured["url"] == "https://api.jina.ai/v1/rerank"
    payload = captured["json"]
    assert payload["model"] == "jina-reranker-v2-base-multilingual"
    assert payload["query"] == "q"
    assert payload["documents"] == ["a", "b"]
    assert payload["top_n"] == 2
    assert payload["return_documents"] is False
    # Result sorted by score descending
    assert result[0][0] == 0 and result[0][1] == 0.9


@pytest.mark.asyncio
async def test_rerank_jina_api_error_falls_back_to_cohere():
    """When Jina returns None, fall through to Cohere (and finally identity)."""
    mock_settings = MagicMock()
    mock_settings.jina_api_key = "jina-key"
    mock_settings.jina_rerank_url = "https://api.jina.ai/v1/rerank"
    mock_settings.jina_rerank_model = "jina-reranker-v2-base-multilingual"
    mock_settings.jina_rerank_requests_per_minute = 10000
    mock_settings.cohere_api_key = "cohere-key"
    mock_settings.cohere_rerank_url = "https://api.cohere.com/v2/rerank"
    mock_settings.cohere_rerank_model = "rerank-english-v3.0"
    mock_settings.cohere_rerank_requests_per_minute = 10000

    jina_result = None
    cohere_result = [(0, 0.75), (1, 0.20)]

    with (
        patch("app.services.reranker._call_jina_rerank", new_callable=AsyncMock, return_value=jina_result),
        patch("app.services.reranker._call_cohere_rerank", new_callable=AsyncMock, return_value=cohere_result),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("q", ["a", "b"])

    assert result == cohere_result


@pytest.mark.asyncio
async def test_rerank_jina_api_error_falls_back_to_identity_when_no_cohere():
    """When Jina fails AND no Cohere key, return identity fallback."""
    mock_settings = MagicMock()
    mock_settings.jina_api_key = "jina-key"
    mock_settings.jina_rerank_url = "https://api.jina.ai/v1/rerank"
    mock_settings.jina_rerank_model = "jina-reranker-v2-base-multilingual"
    mock_settings.jina_rerank_requests_per_minute = 10000
    mock_settings.cohere_api_key = ""

    with (
        patch("app.services.reranker._call_jina_rerank", new_callable=AsyncMock, return_value=None),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("q", ["a", "b", "c"])

    # Identity fallback: descending index scores 3,2,1
    assert result == [(0, 3.0), (1, 2.0), (2, 1.0)]


# ── Cohere API mock tests (legacy fallback) ─────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_cohere_api_success():
    """Successful Cohere call with mocked _call_cohere_rerank."""
    mock_result = [(1, 0.92), (0, 0.41), (2, 0.08)]
    mock_settings = MagicMock()
    mock_settings.jina_api_key = ""  # Cohere path active
    mock_settings.cohere_api_key = "trial-key"
    mock_settings.cohere_rerank_url = "https://api.cohere.com/v2/rerank"
    mock_settings.cohere_rerank_model = "rerank-english-v3.0"
    mock_settings.cohere_rerank_requests_per_minute = 10000  # don't block
    with (
        patch(
            "app.services.reranker._call_cohere_rerank",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("test query", ["doc a", "doc b", "doc c"])

    assert len(result) == 3
    assert result[0] == (1, 0.92)
    assert result[1] == (0, 0.41)
    assert result[2] == (2, 0.08)


@pytest.mark.asyncio
async def test_rerank_cohere_api_success_with_top_k():
    """Cohere call with top_k filtering."""
    mock_result = [(2, 0.99), (0, 0.85)]
    mock_settings = MagicMock()
    mock_settings.jina_api_key = ""
    mock_settings.cohere_api_key = "trial"
    mock_settings.cohere_rerank_url = "https://api.cohere.com/v2/rerank"
    mock_settings.cohere_rerank_model = "rerank-english-v3.0"
    mock_settings.cohere_rerank_requests_per_minute = 10000
    with (
        patch(
            "app.services.reranker._call_cohere_rerank",
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
async def test_rerank_cohere_api_error_returns_fallback():
    """Cohere API error returns fallback scores."""
    mock_settings = MagicMock()
    mock_settings.jina_api_key = ""
    mock_settings.cohere_api_key = "trial"
    mock_settings.cohere_rerank_url = "https://api.cohere.com/v2/rerank"
    mock_settings.cohere_rerank_model = "rerank-english-v3.0"
    mock_settings.cohere_rerank_requests_per_minute = 10000
    with (
        patch(
            "app.services.reranker._call_cohere_rerank",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.reranker.get_settings", return_value=mock_settings),
    ):
        result = await rerank("test query", ["doc a", "doc b", "doc c"])

    assert len(result) == 3
    scores = [s for _, s in result]
    assert scores == sorted(scores, reverse=True)

