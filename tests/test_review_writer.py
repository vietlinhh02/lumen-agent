"""Tests for RAG-aware review_writer_node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import review_writer_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunk(project_paper_id=None, section_label="method", chunk_text="We used BERT."):
    return RetrievedChunk(
        project_paper_id=project_paper_id or uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type="method",
        page_start=1,
        page_end=2,
        content_hash=None,
        score=0.8,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_matrix_row(pp_id=None, method="RAG", dataset="PubMedQA"):
    row = SimpleNamespace()
    row.project_paper_id = pp_id or uuid4()
    row.research_problem = "Medical QA"
    row.method = method
    row.dataset_or_context = dataset
    row.key_result = "Improved accuracy"
    row.limitation = "English only"
    row.contribution = "Novel approach"
    row.relevance = "Directly relevant"
    return row


def _make_state(project_id=None, user_topic="RAG for medical QA"):
    return ResearchState(
        project_id=project_id or uuid4(),
        user_id=uuid4(),
        user_topic=user_topic,
    )


def _mock_db_sequential(results):
    """Create a mock DB that returns different results on successive execute() calls."""
    db = AsyncMock()
    call_index = {"i": 0}

    async def mock_execute(stmt):
        idx = call_index["i"]
        call_index["i"] += 1
        if idx < len(results):
            return results[idx]
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db.execute = mock_execute
    return db


def _result_with_rows(rows):
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_writer_no_matrix_rows():
    state = _make_state()
    db = _mock_db_sequential([_result_with_rows([])])  # no matrix rows

    result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "No matrix rows" in result["errors"][0]


@pytest.mark.asyncio
async def test_review_writer_no_saved_papers():
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id)]
    db = _mock_db_sequential(
        [
            _result_with_rows(rows),  # matrix rows
            _result_with_rows([]),  # no project_papers
        ]
    )

    result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "No saved papers" in result["errors"][0]


@pytest.mark.asyncio
async def test_review_writer_generates_with_valid_citations():
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id)]
    chunk = _make_chunk(project_paper_id=pp_id)

    db = _mock_db_sequential(
        [
            _result_with_rows(rows),  # matrix rows
            _result_with_rows([SimpleNamespace(id=pp_id)]),  # project_papers
            _result_with_rows([pp_id]),  # valid pp_ids for validation
            _result_with_rows([SimpleNamespace(id=pp_id, paper_id=uuid4())]),  # for references
        ]
    )

    with patch(
        "app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[chunk]
    ):
        with patch(
            "app.services.report_generation._persist_report", new_callable=AsyncMock
        ) as mock_persist:
            mock_persist.return_value = SimpleNamespace(id=uuid4())
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "sections": [
                    {
                        "heading": "Introduction",
                        "paragraphs": [
                            {
                                "text": "RAG improves factuality.",
                                "citation_paper_ids": [str(pp_id)],
                            }
                        ],
                    }
                ]
            }
            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await review_writer_node(state, db)

    assert result["report_status"] == "completed"
    assert len(result["report_sections"]) == 1


@pytest.mark.asyncio
async def test_review_writer_invalid_citations_trimmed():
    valid_pp = uuid4()
    invalid_pp = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=valid_pp)]

    db = _mock_db_sequential(
        [
            _result_with_rows(rows),  # matrix rows
            _result_with_rows([SimpleNamespace(id=valid_pp)]),  # project_papers
            _result_with_rows([valid_pp]),  # valid pp_ids for validation
            _result_with_rows([SimpleNamespace(id=valid_pp, paper_id=uuid4())]),  # for references
        ]
    )

    with patch(
        "app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]
    ):
        with patch(
            "app.services.report_generation._persist_report", new_callable=AsyncMock
        ) as mock_persist:
            mock_persist.return_value = SimpleNamespace(id=uuid4())
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "sections": [
                    {
                        "heading": "Results",
                        "paragraphs": [
                            {
                                "text": "Some claim.",
                                "citation_paper_ids": [str(valid_pp), str(invalid_pp)],
                            }
                        ],
                    }
                ]
            }
            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await review_writer_node(state, db)

    assert result["report_status"] == "completed"
    # Invalid citation should be trimmed, valid one kept
    paras = result["report_sections"][0]["paragraphs"]
    assert len(paras[0]["citation_paper_ids"]) == 1


@pytest.mark.asyncio
async def test_review_writer_llm_failure():
    state = _make_state()
    rows = [_make_matrix_row()]

    db = _mock_db_sequential(
        [
            _result_with_rows(rows),  # matrix rows
            _result_with_rows([SimpleNamespace(id=uuid4())]),  # project_papers
        ]
    )

    with patch(
        "app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "Review generation failed" in result["errors"][0]


@pytest.mark.asyncio
async def test_review_writer_no_project_id():
    state = ResearchState(project_id=None, user_id=uuid4())
    db = AsyncMock()

    result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "No project_id" in result["errors"][0]
