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

    for bad in (10, 50, 75, 150, 200):
        with pytest.raises(ValueError):
            await auto_search_and_save(db, user, project.id, "test query", bad)


@pytest.mark.asyncio
async def test_auto_search_returns_404_for_missing_project():
    db = _mock_db()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    user = SimpleNamespace(id=uuid4())
    result = await auto_search_and_save(db, user, uuid4(), "query", 25)
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
        result = await auto_search_and_save(db, user, project.id, "RAG medical QA", 25)

    assert result["status"] == "running"
    assert result["target_count"] == 25
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

    result = await auto_search_and_save(db, user, project.id, "RAG", 25)
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
        total=25,
        progress_json={"phase": "queued", "target_count": 25},
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
                mock_score.return_value = ["high"] * 25 + ["medium"] * 100 + ["low"] * 25

                with patch("app.services.search_session.save_paper_to_project") as mock_save:
                    mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

                    await _run_auto_search_job(
                        job_id, session_id, project_id, user_id, "RAG", 25,
                        timeout_seconds=5,
                    )

        # search_and_download was called with max_per_source=60 (the new
        # per-query cap; we now run multiple queries in parallel so each
        # gets a smaller budget to keep total work bounded).
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("max_per_source") == 60


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
            captured["queries"] = locals_dict.get("queries")
            captured["target_count"] = locals_dict.get("target_count")
        return None

    with patch("app.services.search_session.ensure_future", side_effect=fake_ensure_future), \
         patch("app.services.search_session._generate_queries_from_project") as mock_gen:
        mock_gen.return_value = [
            "RAG medical QA retrieval augmented generation",
            "clinical decision support RAG evaluation",
        ]
        result = await auto_search_and_save(db, user, project.id, "", 25)

    assert result["status"] == "running"
    assert result["query_was_generated"] is True
    # The primary query returned is the first one
    assert result["query"] == "RAG medical QA retrieval augmented generation"
    # The worker received the full list
    assert captured.get("queries") == [
        "RAG medical QA retrieval augmented generation",
        "clinical decision support RAG evaluation",
    ]
    assert captured.get("target_count") == 25
    assert mock_gen.called


@pytest.mark.asyncio
async def test_auto_search_uses_explicit_query_when_provided():
    """When the caller provides a non-empty query, _generate_queries_from_project
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
         patch("app.services.search_session._generate_queries_from_project") as mock_gen:
        result = await auto_search_and_save(db, user, project.id, "explicit query", 25)

    assert result["query_was_generated"] is False
    assert result["query"] == "explicit query"
    assert not mock_gen.called


# ── Multi-query search tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_queries_from_project_returns_list():
    """``_generate_queries_from_project`` returns 4-6 deduplicated queries
    (or a single fallback to project.topic on LLM error)."""
    from app.services.search_session import _generate_queries_from_project

    project = SimpleNamespace(
        title="Cancer Immunotherapy",
        topic="non-chemotherapeutic cancer treatments",
        research_question="How effective is immunotherapy vs chemotherapy?",
        review_protocol=None,
    )

    # Mock the LLM to return a realistic 5-query result
    fake_queries = [
        "immunotherapy cancer clinical trials efficacy",
        "CAR T cell therapy tumor clearance mathematical modeling",
        "non-chemotherapeutic cancer treatment safety adverse events",
        "radiotherapy immunotherapy synergy combination outcomes",
        "computational modeling tumor immune dynamics",
    ]
    with patch("app.ai.provider.get_provider") as mock_get_provider:
        provider = MagicMock()
        provider.complete_structured = AsyncMock(return_value={"queries": fake_queries})
        mock_get_provider.return_value = provider

        queries = await _generate_queries_from_project(project)

    assert len(queries) == 5
    assert queries == fake_queries


@pytest.mark.asyncio
async def test_generate_queries_dedupes_case_insensitive():
    """Duplicate queries (case-insensitive) are removed while preserving order."""
    from app.services.search_session import _generate_queries_from_project

    project = SimpleNamespace(
        title="X", topic="topic", research_question=None, review_protocol=None,
    )
    with patch("app.ai.provider.get_provider") as mock_get_provider:
        provider = MagicMock()
        provider.complete_structured = AsyncMock(return_value={
            "queries": [
                "Cancer Immunotherapy",
                "cancer immunotherapy",  # case-insensitive dup
                "Targeted Therapy",
                "Cancer Immunotherapy",  # exact dup
                "Combination Therapy",
            ]
        })
        mock_get_provider.return_value = provider

        queries = await _generate_queries_from_project(project)

    assert queries == [
        "Cancer Immunotherapy",
        "Targeted Therapy",
        "Combination Therapy",
    ]


@pytest.mark.asyncio
async def test_generate_queries_falls_back_to_topic_on_error():
    """If the LLM call raises, we fall back to [project.topic] (1 element)."""
    from app.services.search_session import _generate_queries_from_project

    project = SimpleNamespace(
        title="X", topic="fallback topic", research_question=None, review_protocol=None,
    )
    with patch("app.ai.provider.get_provider") as mock_get_provider:
        provider = MagicMock()
        provider.complete_structured = AsyncMock(side_effect=Exception("LLM down"))
        mock_get_provider.return_value = provider

        queries = await _generate_queries_from_project(project)

    assert queries == ["fallback topic"]


@pytest.mark.asyncio
async def test_generate_queries_empty_topic_returns_empty_list():
    """If both LLM fails AND project has no topic, return [] so caller can 400."""
    from app.services.search_session import _generate_queries_from_project

    project = SimpleNamespace(
        title="X", topic="", research_question=None, review_protocol=None,
    )
    with patch("app.ai.provider.get_provider") as mock_get_provider:
        provider = MagicMock()
        provider.complete_structured = AsyncMock(side_effect=Exception("LLM down"))
        mock_get_provider.return_value = provider

        queries = await _generate_queries_from_project(project)

    assert queries == []


def test_deduplicate_with_match_counts_returns_count():
    """A paper appearing in 2 queries gets match_count=2."""
    from app.services.search_session import _deduplicate_with_match_counts

    p1 = SimpleNamespace(
        title="Paper A", abstract=None, semantic_scholar_id="ss1",
        arxiv_id=None, doi=None, source_name="", source_specific={},
    )
    p2 = SimpleNamespace(
        title="Paper B", abstract=None, semantic_scholar_id="ss2",
        arxiv_id=None, doi=None, source_name="", source_specific={},
    )
    papers = [p1, p2, p1, p1, p2]  # p1 x3, p2 x2

    unique, counts = _deduplicate_with_match_counts(papers)

    assert len(unique) == 2
    assert counts["ss1"] == 3
    assert counts["ss2"] == 2


def test_deduplicate_with_match_counts_falls_back_to_title():
    """When no S2/arxiv/DOI, dedupe by lowercased title."""
    from app.services.search_session import _deduplicate_with_match_counts

    p1 = SimpleNamespace(
        title="Machine Learning in Oncology",
        abstract=None, semantic_scholar_id=None,
        arxiv_id=None, doi=None, source_name="", source_specific={},
    )
    p2 = SimpleNamespace(
        title="machine learning in oncology",  # same after lowercase
        abstract=None, semantic_scholar_id=None,
        arxiv_id=None, doi=None, source_name="", source_specific={},
    )
    p3 = SimpleNamespace(
        title="Different Paper",
        abstract=None, semantic_scholar_id=None,
        arxiv_id=None, doi=None, source_name="", source_specific={},
    )
    papers = [p1, p2, p3]

    unique, counts = _deduplicate_with_match_counts(papers)

    assert len(unique) == 2
    assert counts["machine learning in oncology"] == 2
    assert counts["different paper"] == 1


def test_auto_search_eligibility_rejects_non_cancer_methods_paper():
    from app.services.search_session import _score_auto_search_eligibility

    paper = SimpleNamespace(
        title="Matched-Pair Designs for Platform Trials",
        abstract=(
            "We propose a statistical methodology for covariate adjustment "
            "using HIV and schizophrenia datasets."
        ),
        venue="Statistics in Medicine",
        source_specific={},
    )

    signal = _score_auto_search_eligibility(
        paper,
        ["non-chemotherapeutic cancer interventions clinical efficacy"],
    )

    assert signal == {"category": "off_topic_condition", "boost": 0}


def test_auto_search_eligibility_penalizes_pure_cancer_methodology():
    from app.services.search_session import _score_auto_search_eligibility

    paper = SimpleNamespace(
        title="Sample Size Calculation for Oncology Basket Trials",
        abstract=(
            "This simulation study evaluates power calculation methods for "
            "oncology trial design without patient outcomes."
        ),
        venue="Clinical Trials",
        source_specific={},
    )

    signal = _score_auto_search_eligibility(
        paper,
        ["cancer immunotherapy efficacy safety"],
    )

    assert signal == {"category": "methodology_only", "boost": 0}


def test_auto_search_eligibility_keeps_oncolytic_malignancy_review():
    from app.services.search_session import _score_auto_search_eligibility

    paper = SimpleNamespace(
        title=(
            "Comparative safety and efficacy of oncolytic virotherapy for "
            "individuals with malignancies"
        ),
        abstract="A systematic review of randomized trials and adverse events.",
        venue="Cancer Medicine",
        source_specific={},
    )

    signal = _score_auto_search_eligibility(
        paper,
        ["cancer immunotherapy efficacy safety"],
    )

    assert signal == {"category": "clinical_or_domain_evidence", "boost": 1}


def test_auto_search_eligibility_penalizes_cancer_mathematical_model():
    from app.services.search_session import _score_auto_search_eligibility

    paper = SimpleNamespace(
        title=(
            "A Mathematical Model for Chemotherapy, Immunotherapy and "
            "Virotherapy Treatments of Cancer"
        ),
        abstract="We analyze travelling waves in a computational model.",
        venue="arXiv",
        source_specific={},
    )

    signal = _score_auto_search_eligibility(
        paper,
        ["cancer immunotherapy efficacy safety"],
    )

    assert signal == {"category": "methodology_only", "boost": 0}


def test_auto_search_eligibility_boosts_cancer_evidence_paper():
    from app.services.search_session import _score_auto_search_eligibility

    paper = SimpleNamespace(
        title="CAR T-Cell Therapy in Relapsed Leukemia",
        abstract=(
            "A clinical trial reports response rate, overall survival, and "
            "adverse event outcomes in patients with leukemia."
        ),
        venue="Journal of Clinical Oncology",
        source_specific={},
    )

    signal = _score_auto_search_eligibility(
        paper,
        ["cancer immunotherapy efficacy safety"],
    )

    assert signal == {"category": "clinical_or_domain_evidence", "boost": 1}


def test_auto_search_ranks_and_caps_candidates_before_llm_scoring():
    from app.services.search_session import (
        _auto_search_score_candidate_limit,
        _deduplicate_with_match_counts,
        _rank_auto_search_candidates,
    )

    clinical = SimpleNamespace(
        title="CAR T clinical trial in leukemia",
        abstract="A clinical trial reports survival and adverse events.",
        year=2024,
        citation_count=10,
        semantic_scholar_id="clinical",
        arxiv_id=None,
        doi=None,
        source_name="exa",
        source_specific={},
    )
    method = SimpleNamespace(
        title="Mathematical model of cancer immunotherapy",
        abstract="We analyze a computational model.",
        year=2026,
        citation_count=500,
        semantic_scholar_id="method",
        arxiv_id=None,
        doi=None,
        source_name="arxiv",
        source_specific={},
    )
    off_topic = SimpleNamespace(
        title="Matched-pair designs using schizophrenia datasets",
        abstract="Statistical methodology for covariate adjustment.",
        year=2026,
        citation_count=900,
        semantic_scholar_id="off",
        arxiv_id=None,
        doi=None,
        source_name="exa",
        source_specific={},
    )

    papers = [off_topic, method, clinical, clinical]
    unique, match_counts = _deduplicate_with_match_counts(papers)
    ranked = _rank_auto_search_candidates(
        unique,
        match_counts,
        ["cancer immunotherapy efficacy safety"],
        limit=2,
    )

    assert _auto_search_score_candidate_limit(25) == 75
    assert ranked == [clinical, method]


@pytest.mark.asyncio
async def test_run_auto_search_phase1_runs_multiple_queries_concurrently():
    """Phase 1 issues one search_and_download call per query (gather'd)."""
    from app.services.search_session import _run_auto_search_job

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    session_id = uuid4()

    job = SimpleNamespace(
        id=job_id, status="pending", progress=0, total=25,
        progress_json={"phase": "queued"}, result={}, error_message=None,
    )
    run = SimpleNamespace(id=session_id, user_query="q", results_json=[], screening_scores=[])
    user = SimpleNamespace(id=user_id)

    with patch("app.services.search_session.async_session_factory") as mock_factory:
        bg_db = AsyncMock()
        # Use a function-based side_effect so we don't run out of responses
        # during the long Phase 4 loop (12 papers each triggers a few
        # ``execute`` calls).
        execute_calls = {"n": 0}

        def make_execute_result(*, with_scalar=False, scalar_value=None):
            result = MagicMock()
            if with_scalar:
                result.scalar_one_or_none = MagicMock(return_value=scalar_value)
            return result

        async def mock_execute(stmt):
            execute_calls["n"] += 1
            n = execute_calls["n"]
            if n == 1:
                return make_execute_result(with_scalar=True, scalar_value=job)
            if n == 2:
                return make_execute_result(with_scalar=True, scalar_value=run)
            if n == 3:
                return make_execute_result(with_scalar=True, scalar_value=user)
            # All subsequent calls (progress_json updates, run commit, etc.)
            # return a bare MagicMock — no specific return needed.
            return MagicMock()

        bg_db.execute = mock_execute
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=bg_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        # Track call count for search_and_download
        search_call_queries: list = []

        async def fake_search(req, max_per_source=None):
            search_call_queries.append(req.query)
            # 3 papers per query, all distinct (so 12 total after dedupe)
            return SimpleNamespace(
                raw_papers=[
                    SimpleNamespace(
                        title=f"Paper {req.query}-{i}",
                        abstract=None, year=2024, venue=None,
                        doi=None, arxiv_id=f"{req.query}-{i}",
                        semantic_scholar_id=None, url=None,
                        citation_count=0, authors=[],
                        source_name="arxiv", source_specific={},
                    )
                    for i in range(3)
                ],
                response=SimpleNamespace(source_diagnostics=[]),
            )

        with patch("app.services.search_session.search_and_download", side_effect=fake_search), \
             patch("app.services.search_session.batch_score_papers") as mock_score, \
             patch("app.services.search_session.save_paper_to_project") as mock_save:

            # All papers score "high" so all 12 are picked (capped at target=25).
            mock_score.return_value = ["high"] * 12
            mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

            queries = ["q1", "q2", "q3", "q4"]
            await _run_auto_search_job(
                job_id, session_id, project_id, user_id, queries, 25,
                timeout_seconds=10,
            )

        # search_and_download was called once per query
        assert sorted(search_call_queries) == ["q1", "q2", "q3", "q4"]

        # job.result should include queries_used + multi_match_papers
        assert job.result["queries_count"] == 4
        assert job.result["queries_used"] == ["q1", "q2", "q3", "q4"]
        assert job.result["candidates_after_dedupe"] == 12  # all distinct


@pytest.mark.asyncio
async def test_run_auto_search_bumps_low_to_medium_when_multi_match():
    """A paper scored 'low' but matched by 2+ queries gets promoted to medium."""
    from app.services.search_session import _run_auto_search_job

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    session_id = uuid4()

    job = SimpleNamespace(
        id=job_id, status="pending", progress=0, total=25,
        progress_json={"phase": "queued"}, result={}, error_message=None,
    )
    run = SimpleNamespace(id=session_id, user_query="q", results_json=[], screening_scores=[])
    user = SimpleNamespace(id=user_id)

    with patch("app.services.search_session.async_session_factory") as mock_factory:
        bg_db = AsyncMock()
        bg_db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=job)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=run)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=user)),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ])
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=bg_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        # Two queries, both return the SAME paper (so match_count=2).
        # All papers score "low" in the LLM.
        shared = SimpleNamespace(
            title="Shared paper",
            abstract=None, year=2024, venue=None,
            doi=None, arxiv_id="2401.99999",
            semantic_scholar_id=None, url=None,
            citation_count=0, authors=[],
            source_name="arxiv", source_specific={},
        )
        other = SimpleNamespace(
            title="Other paper (only query 1)",
            abstract=None, year=2024, venue=None,
            doi=None, arxiv_id="2401.11111",
            semantic_scholar_id=None, url=None,
            citation_count=0, authors=[],
            source_name="arxiv", source_specific={},
        )

        async def fake_search(req, max_per_source=None):
            if req.query == "q1":
                return SimpleNamespace(raw_papers=[shared, other], response=SimpleNamespace(source_diagnostics=[]))
            return SimpleNamespace(raw_papers=[shared], response=SimpleNamespace(source_diagnostics=[]))

        with patch("app.services.search_session.search_and_download", side_effect=fake_search), \
             patch("app.services.search_session.batch_score_papers") as mock_score, \
             patch("app.services.search_session.save_paper_to_project") as mock_save:

            # Both papers scored "low" by LLM
            mock_score.return_value = ["low", "low"]
            mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

            await _run_auto_search_job(
                job_id, session_id, project_id, user_id, ["q1", "q2"], 25,
                timeout_seconds=10,
            )

        # The "shared" paper matched both queries → match_count=2 → bumped to medium.
        # The "other" paper matched only q1 → match_count=1 → stays low.
        # Only the bumped medium paper is saved (low is filtered out by Phase 3).
        assert job.result["saved_count"] == 1
        # job.result records the multi-match signal for debugging.
        assert job.result["multi_match_papers"] >= 1


@pytest.mark.asyncio
async def test_run_auto_search_caps_scoring_candidates_for_target_25():
    from app.services.search_session import _run_auto_search_job

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    session_id = uuid4()

    job = SimpleNamespace(
        id=job_id, status="pending", progress=0, total=25,
        progress_json={"phase": "queued"}, result={}, error_message=None,
    )
    run = SimpleNamespace(id=session_id, user_query="q", results_json=[], screening_scores=[])
    user = SimpleNamespace(id=user_id)
    project = SimpleNamespace(
        id=project_id,
        topic="cancer immunotherapy efficacy safety",
        research_question="Which interventions are effective and safe?",
    )

    with patch("app.services.search_session.async_session_factory") as mock_factory:
        bg_db = AsyncMock()
        execute_calls = {"n": 0}

        async def mock_execute(stmt):
            execute_calls["n"] += 1
            lookup = {
                1: job,
                2: run,
                3: user,
                4: project,
            }.get(execute_calls["n"])
            if lookup is not None:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=lookup))
            return MagicMock()

        bg_db.execute = mock_execute
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=bg_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        async def fake_search(req, max_per_source=None):
            return SimpleNamespace(
                raw_papers=[
                    SimpleNamespace(
                        title=f"Clinical cancer immunotherapy paper {i}",
                        abstract="A clinical trial reports survival and safety.",
                        year=2024,
                        venue=None,
                        doi=None,
                        arxiv_id=f"2401.{i:05d}",
                        semantic_scholar_id=None,
                        url=None,
                        citation_count=i,
                        authors=[],
                        source_name="exa",
                        source_specific={},
                    )
                    for i in range(220)
                ],
                response=SimpleNamespace(source_diagnostics=[]),
            )

        scored_count = {}

        async def fake_score(papers, *args):
            scored_count["n"] = len(papers)
            return ["high"] * len(papers)

        with patch("app.services.search_session.search_and_download", side_effect=fake_search), \
             patch("app.services.search_session.batch_score_papers", side_effect=fake_score), \
             patch("app.services.search_session.save_paper_to_project") as mock_save:
            mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

            await _run_auto_search_job(
                job_id, session_id, project_id, user_id, ["q1"], 25,
                timeout_seconds=10,
            )

    assert scored_count["n"] == 75
    assert job.result["candidates_after_dedupe"] == 220
    assert job.result["candidates_scored"] == 75
    assert job.result["saved_count"] == 25


@pytest.mark.asyncio
async def test_run_auto_search_continues_after_phase2_budget_exceeded():
    from app.services.search_session import _run_auto_search_job

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    session_id = uuid4()

    job = SimpleNamespace(
        id=job_id, status="pending", progress=0, total=1,
        progress_json={"phase": "queued"}, result={}, error_message=None,
    )
    run = SimpleNamespace(id=session_id, user_query="q", results_json=[], screening_scores=[])
    user = SimpleNamespace(id=user_id)
    project = SimpleNamespace(
        id=project_id,
        topic="cancer immunotherapy efficacy safety",
        research_question="Which interventions are effective and safe?",
    )

    with patch("app.services.search_session.async_session_factory") as mock_factory:
        bg_db = AsyncMock()
        execute_calls = {"n": 0}

        async def mock_execute(stmt):
            execute_calls["n"] += 1
            lookup = {
                1: job,
                2: run,
                3: user,
                4: project,
            }.get(execute_calls["n"])
            if lookup is not None:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=lookup))
            return MagicMock()

        bg_db.execute = mock_execute
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=bg_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        paper = SimpleNamespace(
            title="Clinical cancer immunotherapy paper",
            abstract="A clinical trial reports survival and safety.",
            year=2024,
            venue=None,
            doi=None,
            arxiv_id="2401.12345",
            semantic_scholar_id=None,
            url=None,
            citation_count=10,
            authors=[],
            source_name="exa",
            source_specific={},
        )

        async def fake_search(req, max_per_source=None):
            return SimpleNamespace(
                raw_papers=[paper],
                response=SimpleNamespace(source_diagnostics=[]),
            )

        async def fake_score(papers, *args):
            return ["high"] * len(papers)

        monotonic_values = iter([0, 0, 999])

        def fake_monotonic():
            try:
                return next(monotonic_values)
            except StopIteration:
                return 999

        with patch("app.services.search_session.search_and_download", side_effect=fake_search), \
             patch("app.services.search_session.batch_score_papers", side_effect=fake_score), \
             patch("app.services.search_session.save_paper_to_project") as mock_save, \
             patch("app.services.search_session.monotonic", side_effect=fake_monotonic):
            mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

            await _run_auto_search_job(
                job_id, session_id, project_id, user_id, ["q1"], 1,
                timeout_seconds=10,
            )

    assert job.status == "completed"
    assert job.error_message is None
    assert job.result["saved_count"] == 1
