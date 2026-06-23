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


@pytest.mark.asyncio
async def test_run_auto_search_phase1_calls_search_and_download():
    """Phase 1 invokes search_and_download with max_per_source=200."""
    from app.services.search_session import _run_auto_search_job

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    session_id = uuid4()

    # Mock the job + session + user
    job = SimpleNamespace(
        id=job_id,
        status="pending",
        progress=0,
        total=50,
        progress_json={"phase": "queued", "target_count": 50},
        result={},
        error_message=None,
    )
    run = SimpleNamespace(
        id=session_id,
        user_query="RAG",
        results_json=[],
        screening_scores=[],
    )
    user = SimpleNamespace(id=user_id)

    with patch("app.services.search_session.async_session_factory") as mock_factory:
        bg_db = AsyncMock()
        bg_db.execute = AsyncMock(side_effect=[
            # First: load job
            MagicMock(scalar_one_or_none=MagicMock(return_value=job)),
            # Second: load session
            MagicMock(scalar_one_or_none=MagicMock(return_value=run)),
            # Third: load user
            MagicMock(scalar_one_or_none=MagicMock(return_value=user)),
            # Subsequent execute calls (no specific result expected)
            MagicMock(),
        ])
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=bg_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock search_and_download to return 200 papers
        with patch("app.services.search_session.search_and_download") as mock_search:
            mock_paper = SimpleNamespace(
                title="Paper A", abstract="abstract", year=2024,
                venue="NeurIPS", doi=None, arxiv_id="2401.00001",
                semantic_scholar_id="ss1", url="https://example.com",
                citation_count=10, authors=[{"name": "Alice", "author_id": ""}],
                source_name="semantic_scholar", source_specific={},
            )
            mock_outcome = SimpleNamespace(
                raw_papers=[mock_paper] * 200,
                response=SimpleNamespace(source_diagnostics=[]),
            )
            mock_search.return_value = mock_outcome

            with patch("app.services.search_session.batch_score_papers") as mock_score:
                mock_score.return_value = ["high"] * 50 + ["medium"] * 100 + ["low"] * 50

                with patch("app.services.search_session.save_paper_to_project") as mock_save:
                    mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

                    await _run_auto_search_job(
                        job_id, session_id, project_id, user_id, "RAG", 50,
                        timeout_seconds=5,
                    )

        # search_and_download was called with max_per_source=200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("max_per_source") == 200


@pytest.mark.asyncio
async def test_auto_search_generates_query_when_empty():
    """When the caller provides an empty query, the backend auto-generates
    one from the project's topic via the LLM."""
    db = _mock_db()
    project = SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        title="Medical RAG",
        topic="Retrieval-augmented generation for medical QA",
        research_question="How effective is RAG for clinical decision support?",
        review_protocol=None,
    )
    user = SimpleNamespace(id=uuid4())

    # First call: project lookup. Second call: concurrent-job lookup (none).
    project_result = MagicMock(scalar_one_or_none=MagicMock(return_value=project))
    no_running_job = MagicMock()
    no_running_job.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))

    call_index = {"n": 0}

    async def mock_execute(stmt):
        call_index["n"] += 1
        if call_index["n"] == 1:
            return project_result
        return no_running_job

    db.execute = mock_execute

    captured: dict = {}

    def fake_ensure_future(coro):
        # Send None to advance the coroutine so its frame locals get populated
        try:
            coro.send(None)
        except StopIteration:
            pass
        except Exception:
            pass
        if hasattr(coro, "cr_frame") and coro.cr_frame is not None:
            locals_dict = coro.cr_frame.f_locals
            captured["query"] = locals_dict.get("query")
            captured["target_count"] = locals_dict.get("target_count")
        return None

    with patch("app.services.search_session.ensure_future", side_effect=fake_ensure_future), \
         patch("app.services.search_session._generate_query_from_project") as mock_gen:
        mock_gen.return_value = "RAG medical QA retrieval augmented generation"
        result = await auto_search_and_save(db, user, project.id, "", 50)

    assert result["status"] == "running"
    assert result["query_was_generated"] is True
    assert result["query"] == "RAG medical QA retrieval augmented generation"
    assert captured.get("query") == "RAG medical QA retrieval augmented generation"
    assert captured.get("target_count") == 50
    assert mock_gen.called


@pytest.mark.asyncio
async def test_auto_search_uses_explicit_query_when_provided():
    """When the caller provides a non-empty query, _generate_query_from_project
    is NOT called."""
    db = _mock_db()
    project = SimpleNamespace(
        id=uuid4(),
        owner_id=uuid4(),
        title="X", topic="X", research_question=None, review_protocol=None,
    )
    user = SimpleNamespace(id=uuid4())
    project_result = MagicMock(scalar_one_or_none=MagicMock(return_value=project))
    no_running_job = MagicMock()
    no_running_job.scalars = MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))

    call_index = {"n": 0}

    async def mock_execute(stmt):
        call_index["n"] += 1
        if call_index["n"] == 1:
            return project_result
        return no_running_job

    db.execute = mock_execute

    with patch("app.services.search_session.ensure_future"), \
         patch("app.services.search_session._generate_query_from_project") as mock_gen:
        result = await auto_search_and_save(db, user, project.id, "explicit query", 50)

    assert result["query_was_generated"] is False
    assert result["query"] == "explicit query"
    assert not mock_gen.called
