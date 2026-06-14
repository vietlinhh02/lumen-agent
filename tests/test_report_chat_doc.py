"""Tests for report_chat_doc service — generate + edit Markdown documents."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.report_chat_doc import (
    generate_markdown_for_project,
    edit_section,
    parse_markdown_sections,
)


def test_parse_markdown_sections_splits_by_h2():
    md = "## Intro\nParagraph 1.\n\n## Methods\nParagraph 2.\n\n## Results\nParagraph 3.\n"
    sections = parse_markdown_sections(md)
    assert len(sections) == 3
    assert sections[0]["heading"] == "Intro"
    assert "Paragraph 1" in sections[0]["body"]
    assert sections[2]["heading"] == "Results"


def test_parse_markdown_sections_with_no_headings():
    md = "Just a paragraph."
    sections = parse_markdown_sections(md)
    assert len(sections) == 1
    assert sections[0]["heading"] == ""


def _make_db_with_matrix_then_none(matrix_rows):
    """Mock DB: first .execute returns matrix rows, second returns None (no existing doc)."""
    db = AsyncMock()
    call_index = {"i": 0}

    async def mock_execute(stmt):
        idx = call_index["i"]
        call_index["i"] += 1
        result = MagicMock()
        if idx == 0:
            result.scalars.return_value.all.return_value = matrix_rows
        else:
            result.scalar_one_or_none.return_value = None
        return result

    db.execute = mock_execute
    return db


@pytest.mark.asyncio
async def test_generate_markdown_for_project_calls_provider_and_writes():
    project_id = uuid4()
    document_id = uuid4()
    user_id = uuid4()

    matrix_rows = [
        SimpleNamespace(
            project_paper_id=uuid4(),
            research_problem="P",
            method="RAG",
            dataset_or_context="PubMedQA",
            key_result="+5% accuracy",
            limitation="English only",
            contribution="Novel RAG",
            relevance="High",
        )
    ]
    db = _make_db_with_matrix_then_none(matrix_rows)

    with patch(
        "app.services.report_chat_doc.retrieve_project_evidence",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with patch("app.services.report_chat_doc.get_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "title": "Test Report",
                "sections": [{"heading": "Intro", "body": "Some intro text."}],
            }
            mock_get_provider.return_value = mock_provider

            result = await generate_markdown_for_project(
                db=db,
                project_id=project_id,
                document_id=document_id,
                user_id=user_id,
                topic="RAG for medical QA",
                research_question="How does RAG help?",
                include_gaps=True,
            )

    assert result["title"] == "Test Report"
    assert "## Intro" in result["markdown"]
    assert result["version"] == 1


@pytest.mark.asyncio
async def test_edit_section_rewrites_only_one_section():
    document_id = uuid4()
    project_id = uuid4()
    db = AsyncMock()

    async def mock_execute(stmt):
        result = MagicMock()
        # doc lookup returns None (no persistence) — version stays 1
        result.scalar_one_or_none.return_value = None
        return result

    db.execute = mock_execute

    current_md = "## Intro\nOriginal intro.\n\n## Methods\nOriginal methods.\n"

    with patch("app.services.report_chat_doc.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "section": {"heading": "Intro", "body": "Rewritten intro."},
        }
        mock_get_provider.return_value = mock_provider

        result = await edit_section(
            db=db,
            document_id=document_id,
            project_id=project_id,
            section_index=0,
            instruction="make it shorter",
            current_markdown=current_md,
        )

    assert "Rewritten intro." in result["markdown"]
    assert "Original methods." in result["markdown"]  # preserved
    assert result["section_index"] == 0
