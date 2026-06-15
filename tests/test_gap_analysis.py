"""Tests for RAG-aware gap_analysis_node with multi-query retrieval."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import gap_analysis_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunk(
    project_paper_id=None, section_label="limitation", chunk_text="English only evaluation."
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
        content_type="limitation",
        page_start=1,
        page_end=2,
        content_hash=None,
        score=0.8,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_matrix_row(pp_id=None, method="RAG", dataset="PubMedQA", limitation="English only"):
    row = SimpleNamespace()
    row.project_paper_id = pp_id or uuid4()
    row.research_problem = "Medical QA"
    row.method = method
    row.dataset_or_context = dataset
    row.key_result = "Improved accuracy"
    row.limitation = limitation
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
    db = MagicMock()
    call_index = {"i": 0}

    async def mock_execute(stmt):
        idx = call_index["i"]
        call_index["i"] += 1
        if idx < len(results):
            return results[idx]
        # Fallback: empty result
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db.execute = mock_execute
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _result_with_rows(rows):
    """Create a mock DB result that returns `rows` from scalars().all()."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gap_analysis_no_matrix_rows():
    state = _make_state()
    db = _mock_db_sequential([_result_with_rows([])])

    result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "No matrix rows" in result["errors"][0]


@pytest.mark.asyncio
async def test_gap_analysis_insufficient_matrix_rows():
    state = _make_state()
    rows = [_make_matrix_row() for _ in range(3)]  # < 5
    db = _mock_db_sequential([_result_with_rows(rows)])

    result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "INSUFFICIENT_MATRIX" in result["errors"][0]


@pytest.mark.asyncio
async def test_gap_analysis_generates_and_persists():
    pp_id_1 = uuid4()
    pp_id_2 = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id_1) for _ in range(5)]
    chunk = _make_chunk(project_paper_id=pp_id_1)

    # 1st call: matrix rows, 2nd call: valid project_paper_ids
    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([pp_id_1, pp_id_2]),
        ]
    )

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[chunk],
        ),
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=2),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Low-resource language evaluation",
                    "description": "Most papers evaluate English only.",
                    "evidence_paper_ids": [str(pp_id_1), str(pp_id_2)],
                    "evidence_summary": "Papers report English-only evaluation.",
                    "suggested_direction": "Evaluate on Vietnamese datasets.",
                    "confidence": "medium",
                }
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "completed"
    assert len(result["gaps"]) == 1
    assert "Low-resource" in result["gaps"][0]["title"]


@pytest.mark.asyncio
async def test_gap_analysis_filters_invalid_evidence():
    state = _make_state()
    valid_pp_id = uuid4()
    valid_pp_id_2 = uuid4()
    invalid_pp_id = uuid4()
    rows = [_make_matrix_row(pp_id=valid_pp_id) for _ in range(5)]

    # 1st call: matrix rows, 2nd call: valid project_papers
    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([valid_pp_id, valid_pp_id_2]),
        ]
    )

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]
        ),
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=1),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Gap with valid evidence",
                    "description": "Test with multiple papers supporting.",
                    "evidence_paper_ids": [str(valid_pp_id), str(valid_pp_id_2)],
                    "evidence_summary": "Valid",
                    "suggested_direction": "Test",
                    "confidence": "medium",
                },
                {
                    "title": "Gap with invalid evidence",
                    "description": "Test",
                    "evidence_paper_ids": [str(invalid_pp_id)],
                    "evidence_summary": "Invalid",
                    "suggested_direction": "Test",
                    "confidence": "medium",
                },
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    # Gap with invalid evidence should be filtered out; only valid one remains
    assert result["gap_status"] == "completed"
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["title"] == "Gap with valid evidence"


@pytest.mark.asyncio
async def test_gap_analysis_llm_failure():
    state = _make_state()
    rows = [_make_matrix_row() for _ in range(5)]
    # 1st call: matrix rows, 2nd call: valid project_paper_ids
    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([]),
        ]
    )

    with patch(
        "app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "Gap analysis failed" in result["errors"][0]


@pytest.mark.asyncio
async def test_gap_analysis_no_project_id():
    state = ResearchState(project_id=None, user_id=uuid4())
    db = AsyncMock()

    result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "No project_id" in result["errors"][0]


# ── New tests: multi-query retrieval + evidence coverage guard ──────────────


@pytest.mark.asyncio
async def test_gap_analysis_multi_query_retrieval_called():
    """Verify that retrieve_project_evidence is called multiple times (multi-query)."""
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id) for _ in range(5)]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_id])])

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_retrieve,
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=1),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Gap with two papers",
                    "description": "Needs at least two evidence papers.",
                    "evidence_paper_ids": [str(pp_id), str(uuid4())],
                    "evidence_summary": "Test",
                    "suggested_direction": "Test",
                    "confidence": "medium",
                }
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            await gap_analysis_node(state, db)

    # Multi-query: 4 retrieval queries
    assert mock_retrieve.call_count == 4


@pytest.mark.asyncio
async def test_gap_analysis_rejects_fewer_than_2_evidence_papers():
    """Gap with only 1 evidence paper is rejected (guard)."""
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id) for _ in range(5)]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_id])])

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock) as mock_upsert,
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Single paper gap",
                    "description": "Only a unique limitation from one study.",
                    "evidence_paper_ids": [str(pp_id)],
                    "evidence_summary": "Limited coverage found in one source.",
                    "suggested_direction": "Future work",
                    "confidence": "medium",
                }
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "completed"
    assert len(result["gaps"]) == 0  # rejected: < 2 evidence papers
    mock_upsert.assert_not_called()


@pytest.mark.asyncio
async def test_gap_analysis_accepts_single_paper_gap_if_explicit():
    """Gap with 1 evidence paper is accepted if description mentions 'single paper'."""
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id) for _ in range(5)]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_id])])

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=1),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Single paper limitation",
                    "description": (
                        "This single paper reports a unique limitation not found elsewhere."
                    ),
                    "evidence_paper_ids": [str(pp_id)],
                    "evidence_summary": "Single paper finding",
                    "suggested_direction": "Investigate further",
                    "confidence": "medium",
                }
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert len(result["gaps"]) == 1  # accepted: "single paper" in description


@pytest.mark.asyncio
async def test_gap_analysis_downgrades_confidence_without_chunks():
    """When no chunks are retrieved, high confidence is downgraded to medium."""
    pp_id_1 = uuid4()
    pp_id_2 = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id_1) for _ in range(5)]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_id_1, pp_id_2])])

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=1),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Two paper gap",
                    "description": "Two papers support this gap.",
                    "evidence_paper_ids": [str(pp_id_1), str(pp_id_2)],
                    "evidence_summary": "Two papers",
                    "suggested_direction": "Future work",
                    "confidence": "high",
                }
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["confidence"] == "medium"  # downgraded


@pytest.mark.asyncio
async def test_gap_analysis_dedupes_chunks_by_id():
    """Multi-query retrieval deduplicates chunks by chunk_id."""
    pp_id = uuid4()
    chunk = _make_chunk(project_paper_id=pp_id, chunk_text="Unique limitation text.")

    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id) for _ in range(5)]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_id])])

    call_count = {"n": 0}

    async def mock_retrieve(db, project_id, query, limit=15):
        call_count["n"] += 1
        # Return same chunk on first call, empty on rest (simulates dedup)
        if call_count["n"] == 1:
            return [chunk]
        return []

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            side_effect=mock_retrieve,
        ),
        patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=1),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "gaps": [
                {
                    "title": "Gap with deduped chunks",
                    "description": "Supported by two papers.",
                    "evidence_paper_ids": [str(pp_id), str(uuid4())],
                    "evidence_summary": "Test",
                    "suggested_direction": "Test",
                    "confidence": "medium",
                }
            ]
        }
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "completed"
    # All 4 queries were made
    assert call_count["n"] == 4
