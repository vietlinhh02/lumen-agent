"""Tests for project knowledge graph context and retrieval integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.knowledge_graph import build_graph_context, expand_query_with_graph_context


def _project_paper(method="RAG", dataset="PubMedQA", limitation="English only"):
    pp_id = uuid4()
    paper = SimpleNamespace(
        title=f"Paper {str(pp_id)[:8]}",
        year=2024,
        abstract="A medical QA paper.",
        authors=[{"name": "Ada"}],
        venue="TestConf",
        url="https://example.com",
    )
    matrix = SimpleNamespace(
        method=method,
        dataset_or_context=dataset,
        limitation=limitation,
    )
    return SimpleNamespace(id=pp_id, paper=paper, matrix_row=matrix)


def _db_with_project_papers(project_papers):
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = project_papers
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_build_graph_context_summarizes_project_concepts():
    project_id = uuid4()
    db = _db_with_project_papers(
        [
            _project_paper(method="RAG", dataset="PubMedQA", limitation="English only"),
            _project_paper(method="RAG", dataset="MedQA", limitation="Small sample"),
        ]
    )

    context = await build_graph_context(db, project_id, query="medical rag limitations")

    assert "Knowledge graph context:" in context
    assert "Central methods: RAG" in context
    assert "Central datasets or contexts:" in context
    assert "Recurring limitations:" in context
    assert "shared method" in context


@pytest.mark.asyncio
async def test_expand_query_with_graph_context_adds_concepts():
    project_id = uuid4()
    db = _db_with_project_papers(
        [
            _project_paper(method="RAG", dataset="PubMedQA", limitation="English only"),
            _project_paper(method="RAG", dataset="PubMedQA", limitation="English only"),
        ]
    )

    expanded = await expand_query_with_graph_context(db, project_id, "limitations")

    assert expanded.startswith("limitations")
    assert "RAG" in expanded
    assert "PubMedQA" in expanded


@pytest.mark.asyncio
async def test_retrieve_project_evidence_embeds_graph_expanded_query():
    from app.services.hybrid_retrieval import retrieve_project_evidence

    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    with (
        patch(
            "app.services.knowledge_graph.expand_query_with_graph_context",
            new_callable=AsyncMock,
            return_value="limitations RAG PubMedQA",
        ),
        patch("app.services.hybrid_retrieval.encode_text", return_value=[0.1] * 2000) as encode,
        patch("app.services.hybrid_retrieval.get_settings") as settings,
    ):
        settings.return_value.reranker_top_n = 10
        settings.return_value.embedding_provider = "openai"
        await retrieve_project_evidence(db, uuid4(), "limitations", use_reranker=False)

    encode.assert_called_once_with("limitations RAG PubMedQA", task=None)
