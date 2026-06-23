"""Tests for auto_search_and_save service entry point."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.search_session import auto_search_and_save


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", uuid4()))
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_auto_search_rejects_invalid_target_count():
    """Service validates target_count before creating job."""
    db = _mock_db()
    project = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    user = SimpleNamespace(id=uuid4())

    # Mock the project lookup
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=project))

    for bad in (5, 75, 150, 200):
        with pytest.raises(ValueError):
            await auto_search_and_save(db, user, project.id, "test query", bad)


@pytest.mark.asyncio
async def test_auto_search_returns_404_for_missing_project():
    db = _mock_db()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    user = SimpleNamespace(id=uuid4())
    result = await auto_search_and_save(db, user, uuid4(), "query", 50)
    assert result == {"error": "Project not found"}


@pytest.mark.asyncio
async def test_auto_search_creates_job_and_run():
    db = _mock_db()
    project = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    user = SimpleNamespace(id=uuid4())

    # First call (project lookup) returns project; second call (concurrent
    # job lookup) returns no running job.
    project_result = MagicMock(scalar_one_or_none=MagicMock(return_value=project))
    scalars_inner = MagicMock()
    scalars_inner.first = MagicMock(return_value=None)
    no_running_job = MagicMock()
    no_running_job.scalars = MagicMock(return_value=scalars_inner)

    call_index = {"n": 0}

    async def mock_execute(stmt):
        call_index["n"] += 1
        if call_index["n"] == 1:
            return project_result
        return no_running_job

    db.execute = mock_execute

    with patch("app.services.search_session.ensure_future") as mock_ensure:
        result = await auto_search_and_save(db, user, project.id, "RAG medical QA", 50)

    assert result["status"] == "running"
    assert result["target_count"] == 50
    assert "job_id" in result
    assert "session_id" in result
    # Worker was launched
    assert mock_ensure.called


@pytest.mark.asyncio
async def test_auto_search_rejects_concurrent_job_for_same_user():
    """A 2nd auto_search for the same user while one is running returns 429."""
    db = _mock_db()
    project = SimpleNamespace(id=uuid4(), owner_id=uuid4())
    user = SimpleNamespace(id=uuid4())

    # First lookup: project exists
    # Second lookup: existing running job for this user
    project_result = MagicMock(scalar_one_or_none=MagicMock(return_value=project))
    running_job = SimpleNamespace(id=uuid4(), status="running", job_type="auto_search")
    scalars_inner = MagicMock()
    scalars_inner.first = MagicMock(return_value=running_job)
    job_result = MagicMock()
    job_result.scalars = MagicMock(return_value=scalars_inner)

    call_index = {"n": 0}

    async def mock_execute(stmt):
        call_index["n"] += 1
        if call_index["n"] == 1:
            return project_result
        return job_result

    db.execute = mock_execute

    result = await auto_search_and_save(db, user, project.id, "RAG", 50)
    assert result == {"error": "Another auto-search is already running", "status_code": 429}
