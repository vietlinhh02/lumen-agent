"""Tests for conflict_detection_node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import conflict_detection_node
from app.agents.state import ResearchState


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

    # 1st: matrix rows, 2nd: valid project_paper_ids, 3rd: delete old conflicts
    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([pp_a, pp_b]),
            _result_with_rows([]),
        ]
    )

    with patch("app.services.conflict_detection.get_provider") as mock_get_provider:
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

    # 1st call: matrix rows, 2nd call: valid project_papers (empty)
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

    # 1st call: matrix rows, 2nd call: valid project_papers
    db = _mock_db_sequential(
        [
            _result_with_rows(rows),
            _result_with_rows([pp_a, pp_b]),
        ]
    )

    with patch("app.services.conflict_detection.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []  # graceful empty result


@pytest.mark.asyncio
async def test_conflict_detection_node_no_project_id():
    """Node returns failed status when project_id is None."""
    state = ResearchState(project_id=None, user_id=uuid4())
    db = AsyncMock()

    result = await conflict_detection_node(state, db)

    assert result["conflict_status"] == "failed"
    assert "No project_id" in result["errors"][0]
