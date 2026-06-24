"""Tests for the T3 matrix-row evidence endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routers import matrix as matrix_router
from app.services.hybrid_retrieval import RetrievedChunk


def _make_chunk(
    *,
    chunk_text="We fine-tuned BERT on the SQuAD dataset.",
    content_type="method",
    section_label="Method",
) -> RetrievedChunk:
    return RetrievedChunk(
        project_paper_id=uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type=content_type,
        page_start=3,
        page_end=3,
        content_hash=None,
        score=0.82,
        keyword_score=0.4,
        vector_score=0.5,
    )


def _make_row():
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        project_paper_id=uuid4(),
        research_problem="How well does RAG answer medical questions?",
        method="Retrieval-augmented BERT",
        key_result="92% accuracy",
        limitation="Small test set",
        project_paper=SimpleNamespace(paper=SimpleNamespace(title="RAG for Medical QA")),
    )


def test_evidence_query_uses_claim_fields():
    row = _make_row()
    query = matrix_router._evidence_query(row, "RAG for Medical QA")
    assert "Retrieval-augmented BERT" in query
    assert "92% accuracy" in query


def test_evidence_query_falls_back_to_title():
    row = SimpleNamespace(
        research_problem=None, method=None, key_result=None, limitation=None
    )
    assert matrix_router._evidence_query(row, "Some Paper") == "Some Paper"


@pytest.mark.asyncio
async def test_get_matrix_row_evidence_returns_chunks():
    """Matrix row -> evidence endpoint -> >= 1 chunk with text/type/section."""
    row = _make_row()
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)

    chunk = _make_chunk()
    with (
        patch.object(matrix_router, "_verify_project_owner", AsyncMock()),
        patch.object(
            matrix_router,
            "retrieve_paper_evidence",
            AsyncMock(return_value=[chunk]),
        ) as ret,
    ):
        resp = await matrix_router.get_matrix_row_evidence(
            project_id=row.project_id,
            row_id=row.id,
            limit=5,
            content_types="method,results",
            db=db,
            user=MagicMock(),
        )

    assert resp.project_paper_id == row.project_paper_id
    assert resp.paper_title == "RAG for Medical QA"
    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.chunk_text
    assert item.content_type == "method"
    assert item.section_label == "Method"

    # CSV content_types is parsed into a list and forwarded to retrieval.
    assert ret.await_args.kwargs["content_types"] == ["method", "results"]


@pytest.mark.asyncio
async def test_get_matrix_row_evidence_404_when_row_missing():
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    from fastapi import HTTPException

    with patch.object(matrix_router, "_verify_project_owner", AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await matrix_router.get_matrix_row_evidence(
                project_id=uuid4(),
                row_id=uuid4(),
                db=db,
                user=MagicMock(),
            )
    assert exc.value.status_code == 404
