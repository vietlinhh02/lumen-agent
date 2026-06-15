"""Tests for conflict_detection_node with full-text evidence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import conflict_detection_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk


def _make_chunk(
    project_paper_id=None, section_label="method", chunk_text="We used RAG with dense retrieval."
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
        content_type=section_label or "method",
        page_start=1,
        page_end=2,
        content_hash=None,
        score=0.8,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_matrix_row(pp_id=None, method="RAG", dataset="PubMedQA", key_result="Improved accuracy"):
    row = SimpleNamespace()
    row.project_paper_id = pp_id or uuid4()
    row.research_problem = "Medical QA"
    row.method = method
    row.dataset_or_context = dataset
    row.key_result = key_result
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
    db = MagicMock()
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
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _result_with_rows(rows):
    """Create a mock DB result that returns `rows` from scalars().all()."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


# ── Existing tests (adapted) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conflict_detection_too_few_rows():
    """Skip conflict detection when < 4 matrix rows."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    state = _make_state()
    rows = [_make_matrix_row() for _ in range(3)]
    db = _mock_db_sequential([_result_with_rows(rows)])

    result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []


@pytest.mark.asyncio
async def test_conflict_detection_shared_method():
    """Detect conflict when two papers share same method but opposing results."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(
            pp_id=pp_a, method="RAG", dataset="PubMedQA", key_result="Improved accuracy by 10%"
        ),
        _make_matrix_row(
            pp_id=pp_b, method="RAG", dataset="SQuAD", key_result="No significant improvement"
        ),
        _make_matrix_row(method="BM25", dataset="MS MARCO", key_result="Baseline results"),
        _make_matrix_row(method="Dense retrieval", dataset="NQ", key_result="Moderate improvement"),
    ]

    chunk_a = _make_chunk(
        project_paper_id=pp_a,
        section_label="results",
        chunk_text="RAG improved accuracy by 10% on PubMedQA.",
    )

    # 1st: matrix rows, 2nd: valid project_paper_ids,
    # then retrieve_paper_evidence calls (2 papers × vector search + keyword)
    db_results = [
        _result_with_rows(rows),
        _result_with_rows([pp_a, pp_b]),
    ]
    db = _mock_db_sequential(db_results)

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence", new_callable=AsyncMock
        ) as mock_retrieve,
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        mock_retrieve.return_value = [chunk_a]
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "conflicts": [
                {
                    "title": "Opposing findings on RAG accuracy",
                    "description": (
                        "Paper A reports improvement while Paper B reports no improvement."
                    ),
                    "paper_a_id": str(pp_a),
                    "paper_b_id": str(pp_b),
                    "shared_context": "RAG method",
                    "claim_a": "Improved accuracy by 10%",
                    "claim_b": "No significant improvement",
                    "possible_explanation": "Different evaluation settings",
                    "confidence": "medium",
                }
            ]
        }
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert len(result) == 1
    assert "Opposing" in result[0]["title"]
    # Verify retrieve_paper_evidence was called for the group
    assert mock_retrieve.call_count >= 1


@pytest.mark.asyncio
async def test_conflict_detection_no_shared_context():
    """No conflicts when no papers share method or dataset."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    state = _make_state()
    rows = [
        _make_matrix_row(method="RAG", dataset="PubMedQA"),
        _make_matrix_row(method="BM25", dataset="Natural Questions"),
        _make_matrix_row(method="Dense retrieval", dataset="SQuAD"),
        _make_matrix_row(method="Sparse retrieval", dataset="MS MARCO"),
    ]

    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([]),
        ]
    )

    result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []


@pytest.mark.asyncio
async def test_conflict_detection_llm_failure_graceful():
    """LLM failure doesn't crash the workflow."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG"),
        _make_matrix_row(pp_id=pp_b, method="RAG"),
        _make_matrix_row(method="BM25"),
        _make_matrix_row(method="Dense"),
    ]

    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([pp_a, pp_b]),
        ]
    )

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []


@pytest.mark.asyncio
async def test_conflict_detection_node_no_project_id():
    """Node returns failed status when project_id is None."""
    state = ResearchState(project_id=None, user_id=uuid4())
    db = AsyncMock()

    result = await conflict_detection_node(state, db)

    assert result["conflict_status"] == "failed"
    assert "No project_id" in result["errors"][0]


# ── New tests: evidence coverage guards ─────────────────────────────────────


@pytest.mark.asyncio
async def test_conflict_skipped_when_no_chunk_evidence_downgrades_confidence():
    """When no chunks are retrieved, high confidence is downgraded to medium."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(
            pp_id=pp_a, method="RAG", dataset="PubMedQA", key_result="Improved accuracy"
        ),
        _make_matrix_row(pp_id=pp_b, method="RAG", dataset="SQuAD", key_result="No improvement"),
        _make_matrix_row(method="BM25", dataset="MS MARCO"),
        _make_matrix_row(method="Dense", dataset="NQ"),
    ]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_a, pp_b])])

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "conflicts": [
                {
                    "title": "Opposing RAG results",
                    "description": "A says yes, B says no.",
                    "paper_a_id": str(pp_a),
                    "paper_b_id": str(pp_b),
                    "shared_context": "RAG method",
                    "claim_a": "Yes",
                    "claim_b": "No",
                    "possible_explanation": "Different setup",
                    "confidence": "high",
                }
            ]
        }
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert len(result) == 1
    assert result[0]["confidence"] == "medium"  # downgraded from high


@pytest.mark.asyncio
async def test_conflict_skipped_when_empty_shared_context():
    """Conflict with empty shared_context is skipped."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG"),
        _make_matrix_row(pp_id=pp_b, method="RAG"),
        _make_matrix_row(method="BM25"),
        _make_matrix_row(method="Dense"),
    ]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_a, pp_b])])

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "conflicts": [
                {
                    "title": "Empty context conflict",
                    "description": "Some description",
                    "paper_a_id": str(pp_a),
                    "paper_b_id": str(pp_b),
                    "shared_context": "",
                    "claim_a": "A claim",
                    "claim_b": "B claim",
                    "possible_explanation": None,
                    "confidence": "medium",
                }
            ]
        }
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []  # empty shared_context → skipped


@pytest.mark.asyncio
async def test_conflict_skipped_when_invalid_paper_id():
    """Conflict referencing invalid project_paper_id is skipped."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    invalid_id = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG"),
        _make_matrix_row(method="RAG"),
        _make_matrix_row(method="BM25"),
        _make_matrix_row(method="Dense"),
    ]

    db = _mock_db_sequential(
        [_result_with_rows(rows), _result_with_rows([pp_a])]  # invalid_id not in saved
    )

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "conflicts": [
                {
                    "title": "Bad ID conflict",
                    "description": "Desc",
                    "paper_a_id": str(pp_a),
                    "paper_b_id": str(invalid_id),
                    "shared_context": "RAG",
                    "claim_a": "A",
                    "claim_b": "B",
                    "possible_explanation": None,
                    "confidence": "medium",
                }
            ]
        }
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []  # invalid paper ID → skipped


@pytest.mark.asyncio
async def test_conflict_same_method_different_dataset_no_conflict():
    """Same method but different datasets should not produce a conflict
    (LLM should return empty list)."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG", dataset="PubMedQA", key_result="Acc 85%"),
        _make_matrix_row(pp_id=pp_b, method="RAG", dataset="SQuAD", key_result="Acc 72%"),
        _make_matrix_row(method="BM25", dataset="MS MARCO"),
        _make_matrix_row(method="Dense", dataset="NQ"),
    ]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_a, pp_b])])

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence", new_callable=AsyncMock
        ) as mock_retrieve,
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        chunk = _make_chunk(project_paper_id=pp_a)
        mock_retrieve.return_value = [chunk]
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {"conflicts": []}
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []  # LLM says no conflict


@pytest.mark.asyncio
async def test_conflict_retrieve_evidence_is_called_per_paper():
    """Verify that retrieve_paper_evidence is called for each paper in the group."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG", dataset="PubMedQA", key_result="Positive"),
        _make_matrix_row(pp_id=pp_b, method="RAG", dataset="SQuAD", key_result="Negative"),
        _make_matrix_row(method="BM25", dataset="MS MARCO"),
        _make_matrix_row(method="Dense", dataset="NQ"),
    ]

    db = _mock_db_sequential([_result_with_rows(rows), _result_with_rows([pp_a, pp_b])])

    with (
        patch(
            "app.services.conflict_detection.retrieve_paper_evidence", new_callable=AsyncMock
        ) as mock_retrieve,
        patch("app.services.conflict_detection.get_provider") as mock_get_provider,
    ):
        mock_retrieve.return_value = []
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {"conflicts": []}
        mock_get_provider.return_value = mock_provider

        await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    # 1 group (method: RAG, 2 papers) → 2 retrieve calls
    assert mock_retrieve.call_count == 2
