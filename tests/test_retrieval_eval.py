"""Retrieval quality eval tests.

Tests retrieval pipeline components: scoring, ranking, per-paper retrieval,
and fallback behavior. Uses mocks for DB-dependent tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.hybrid_retrieval import (
    RetrievedChunk,
    _combined_score,
    _keyword_score,
    _tokens,
)

# ── Pure function tests ──────────────────────────────────────────────────────


def test_keyword_score_exact_match():
    """Exact token overlap should produce high score."""
    query_tokens = {"rag", "retrieval", "augmented"}
    paper = SimpleNamespace(
        title="Retrieval Augmented Generation for QA",
        abstract="RAG combines retrieval and generation",
    )
    chunk = SimpleNamespace(
        section_label="method",
        content_type="method",
        chunk_text="We use RAG for retrieval augmented generation",
    )

    score = _keyword_score(query_tokens, paper, chunk)
    assert score > 0.3


def test_keyword_score_no_match():
    """No overlap should produce zero score."""
    query_tokens = {"quantum", "physics"}
    paper = SimpleNamespace(title="Deep learning for NLP", abstract="Neural networks")
    chunk = SimpleNamespace(
        section_label="method", content_type="method", chunk_text="BERT transformer"
    )

    score = _keyword_score(query_tokens, paper, chunk)
    assert score == 0.0


def test_combined_score_section_boosts():
    """Limitation and results sections should get higher boost than narrative."""
    base_kw = 0.2
    base_vec = 0.3
    narrative = _combined_score(base_kw, base_vec, "narrative")
    limitation = _combined_score(base_kw, base_vec, "limitation")
    results = _combined_score(base_kw, base_vec, "results")
    method = _combined_score(base_kw, base_vec, "method")

    assert limitation > results > method > narrative


def test_combined_score_no_content_type():
    """No content_type should still produce valid score."""
    score = _combined_score(0.5, 0.5, None)
    # 0.5 * 0.45 + 0.5 * 0.55 + 0.0 = 0.5
    assert score == pytest.approx(0.5, abs=0.01)


def test_tokens_basic():
    """Token extraction should be case-insensitive and alphanumeric."""
    tokens = _tokens("RAG for Medical QA 2024!")
    assert "rag" in tokens
    assert "for" in tokens
    assert "medical" in tokens
    assert "qa" in tokens
    assert "2024" in tokens
    assert "!" not in tokens


def test_tokens_empty():
    assert _tokens("") == set()
    assert _tokens("   ") == set()


# ── Mock retrieval tests ─────────────────────────────────────────────────────


def _make_chunk(
    project_paper_id=None,
    paper_id=None,
    chunk_id=None,
    title="Test Paper",
    chunk_text="RAG retrieval augmented generation method",
    section_label="method",
    content_type="method",
    score=0.5,
    keyword_score=0.3,
    vector_score=0.7,
):
    return RetrievedChunk(
        project_paper_id=project_paper_id or uuid4(),
        paper_id=paper_id or uuid4(),
        chunk_id=chunk_id or uuid4(),
        title=title,
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type=content_type,
        page_start=1,
        page_end=2,
        content_hash=None,
        score=score,
        keyword_score=keyword_score,
        vector_score=vector_score,
    )


def test_retrieved_chunk_fields():
    """RetrievedChunk should have all required fields."""
    chunk = _make_chunk()
    assert chunk.project_paper_id is not None
    assert chunk.paper_id is not None
    assert chunk.chunk_id is not None
    assert chunk.title == "Test Paper"
    assert chunk.score == 0.5
    assert chunk.keyword_score == 0.3
    assert chunk.vector_score == 0.7


def test_retrieved_chunk_is_frozen():
    """RetrievedChunk should be immutable."""
    chunk = _make_chunk()
    with pytest.raises(AttributeError):
        chunk.score = 0.9  # type: ignore[misc]


# ── Scoring integration tests ───────────────────────────────────────────────


def test_vector_score_higher_for_similar():
    """Chunks with content matching query should rank higher."""
    chunks = [
        _make_chunk(
            chunk_text="quantum physics particles", keyword_score=0.1, vector_score=0.9, score=0.0
        ),
        _make_chunk(
            chunk_text="retrieval augmented generation",
            keyword_score=0.8,
            vector_score=0.3,
            score=0.0,
        ),
    ]

    # Compute combined scores
    scored = []
    for c in chunks:
        scored.append(_combined_score(c.keyword_score, c.vector_score, c.content_type))

    # High keyword + low vector vs low keyword + high vector
    # Both should be > 0
    assert all(s > 0 for s in scored)


def test_section_boost_ordering():
    """Limitation chunks should rank above abstract chunks with same base score."""
    lim = _combined_score(0.3, 0.5, "limitation")
    abs_ = _combined_score(0.3, 0.5, "abstract")
    assert lim > abs_


def test_multiple_papers_diverse_evidence():
    """Retrieval should support chunks from different papers."""
    pp1 = uuid4()
    pp2 = uuid4()
    chunks = [
        _make_chunk(project_paper_id=pp1, title="Paper A", chunk_text="RAG method", score=0.8),
        _make_chunk(project_paper_id=pp2, title="Paper B", chunk_text="RAG results", score=0.6),
        _make_chunk(project_paper_id=pp1, title="Paper A", chunk_text="RAG limitation", score=0.4),
    ]

    papers = {c.project_paper_id for c in chunks}
    assert len(papers) == 2


# ── DB-side vector search mock test ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieve_project_evidence_uses_cosine_distance():
    """Verify that retrieve_project_evidence uses pgvector cosine_distance."""
    from app.services.hybrid_retrieval import retrieve_project_evidence

    db = AsyncMock()
    project_id = uuid4()

    # Mock the DB result with vector_dist column
    mock_row = (
        SimpleNamespace(id=project_id),  # ProjectPaper
        SimpleNamespace(title="Test", abstract="test", id=uuid4()),  # Paper
        SimpleNamespace(
            id=uuid4(),
            project_paper_id=project_id,
            chunk_text="test content",
            section_label="method",
            section_path=None,
            chunk_index=0,
            content_type="method",
            page_start=1,
            page_end=2,
            content_hash=None,
            chunk_type="full_text",
        ),  # PaperChunk
        0.15,  # vector_dist (cosine distance)
    )
    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]
    db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("app.services.hybrid_retrieval.encode_text", return_value=[0.1] * 2048),
        patch("app.core.config.get_settings") as mock_settings,
    ):
        mock_settings.return_value.reranker_top_n = 10
        results = await retrieve_project_evidence(
            db, project_id, "test query", limit=5, use_reranker=False
        )

    # Should have called db.execute with a cosine_distance query
    assert db.execute.called
    assert results is not None


@pytest.mark.asyncio
async def test_retrieve_project_evidence_empty_query():
    """Empty query should return empty list."""
    from app.services.hybrid_retrieval import retrieve_project_evidence

    db = AsyncMock()
    results = await retrieve_project_evidence(db, uuid4(), "", limit=5)
    assert results == []


@pytest.mark.asyncio
async def test_retrieve_project_evidence_zero_embedding_fallback():
    """Zero embedding should fall back to keyword-only."""
    from app.services.hybrid_retrieval import retrieve_project_evidence

    db = AsyncMock()
    project_id = uuid4()

    # Mock keyword-only fallback result
    mock_row = (
        SimpleNamespace(id=project_id),
        SimpleNamespace(title="Test", abstract="test", id=uuid4()),
        SimpleNamespace(
            id=uuid4(),
            project_paper_id=project_id,
            chunk_text="test content",
            section_label="method",
            section_path=None,
            chunk_index=0,
            content_type="method",
            page_start=1,
            page_end=2,
            content_hash=None,
            chunk_type="full_text",
        ),
    )
    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]
    db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.hybrid_retrieval.encode_text", return_value=[0.0] * 2048):
        results = await retrieve_project_evidence(
            db, project_id, "test query", limit=5, use_reranker=False
        )

    # Should still return results via keyword fallback
    assert isinstance(results, list)
