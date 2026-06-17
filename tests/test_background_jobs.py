"""Tests for background job system and optimized queries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models import User
from app.services.search_session import get_saved_paper_ids

# ── get_saved_paper_ids batch query tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_saved_paper_ids_empty_input():
    db = AsyncMock()
    result = await get_saved_paper_ids(db, uuid4(), [])
    assert result == []


@pytest.mark.asyncio
async def test_get_saved_paper_ids_no_matches():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    papers = [
        {"semantic_scholar_id": "ss1", "doi": "doi1", "arxiv_id": "arxiv1"},
    ]
    result = await get_saved_paper_ids(db, uuid4(), papers)
    assert result == []


@pytest.mark.asyncio
async def test_get_saved_paper_ids_batch_query():
    """Verify the function uses batch queries instead of N+1."""
    project_id = uuid4()
    paper_id = uuid4()

    # Mock the paper lookup result
    paper_result = MagicMock()
    paper_result.all.return_value = [
        (paper_id, "ss1", "doi1", "arxiv1"),
    ]

    # Mock the project_paper lookup result
    pp_result = MagicMock()
    pp_result.scalars.return_value.all.return_value = [paper_id]

    call_count = {"n": 0}

    async def mock_execute(stmt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return paper_result
        return pp_result

    db = AsyncMock()
    db.execute = mock_execute

    papers = [
        {"semantic_scholar_id": "ss1", "doi": "doi1", "arxiv_id": "arxiv1"},
        {"semantic_scholar_id": "ss2", "doi": "doi2", "arxiv_id": "arxiv2"},
    ]
    result = await get_saved_paper_ids(db, project_id, papers)

    # Should have made exactly 2 DB calls (paper lookup + project_paper lookup)
    # NOT 8 calls (4 per paper x 2 papers)
    assert call_count["n"] == 2
    assert "ss1" in result or "doi1" in result or "arxiv1" in result


# ── auto_save_high_papers background job tests ──────────────────────────────


@pytest.mark.asyncio
async def test_auto_save_creates_background_job():
    """Auto-save should create a BackgroundJob and return job_id."""
    from app.services.search_session import auto_save_high_papers

    project_id = uuid4()
    session_id = uuid4()
    user = cast(User, SimpleNamespace(id=uuid4()))

    # Mock session with high-scoring papers
    run = SimpleNamespace(
        screening_scores=["high", "medium", "high"],
        results_json=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
    )

    db = AsyncMock()
    call_count = {"n": 0}

    async def mock_execute(stmt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return MagicMock(scalar_one_or_none=MagicMock(return_value=run))
        return MagicMock()

    db.execute = mock_execute
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", uuid4()))

    with patch("asyncio.ensure_future"):
        result = await auto_save_high_papers(db, user, project_id, session_id)

    assert "job_id" in result
    assert result["status"] == "running"
    assert result["total"] == 2  # 2 high-scoring papers


@pytest.mark.asyncio
async def test_auto_save_no_high_papers():
    """Auto-save with no high papers returns immediately."""
    from app.services.search_session import auto_save_high_papers

    run = SimpleNamespace(
        screening_scores=["low", "medium"],
        results_json=[{"title": "A"}, {"title": "B"}],
    )

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run)))

    result = await auto_save_high_papers(
        db, cast(User, SimpleNamespace(id=uuid4())), uuid4(), uuid4()
    )
    assert result["saved"] == 0
    assert result["skipped"] == 2


@pytest.mark.asyncio
async def test_auto_save_session_not_found():
    """Auto-save with invalid session returns error."""
    from app.services.search_session import auto_save_high_papers

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await auto_save_high_papers(
        db, cast(User, SimpleNamespace(id=uuid4())), uuid4(), uuid4()
    )
    assert "error" in result
    assert "Session not found" in result["error"]
