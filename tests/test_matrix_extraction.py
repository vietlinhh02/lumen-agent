"""Tests for chunk-aware matrix extraction node."""

from __future__ import annotations

from datetime import UTC, datetime
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


def _make_project_paper(
    pp_id=None,
    title="Test Paper",
    abstract="Test abstract",
    updated_at: datetime | None = None,
    matrix_row=None,
):
    pp = SimpleNamespace()
    pp.id = pp_id or uuid4()
    pp.status = "saved"
    pp.paper = SimpleNamespace()
    pp.paper.title = title
    pp.paper.abstract = abstract
    pp.paper.authors = ["Author A"]
    pp.paper.year = 2024
    pp.paper.venue = "Test Venue"
    pp.paper.updated_at = updated_at or datetime.now(UTC)
    pp.matrix_row = matrix_row
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

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[chunk],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "research_problem": "Medical QA accuracy",
            "method": "We used dense retrieval.",
            "dataset_or_context": "PubMedQA",
            "key_result": "Improved accuracy by 5%",
            "limitation": "English only",
            "contribution": "Novel RAG pipeline",
            "relevance": "Directly relevant",
            "confidence": "high",
        }

        with patch("app.agents.nodes.get_provider", return_value=mock_provider), \
             patch("app.agents.nodes.get_matrix_verifier_provider", return_value=None):
            result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1
    assert result["matrix_rows"][0]["project_paper_id"] == str(pp_id)
    assert "dense retrieval" in result["matrix_rows"][0]["method"].lower()


@pytest.mark.asyncio
async def test_matrix_extraction_reports_progress_per_processed_paper():
    pp_id_1 = uuid4()
    pp_id_2 = uuid4()
    state = _make_state()
    db = _mock_db_with_papers(
        [
            _make_project_paper(pp_id=pp_id_1, title="Paper A"),
            _make_project_paper(pp_id=pp_id_2, title="Paper B"),
        ]
    )
    progress_updates: list[tuple[int, int, str]] = []

    async def _record_progress(processed: int, total: int, current: str) -> None:
        progress_updates.append((processed, total, current))

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=2,
        ),
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
            result = await matrix_extraction_node(
                state,
                db,
                progress_callback=_record_progress,
            )

    assert result["matrix_status"] == "completed"
    assert [update[0] for update in progress_updates] == [1, 2]
    assert all(update[1] == 2 for update in progress_updates)
    assert {update[2] for update in progress_updates} == {"Paper A", "Paper B"}


@pytest.mark.asyncio
async def test_matrix_extraction_skips_unchanged_cached_rows():
    from app.services.literature_matrix import build_content_hash

    pp_id = uuid4()
    updated_at = datetime(2026, 6, 18, tzinfo=UTC)
    cached_hash = build_content_hash(pp_id, updated_at)
    cached_row = SimpleNamespace(content_hash=cached_hash)
    state = _make_state()
    db = _mock_db_with_papers(
        [
            _make_project_paper(
                pp_id=pp_id,
                title="Cached Paper",
                updated_at=updated_at,
                matrix_row=cached_row,
            )
        ]
    )
    progress_updates: list[tuple[int, int, str]] = []

    async def _record_progress(processed: int, total: int, current: str) -> None:
        progress_updates.append((processed, total, current))

    with (
        patch("app.agents.nodes.retrieve_paper_evidence", new_callable=AsyncMock) as mock_retrieve,
        patch("app.services.literature_matrix.upsert_rows", new_callable=AsyncMock) as mock_upsert,
        patch("app.agents.nodes.get_provider") as mock_get_provider,
    ):
        result = await matrix_extraction_node(
            state,
            db,
            progress_callback=_record_progress,
        )

    mock_retrieve.assert_not_called()
    mock_upsert.assert_not_called()
    mock_get_provider.assert_not_called()
    assert result["matrix_status"] == "completed"
    assert result["matrix_rows"] == []
    assert progress_updates == [(1, 1, "Cached Paper")]


@pytest.mark.asyncio
async def test_matrix_extraction_reextracts_when_content_hash_changes():
    from app.services.literature_matrix import build_content_hash

    pp_id = uuid4()
    old_updated_at = datetime(2026, 6, 17, tzinfo=UTC)
    new_updated_at = datetime(2026, 6, 18, tzinfo=UTC)
    cached_row = SimpleNamespace(content_hash=build_content_hash(pp_id, old_updated_at))
    state = _make_state()
    db = _mock_db_with_papers(
        [
            _make_project_paper(
                pp_id=pp_id,
                title="Updated Paper",
                updated_at=new_updated_at,
                matrix_row=cached_row,
            )
        ]
    )

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ) as mock_upsert,
    ):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "research_problem": "Updated problem",
            "method": "Updated method",
            "dataset_or_context": "Updated context",
            "key_result": "Updated result",
            "limitation": "Updated limitation",
            "contribution": "Updated contribution",
            "relevance": "Updated relevance",
            "confidence": "high",
        }

        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await matrix_extraction_node(state, db)

    upsert_call = mock_upsert.await_args
    assert upsert_call is not None
    upsert_rows = upsert_call.args[2]
    assert upsert_rows[0]["content_hash"] == build_content_hash(pp_id, new_updated_at)
    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1


@pytest.mark.asyncio
async def test_matrix_extraction_verifier_can_adjust_primary_result():
    pp_id = uuid4()
    state = _make_state()
    db = _mock_db_with_papers([_make_project_paper(pp_id=pp_id, title="Verifier Paper")])

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        primary_provider = AsyncMock()
        primary_provider.complete_structured.return_value = {
            "research_problem": "Primary problem",
            "method": "Primary method",
            "dataset_or_context": "Primary context",
            "key_result": "Primary result",
            "limitation": "Primary limitation",
            "contribution": "Primary contribution",
            "relevance": "Primary relevance",
            "confidence": "high",
        }
        verifier_provider = AsyncMock()
        verifier_provider.complete_structured.return_value = {
            "research_problem": "Verified problem",
            "method": "Verified method",
            "dataset_or_context": "Verified context",
            "key_result": "Verified result",
            "limitation": "Verified limitation",
            "contribution": "Verified contribution",
            "relevance": "Verified relevance",
            "confidence": "high",
        }

        with (
            patch("app.agents.nodes.get_provider", return_value=primary_provider),
            patch(
                "app.agents.nodes.get_matrix_verifier_provider",
                return_value=verifier_provider,
            ),
        ):
            result = await matrix_extraction_node(state, db)

    row = result["matrix_rows"][0]
    assert row["method"] == "Verified method"
    assert row["key_result"] == "Verified result"
    assert row["extraction_confidence"] == "medium"


@pytest.mark.asyncio
async def test_matrix_extraction_verifier_failure_falls_back_to_primary():
    pp_id = uuid4()
    state = _make_state()
    db = _mock_db_with_papers([_make_project_paper(pp_id=pp_id, title="Fallback Paper")])

    with (
        patch(
            "app.agents.nodes.retrieve_paper_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
    ):
        primary_provider = AsyncMock()
        primary_provider.complete_structured.return_value = {
            "research_problem": "Primary problem",
            "method": "Primary method",
            "dataset_or_context": "Primary context",
            "key_result": "Primary result",
            "limitation": "Primary limitation",
            "contribution": "Primary contribution",
            "relevance": "Primary relevance",
            "confidence": "high",
        }
        verifier_provider = AsyncMock()
        verifier_provider.complete_structured.side_effect = Exception("Verifier timeout")

        with (
            patch("app.agents.nodes.get_provider", return_value=primary_provider),
            patch(
                "app.agents.nodes.get_matrix_verifier_provider",
                return_value=verifier_provider,
            ),
        ):
            result = await matrix_extraction_node(state, db)

    row = result["matrix_rows"][0]
    assert row["method"] == "Primary method"
    assert row["key_result"] == "Primary result"
    assert row["extraction_confidence"] == "high"


@pytest.mark.asyncio
async def test_matrix_extraction_no_chunks_falls_back():
    pp_id = uuid4()
    state = _make_state()

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.hybrid_retrieval.encode_text",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
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

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.hybrid_retrieval.encode_text",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
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

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.hybrid_retrieval.encode_text",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
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

        with patch("app.agents.nodes.get_provider", return_value=mock_provider), \
             patch("app.agents.nodes.get_matrix_verifier_provider", return_value=None):
            result = await matrix_extraction_node(state, db)

        assert result["matrix_rows"][0]["extraction_confidence"] == "medium"


@pytest.mark.asyncio
async def test_matrix_extraction_persist_failure_sets_status():
    pp_id = uuid4()
    state = _make_state()

    pp = _make_project_paper(pp_id=pp_id)
    db = _mock_db_with_papers([pp])

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.hybrid_retrieval.encode_text",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection lost"),
        ),
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

    with (
        patch(
            "app.agents.nodes.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.hybrid_retrieval.encode_text",
            new_callable=AsyncMock,
            return_value=[0.0] * 1536,
        ),
        patch(
            "app.services.literature_matrix.upsert_rows",
            new_callable=AsyncMock,
            return_value=1,
        ),
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
