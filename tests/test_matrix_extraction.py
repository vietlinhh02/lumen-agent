"""Tests for chunk-aware matrix extraction node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import _build_chunk_context, _rows_to_json_safe, matrix_extraction_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunk(
    project_paper_id=None,
    section_label: str | None = "method",
    content_type="method",
    chunk_text="We used BERT for encoding.",
    score=0.8,
):
    return RetrievedChunk(
        project_paper_id=project_paper_id or uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type=content_type,
        page_start=1,
        page_end=2,
        content_hash=None,
        score=score,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_project_paper(pp_id=None, title="Test Paper", abstract="Test abstract"):
    pp = SimpleNamespace()
    pp.id = pp_id or uuid4()
    pp.status = "saved"
    pp.paper = SimpleNamespace()
    pp.paper.title = title
    pp.paper.abstract = abstract
    pp.paper.authors = ["Author A"]
    pp.paper.year = 2024
    pp.paper.venue = "Test Venue"
    return pp


def _make_state(project_id=None, user_topic="RAG for medical QA"):
    return ResearchState(
        project_id=project_id or uuid4(),
        user_id=uuid4(),
        user_topic=user_topic,
    )


def _mock_db_with_papers(papers):
    """Create a mock DB session that returns the given papers from execute()."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = papers
    db.execute = AsyncMock(return_value=mock_result)
    return db


# ── _build_chunk_context tests ───────────────────────────────────────────────


def test_build_chunk_context_with_chunks():
    chunks = [
        _make_chunk(section_label="method", chunk_text="We used BERT."),
        _make_chunk(section_label="results", chunk_text="Accuracy improved 5%."),
    ]
    result = _build_chunk_context(chunks)
    assert "---method---" in result
    assert "---results---" in result
    assert "We used BERT." in result
    assert "Accuracy improved 5%." in result


def test_build_chunk_context_empty():
    result = _build_chunk_context([])
    assert result == "No full-text sections available."


def test_build_chunk_context_missing_label():
    chunk = _make_chunk(section_label=None, content_type="narrative")
    result = _build_chunk_context([chunk])
    assert "---narrative---" in result


def test_build_chunk_context_respects_max_chars():
    long_chunk = _make_chunk(chunk_text="x" * 5000)
    result = _build_chunk_context([long_chunk], max_chars=1000)
    assert result == "No full-text sections available."


def test_build_chunk_context_includes_chunks_within_limit():
    c1 = _make_chunk(section_label="method", chunk_text="a" * 100)
    c2 = _make_chunk(section_label="results", chunk_text="b" * 100)
    result = _build_chunk_context([c1, c2], max_chars=500)
    assert "---method---" in result
    assert "---results---" in result


# ── _rows_to_json_safe tests ─────────────────────────────────────────────────


def test_rows_to_json_safe_converts_uuids():
    uid = uuid4()
    rows = [{"project_paper_id": uid, "method": "test"}]
    result = _rows_to_json_safe(rows)
    assert result[0]["project_paper_id"] == str(uid)
    assert result[0]["method"] == "test"


def test_rows_to_json_safe_preserves_strings():
    rows = [{"project_paper_id": str(uuid4()), "method": "test"}]
    result = _rows_to_json_safe(rows)
    assert result[0]["method"] == "test"


# ── matrix_extraction_node tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_matrix_extraction_no_saved_papers():
    state = _make_state()
    db = _mock_db_with_papers([])

    result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert result["matrix_rows"] == []


@pytest.mark.asyncio
async def test_matrix_extraction_skips_existing_rows():
    """When all papers already have matrix rows, the query returns empty."""
    state = _make_state()
    db = _mock_db_with_papers([])  # query already filters out existing

    result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert result["matrix_rows"] == []


@pytest.mark.asyncio
async def test_matrix_extraction_with_chunks():
    pp_id = uuid4()
    state = _make_state()

    chunk = _make_chunk(
        project_paper_id=pp_id,
        section_label="method",
        chunk_text="We used dense retrieval.",
    )

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with patch(
        "app.agents.nodes.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[chunk],
    ):
        with patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "research_problem": "Medical QA accuracy",
                "method": "Dense retrieval with BERT",
                "dataset_or_context": "PubMedQA",
                "key_result": "Improved accuracy by 5%",
                "limitation": "English only",
                "contribution": "Novel RAG pipeline",
                "relevance": "Directly relevant",
                "confidence": "high",
            }

            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1
    assert result["matrix_rows"][0]["project_paper_id"] == str(pp_id)
    assert "Dense retrieval" in result["matrix_rows"][0]["method"]


@pytest.mark.asyncio
async def test_matrix_extraction_no_chunks_falls_back():
    pp_id = uuid4()
    state = _make_state()

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with patch(
        "app.agents.nodes.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "research_problem": "Test problem",
                "method": "Test method",
                "dataset_or_context": "Test context",
                "key_result": "Test result",
                "limitation": "not specified",
                "contribution": "Test contribution",
                "relevance": "Test relevance",
                "confidence": "medium",
            }

            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1


@pytest.mark.asyncio
async def test_matrix_extraction_partial_failure():
    """One paper fails extraction, others succeed."""
    pp_id_1 = uuid4()
    pp_id_2 = uuid4()
    state = _make_state()

    pp1 = _make_project_paper(pp_id=pp_id_1, title="Paper A")
    pp2 = _make_project_paper(pp_id=pp_id_2, title="Paper B")
    db = _mock_db_with_papers([pp1, pp2])

    with patch(
        "app.agents.nodes.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ):
            call_count = 0

            async def mock_complete(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("LLM timeout")
                return {
                    "research_problem": "Test",
                    "method": "Test",
                    "dataset_or_context": "Test",
                    "key_result": "Test",
                    "limitation": "not specified",
                    "contribution": "Test",
                    "relevance": "Test",
                    "confidence": "medium",
                }

            mock_provider = AsyncMock()
            mock_provider.complete_structured = mock_complete

            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1  # only second paper succeeded


@pytest.mark.asyncio
async def test_matrix_extraction_invalid_confidence_defaults_to_medium():
    pp_id = uuid4()
    state = _make_state()

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with patch(
        "app.agents.nodes.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "research_problem": "Test",
                "method": "Test",
                "dataset_or_context": "Test",
                "key_result": "Test",
                "limitation": "not specified",
                "contribution": "Test",
                "relevance": "Test",
                "confidence": "very_high",  # invalid
            }

            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await matrix_extraction_node(state, db)

    assert result["matrix_rows"][0]["extraction_confidence"] == "medium"


@pytest.mark.asyncio
async def test_matrix_extraction_persist_failure_sets_status():
    pp_id = uuid4()
    state = _make_state()

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with patch(
        "app.agents.nodes.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection lost"),
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "research_problem": "Test",
                "method": "Test",
                "dataset_or_context": "Test",
                "key_result": "Test",
                "limitation": "not specified",
                "contribution": "Test",
                "relevance": "Test",
                "confidence": "medium",
            }

            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "failed"
    assert len(result["matrix_rows"]) == 1  # rows still returned for state


@pytest.mark.asyncio
async def test_matrix_extraction_rows_are_json_serializable():
    """Returned matrix_rows must be JSON-safe (no raw UUIDs)."""
    import json

    pp_id = uuid4()
    state = _make_state()

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with patch(
        "app.agents.nodes.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "research_problem": "Test",
                "method": "Test",
                "dataset_or_context": "Test",
                "key_result": "Test",
                "limitation": "not specified",
                "contribution": "Test",
                "relevance": "Test",
                "confidence": "medium",
            }

            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await matrix_extraction_node(state, db)

    # This should NOT raise TypeError: Object of type UUID is not JSON serializable
    json.dumps(result["matrix_rows"])
