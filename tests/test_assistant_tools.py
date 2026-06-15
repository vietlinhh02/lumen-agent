import asyncio
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.assistant_tools import TOOL_REGISTRY
from app.services.assistant_tools import search_papers as search_papers_module
from app.services.assistant_tools.create_project import handle as create_project_handle
from app.services.assistant_tools.generate_report import handle as generate_report_handle
from app.services.assistant_tools.ids import coerce_uuid
from app.services.assistant_tools.qa_search_papers import handle as qa_search_papers_handle
from app.services.assistant_tools.save_paper import handle as save_paper_handle
from app.services.assistant_tools.search_papers import handle as search_papers_handle


def test_all_11_tools_registered():
    """Verify all production tools are registered, including the new ones."""
    expected = {
        "create_project",
        "search_papers",
        "save_paper_to_project",
        "save_papers_batch",
        "generate_matrix",
        "trigger_normalization",
        "detect_gaps",
        "detect_conflicts",
        "generate_report",
        "edit_report_section",
        "qa_search_papers",
    }
    assert set(TOOL_REGISTRY.keys()) == expected


def test_each_handler_is_async_callable():
    for name, handler in TOOL_REGISTRY.items():
        assert callable(handler), f"{name} not callable"
        import inspect

        assert inspect.iscoroutinefunction(handler), f"{name} not async"


def test_coerce_uuid_accepts_uuid_object_and_string():
    value = uuid4()

    assert coerce_uuid(value) == value
    assert coerce_uuid(str(value)) == value


@pytest.mark.asyncio
async def test_create_project_accepts_uuid_response_id():
    project_id = uuid4()
    document_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    doc_ref = {}

    async def refresh(obj):
        obj.id = document_id
        doc_ref["doc"] = obj

    db.refresh.side_effect = refresh
    runner = SimpleNamespace(
        history=[{"role": "user", "content": "AI trong y tế"}],
        project_id=None,
        document_id=None,
        emit=AsyncMock(),
    )

    with patch(
        "app.services.assistant_tools.create_project.svc_create_project",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(id=project_id),
    ):
        result = await create_project_handle(
            db,
            user,
            {
                "title": "AI cancer diagnosis",
                "topic": "AI in oncology diagnostics",
                "research_question": "How can AI improve cancer diagnosis accuracy?",
            },
            runner,
        )

    assert UUID(result["project_id"]) == project_id
    assert UUID(result["document_id"]) == document_id
    assert runner.project_id == project_id
    assert runner.document_id == document_id
    assert doc_ref["doc"].project_id == project_id
    # Should emit at least 2 events: project_created + progress
    assert runner.emit.await_count >= 2


@pytest.mark.asyncio
async def test_save_paper_accepts_uuid_project_id_and_returns_saved_status():
    project_id = uuid4()
    project_paper_id = uuid4()
    db = AsyncMock()
    user = SimpleNamespace(id=uuid4())

    with patch(
        "app.services.assistant_tools.save_paper.save_paper_to_project",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            project_paper_id=project_paper_id,
            full_text_status="pending",
        ),
    ) as save_mock:
        runner = SimpleNamespace(emit=AsyncMock())
        result = await save_paper_handle(
            db,
            user,
            {"project_id": project_id, "paper": {"title": "Paper", "authors": []}},
            runner,
        )

    assert save_mock.call_args.args[2] == project_id
    assert result["saved"] is True
    assert result["project_paper_id"] == str(project_paper_id)
    assert result["full_text_status"] == "pending"
    assert runner.emit.await_count >= 2  # progress events


@pytest.mark.asyncio
async def test_qa_search_papers_accepts_uuid_project_id():
    project_id = uuid4()
    db = AsyncMock()
    user = SimpleNamespace(id=uuid4())

    with (
        patch(
            "app.services.assistant_tools.qa_search_papers.retrieve_project_evidence",
            new_callable=AsyncMock,
            return_value=[],
        ) as retrieve_mock,
        patch("app.services.assistant_tools.qa_search_papers.get_provider") as provider_mock,
    ):
        provider_mock.return_value.complete = AsyncMock(return_value="No evidence yet.")
        result = await qa_search_papers_handle(
            db,
            user,
            {"project_id": project_id, "question": "What evidence exists?"},
        )

    assert retrieve_mock.call_args.args[1] == project_id
    assert result["answer"] == "No evidence yet."


@pytest.mark.asyncio
async def test_generate_report_writes_to_review_report():
    """generate_report should write ReviewReport and update ChatDocument."""
    project_id = uuid4()
    document_id = uuid4()
    report_id = uuid4()
    db = AsyncMock()
    user = SimpleNamespace(id=uuid4())
    doc = SimpleNamespace(id=document_id, project_id=project_id, version=0, content_md="")
    project = SimpleNamespace(topic="AI oncology", research_question="How accurate?")

    db.execute.side_effect = [
        # First call: production generate_report (project lookup)
        SimpleNamespace(scalar_one_or_none=lambda: project),
        # Second call: ChatDocument lookup
        SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: doc)),
        # Commit
        None,
    ]

    prod_result = {
        "id": str(report_id),
        "status": "completed",
        "title": "Literature Review: AI oncology",
        "content_markdown": "# Literature Review\n\nContent",
        "validation_status": "valid",
        "citation_audit": {
            "total_citations": 10,
            "valid_citations": 10,
            "invalid_citations": 0,
            "uncited_saved_papers": 0,
        },
    }

    with (
        patch(
            "app.services.assistant_tools.generate_report.production_generate_report",
            new_callable=AsyncMock,
            return_value=prod_result,
        ) as prod_mock,
        patch(
            "app.services.assistant_tools.generate_report.generate_markdown_for_project",
            new_callable=AsyncMock,
            return_value={"markdown": "# Report", "version": 1},
        ),
    ):
        runner = SimpleNamespace(emit=AsyncMock())
        result = await generate_report_handle(
            db,
            user,
            {"project_id": project_id, "include_gaps": True},
            runner,
        )

    # Should call production service (writes to ReviewReport)
    assert prod_mock.call_args.kwargs["project_id"] == project_id
    assert result["status"] == "completed"
    assert result["report_id"] == str(report_id)
    assert result["validation_status"] == "valid"
    # Should emit markdown_updated + progress events
    assert runner.emit.await_count >= 2


# ── save_papers_batch tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_papers_batch_handles_empty_input():
    from app.services.assistant_tools.save_papers_batch import handle

    runner = SimpleNamespace(emit=AsyncMock())
    result = await handle(
        AsyncMock(), SimpleNamespace(id=uuid4()),
        {"project_id": str(uuid4()), "papers": []},
        runner,
    )
    assert result["saved"] == 0
    assert result["failed"] == 0
    assert result["pdfs_available"] == 0
    assert runner.emit.await_count == 0  # no progress for empty batch


@pytest.mark.asyncio
async def test_save_papers_batch_saves_each_paper_and_counts_pdfs():
    from app.schemas.project import SavePaperResponse
    from app.services.assistant_tools.save_papers_batch import handle

    user = SimpleNamespace(id=uuid4())
    project_id = uuid4()

    # 3 papers, 2 already have PDF, 1 doesn't
    papers = [
        {"title": f"Paper {i}", "arxiv_id": f"123.{i}",
         "pdf_downloaded": i < 2, "pdf_path": f"/tmp/p{i}.pdf" if i < 2 else None}
        for i in range(3)
    ]

    async def fake_save(db, user, project_id, req):
        return SavePaperResponse(
            project_paper_id=uuid4(),
            paper_id=uuid4(),
            title=req.paper_title,
            status="saved",
            pdf_path=req.prefetched_pdf_path,
            full_text_status="ingesting" if req.prefetched_pdf_path else "pending",
        )

    with patch(
        "app.services.assistant_tools.save_papers_batch.save_paper_to_project",
        new_callable=AsyncMock,
        side_effect=fake_save,
    ):
        runner = SimpleNamespace(emit=AsyncMock())
        result = await handle(
            AsyncMock(),
            user,
            {"project_id": str(project_id), "papers": papers},
            runner,
        )

    assert result["saved"] == 3
    assert result["failed"] == 0
    assert result["pdfs_available"] == 2
    # Should emit at least start + end progress events
    assert runner.emit.await_count >= 2


@pytest.mark.asyncio
async def test_save_papers_batch_does_not_use_one_session_concurrently():
    from app.schemas.project import SavePaperResponse
    from app.services.assistant_tools.save_papers_batch import handle

    user = SimpleNamespace(id=uuid4())
    project_id = uuid4()
    papers = [{"title": f"Paper {idx}"} for idx in range(4)]
    busy = False

    async def fake_save(db, user, project_id, req):
        nonlocal busy
        if busy:
            raise AssertionError("concurrent DB use")
        busy = True
        await asyncio.sleep(0)
        busy = False
        return SavePaperResponse(
            project_paper_id=uuid4(),
            paper_id=uuid4(),
            title=req.paper_title,
            status="saved",
        )

    with patch(
        "app.services.assistant_tools.save_papers_batch.save_paper_to_project",
        new_callable=AsyncMock,
        side_effect=fake_save,
    ):
        result = await handle(AsyncMock(), user, {"project_id": str(project_id), "papers": papers})

    assert result["saved"] == 4
    assert result["failed"] == 0


@pytest.mark.asyncio
async def test_save_papers_batch_reports_failures_without_crashing():
    from app.services.assistant_tools.save_papers_batch import handle

    user = SimpleNamespace(id=uuid4())
    project_id = uuid4()
    papers = [{"title": "A"}, {"title": "B"}, {"title": "C"}]

    async def fake_save(db, user, project_id, req):
        if req.paper_title == "B":
            return None  # duplicate/invalid
        raise RuntimeError("boom") if req.paper_title == "C" else None

    # Make 2 succeed, 1 return None, 1 raise
    call_count = {"n": 0}

    async def maybe_save(db, user, project_id, req):
        from app.schemas.project import SavePaperResponse
        call_count["n"] += 1
        if req.paper_title == "B":
            return None
        if req.paper_title == "C":
            raise RuntimeError("boom")
        return SavePaperResponse(
            project_paper_id=uuid4(),
            paper_id=uuid4(),
            title=req.paper_title,
            status="saved",
        )

    with patch(
        "app.services.assistant_tools.save_papers_batch.save_paper_to_project",
        new_callable=AsyncMock,
        side_effect=maybe_save,
    ):
        runner = SimpleNamespace(emit=AsyncMock())
        result = await handle(
            AsyncMock(), user,
            {"project_id": str(project_id), "papers": papers},
            runner,
        )

    assert result["saved"] == 1
    assert result["failed"] == 2
    assert "B" in result["failed_titles"][0] or len(result["failed_titles"]) == 2


@pytest.mark.asyncio
async def test_project_paper_upsert_does_not_query_identifiers_concurrently():
    from app.schemas.project import SavePaperRequest
    from app.services.project import _upsert_paper

    busy = False
    db = AsyncMock()

    async def execute(_stmt):
        nonlocal busy
        if busy:
            raise AssertionError("concurrent DB use")
        busy = True
        await asyncio.sleep(0)
        busy = False
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def refresh(_paper):
        return None

    db.execute.side_effect = execute
    db.refresh.side_effect = refresh

    paper = await _upsert_paper(
        db,
        SavePaperRequest(
            paper_title="Closed timelike curves",
            paper_doi="10.1007/example",
            paper_arxiv_id="1234.5678",
            paper_semantic_scholar_id="s2-paper-id",
        ),
    )

    assert paper.title == "Closed timelike curves"
    assert db.execute.await_count == 3


# ── create_project scratch update tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_create_project_updates_scratch_project_in_place():
    """When the runner has a scratch project (title='New conversation'),
    create_project should UPDATE it instead of creating a new one.

    This is critical for preserving conversation history — without it,
    messages from before the project was created would be lost.
    """
    from app.db.models import ChatDocument, Project

    user = SimpleNamespace(id=uuid4())
    scratch_project_id = uuid4()
    scratch_doc_id = uuid4()

    # Real-like Project + ChatDocument
    from datetime import datetime
    now = datetime.now(UTC)
    project = Project(
        id=scratch_project_id,
        owner_id=user.id,
        title="New conversation",  # <-- the scratch title
        topic="",
        research_question=None,
        status="active",
        created_at=now,
        updated_at=now,
    )
    doc = ChatDocument(
        id=scratch_doc_id,
        project_id=scratch_project_id,
        user_id=user.id,
        title="New conversation",
        content_md="",
        version=0,
        created_at=now,
        updated_at=now,
    )

    db = AsyncMock()

    # db.execute returns a result whose scalars().one()/scalar_one() works
    class _ExecResult:
        def __init__(self, value):
            self._value = value
        def scalar_one(self):
            return self._value
        def scalar_one_or_none(self):
            return self._value
        def scalars(self):
            class S:
                def __init__(self, v): self._v = v
                def one(self): return self._v
                def first(self): return self._v
                def all(self): return [self._v]
            return S(self._value)

    # First execute → project lookup (is_scratch)
    # Second execute → project re-fetch for update
    # Third execute → chat_doc lookup
    # Fourth+ → dedupe checks
    exec_results = [
        _ExecResult(project),   # is_scratch
        _ExecResult(project),   # re-fetch project
        _ExecResult(doc),       # chat_doc lookup
        _ExecResult(None),      # dedupe check (no existing msg)
        _ExecResult(None),      # dedupe check (no existing msg)
    ]
    db.execute.side_effect = exec_results

    runner = SimpleNamespace(
        history=[{"role": "user", "content": "vũ trụ"}, {"role": "assistant", "content": "ok"}],
        project_id=scratch_project_id,
        document_id=scratch_doc_id,
        emit=AsyncMock(),
    )

    # Must NOT call svc_create_project (would create a new project)
    with patch(
        "app.services.assistant_tools.create_project.svc_create_project",
        new_callable=AsyncMock,
    ) as create_mock:
        result = await create_project_handle(
            db, user,
            {"title": "Time travel physics", "topic": "Theoretical physics of time travel"},
            runner,
        )

    create_mock.assert_not_called()
    assert result["project_id"] == str(scratch_project_id)
    assert result["title"] == "Time travel physics"
    # Project fields were updated
    assert project.title == "Time travel physics"
    assert project.topic == "Theoretical physics of time travel"
    assert doc.title == "Time travel physics"


@pytest.mark.asyncio
async def test_create_project_creates_new_when_no_scratch():
    """If runner.project_id is None (no scratch), create_project falls
    back to creating a brand-new project."""
    project_id = uuid4()
    document_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    db = AsyncMock()

    async def refresh(obj):
        obj.id = document_id
    db.refresh.side_effect = refresh

    runner = SimpleNamespace(
        history=[],
        project_id=None,  # No scratch
        document_id=None,
        emit=AsyncMock(),
    )

    with patch(
        "app.services.assistant_tools.create_project.svc_create_project",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(id=project_id),
    ):
        result = await create_project_handle(
            db, user,
            {"title": "Fresh project", "topic": "A new topic"},
            runner,
        )

    assert UUID(result["project_id"]) == project_id
    assert runner.project_id == project_id


# ── search_papers compact-brief tests ─────────────────────────────────────


def _make_fake_paper(idx: int, *, with_abstract: bool = True, with_pdf: bool = True):
    """Build a fake PaperResult for testing the search_papers tool."""
    from app.schemas.paper import PaperResult

    return PaperResult(
        title=f"Paper {idx}: Time Travel and Wormholes in General Relativity",
        abstract=("Long abstract about wormholes. " * 20)[:1500] if with_abstract else None,
        year=2020 + (idx % 7),
        venue="Phys Rev D",
        doi=f"10.1234/test.{idx}",
        arxiv_id=f"2604.{idx:05d}" if idx % 3 == 0 else None,
        semantic_scholar_id=f"s2_{idx}",
        url=f"https://example.com/{idx}",
        citation_count=idx * 3,
        authors=[{"name": f"Author {chr(65 + idx % 26)}", "author_id": ""}],
        fields_of_study=["Physics"],
        is_open_access=True,
        source_names=["arxiv"],
        source_specific={"exa_raw": {"nested": "x" * 500}, "pdf_url": None},
        pdf_downloaded=with_pdf,
        pdf_path=f"/tmp/paper_{idx}.pdf" if with_pdf else None,
        pdf_source="arxiv_cdn" if with_pdf else None,
    )


@pytest.mark.asyncio
async def test_search_papers_returns_compact_brief_and_full_papers():
    """search_papers must return BOTH paper_brief (LLM-visible) and
    papers (full data for save_papers_batch). The brief is what survives
    the runner's tool-summary truncation; full papers are still passed
    through so the LLM can forward them to save_papers_batch."""
    from app.schemas.paper import PaperSearchResponse
    from app.services.paper_search import SearchOutcome

    papers = [_make_fake_paper(i) for i in range(50)]
    fake_response = PaperSearchResponse(
        query="time travel",
        total_found=50,
        total_returned=50,
        search_time_ms=100.0,
        download_time_ms=200.0,
        pdfs_downloaded=25,
        pdfs_failed=25,
        papers=papers,
        detected_language="en",
        query_variants=[],
        language_bias_audit=None,
        source_diagnostics=[{"source": "arxiv", "status": "ok", "result_count": 50}],
    )
    fake_outcome = SearchOutcome(
        response=fake_response, raw_papers=[], pdf_statuses=[]
    )

    user = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    runner = SimpleNamespace(emit=AsyncMock())

    with patch.object(
        search_papers_module,
        "search_and_download",
        AsyncMock(return_value=fake_outcome),
    ):
        result = await search_papers_handle(
            db, user, {"query": "time travel", "max_results": 50}, runner
        )

    # Both views present
    assert "paper_brief" in result
    assert "papers" in result
    assert len(result["paper_brief"]) == 50
    assert len(result["papers"]) == 50

    # Briefs are COMPACT — no abstract, no source_specific blob
    sample_brief = result["paper_brief"][0]
    assert "abstract" not in sample_brief
    assert "source_specific" not in sample_brief
    assert "id" in sample_brief
    assert "title" in sample_brief
    assert "year" in sample_brief
    assert "pdf_downloaded" in sample_brief

    # Briefs include enough fields for save_papers_batch
    for needed in (
        "title", "year", "venue", "doi", "arxiv_id",
        "semantic_scholar_id", "pdf_path", "pdf_source",
    ):
        assert needed in sample_brief, f"brief missing field: {needed}"

    # Full papers preserved
    full_paper = result["papers"][0]
    assert "abstract" in full_paper
    assert "source_specific" in full_paper


@pytest.mark.asyncio
async def test_search_papers_brief_fits_in_runner_summary_budget():
    """All N paper briefs must fit inside the 16K-char tool summary
    the runner sends back to the LLM. Otherwise the LLM can't see the
    full result set and ends up saving just 1 paper per turn.
    """
    import json

    from app.schemas.paper import PaperSearchResponse
    from app.services.assistant_runner import _TOOL_RESULT_SUMMARY_CHARS
    from app.services.paper_search import SearchOutcome

    papers = [_make_fake_paper(i) for i in range(50)]
    fake_response = PaperSearchResponse(
        query="time travel", total_found=50, total_returned=50,
        search_time_ms=0, download_time_ms=0, pdfs_downloaded=25, pdfs_failed=25,
        papers=papers, detected_language="en", query_variants=[],
        language_bias_audit=None, source_diagnostics=[],
    )
    fake_outcome = SearchOutcome(response=fake_response, raw_papers=[], pdf_statuses=[])

    user = SimpleNamespace(id=uuid4())
    db = AsyncMock()
    runner = SimpleNamespace(emit=AsyncMock())

    with patch.object(
        search_papers_module,
        "search_and_download",
        AsyncMock(return_value=fake_outcome),
    ):
        result = await search_papers_handle(
            db, user, {"query": "time travel", "max_results": 50}, runner
        )

    full = json.dumps(result, default=str)
    summary = full[:_TOOL_RESULT_SUMMARY_CHARS]
    # Count how many brief items survived truncation
    visible_briefs = summary.count('"id":')
    # The LLM needs to see at least 15 papers to make a meaningful selection
    # for save_papers_batch. We previously hit ~2-3 due to a 1500-char cap.
    assert visible_briefs >= 30, (
        f"Only {visible_briefs}/50 briefs fit in "
        f"{_TOOL_RESULT_SUMMARY_CHARS}-char summary; the LLM would not "
        f"be able to see enough papers to make a multi-paper selection. "
        f"Target: ≥ 30 visible briefs (was previously 2-3 due to 1500-char cap)."
    )
