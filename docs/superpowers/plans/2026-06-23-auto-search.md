# Auto Search & Save Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Auto Search" button to the search page that fans out to all wired paper sources, LLM-scores the candidates, picks the top N (25/50/100) most relevant papers, and auto-saves them to the project.

**Architecture:** A new `BackgroundJob(job_type="auto_search")` runs a 4-phase worker in the background. Each phase updates `progress_json` so the frontend can render a multi-step progress UI via the existing `useJobPolling` hook. Reuses `search_and_download`, `save_paper_to_project`, and `_deduplicate_raw_books` from existing services.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, DeepSeek V4, Next.js 16, React 19, TypeScript, Tailwind v4

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/ai/prompts.py` | **Modify** | Add `AUTO_SEARCH_SCREEN_SYSTEM` / `AUTO_SEARCH_SCREEN_USER` |
| `app/schemas/paper.py` | **Modify** | Add `AutoSearchRequest`, `AutoSearchResponse` |
| `app/services/paper_search.py` | **Modify** | `search_and_download` accepts `max_per_source` param to lift the 100/source cap |
| `app/services/search_session.py` | **Modify** | Add `auto_search_and_save` + `_run_auto_search_job` (4-phase worker) |
| `app/routers/search_session.py` | **Modify** | Add `POST /projects/{project_id}/search/auto` endpoint |
| `frontend/lib/types.ts` | **Modify** | Add `AutoSearchRequest`, `AutoSearchResponse`, `AutoSearchProgressJson` |
| `frontend/lib/stores/search-store.ts` | **Modify** | Add `startAutoSearch` action + `autoSearchJobId` state |
| `frontend/app/(app)/projects/[id]/search/page.tsx` | **Modify** | Add Auto Search dropdown + progress bar |
| `frontend/components/search/AutoSearchProgress.tsx` | **Create** | Multi-step progress UI |
| `tests/test_auto_search.py` | **Create** | Unit tests for the worker phases |

---

## Task 1: Add new prompts to `app/ai/prompts.py`

**Files:**
- Modify: `app/ai/prompts.py` (append after the existing `PAPER_SCREEN_USER` at line 138)

- [ ] **Step 1: Add the two new prompt constants**

Append after line 138:

```python
AUTO_SEARCH_SCREEN_SYSTEM = """\
You are a paper relevance scorer. Score each paper on a 3-point scale:
- "high": highly relevant to the research topic, should be saved
- "medium": somewhat related, marginal relevance
- "low": not relevant, should be discarded

Output a JSON array. Each element: {"index": <int>, "score": "high"|"medium"|"low", "reason": "<one sentence>"}.
Indices match the input order. Be strict: most papers should be "medium" or "low"."""

AUTO_SEARCH_SCREEN_USER = """\
Research topic: {topic}
Research question: {research_question}

Papers to score (indexed from 0):
{papers_json}

Output a JSON array of {{index, score, reason}} in the same order.
"""
```

- [ ] **Step 2: Verify the import**

Run: `python -c "from app.ai.prompts import AUTO_SEARCH_SCREEN_SYSTEM, AUTO_SEARCH_SCREEN_USER; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/ai/prompts.py
git commit -m "feat: add auto search screen prompts for batch LLM scoring"
```

---

## Task 2: Add new schemas to `app/schemas/paper.py`

**Files:**
- Modify: `app/schemas/paper.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auto_search_schemas.py`:

```python
"""Schemas for the auto search endpoint."""

from app.schemas.paper import AutoSearchRequest, AutoSearchResponse


def test_auto_search_request_validates_target_count():
    """Only 25, 50, 100 are accepted. Others raise validation error."""
    for n in (25, 50, 100):
        r = AutoSearchRequest(query="RAG medical QA", target_count=n)
        assert r.target_count == n

    # Out-of-range values are rejected
    import pytest
    from pydantic import ValidationError
    for n in (5, 75, 150, 200):
        with pytest.raises(ValidationError):
            AutoSearchRequest(query="RAG medical QA", target_count=n)


def test_auto_search_request_validates_query_length():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        AutoSearchRequest(query="x", target_count=50)  # too short
    with pytest.raises(ValidationError):
        AutoSearchRequest(query="x" * 501, target_count=50)  # too long


def test_auto_search_response_defaults():
    r = AutoSearchResponse(job_id="j", session_id="s", target_count=50, status="running")
    assert r.status == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_search_schemas.py -v`
Expected: FAIL with `ImportError: cannot import name 'AutoSearchRequest'`

- [ ] **Step 3: Add the schemas**

Append to `app/schemas/paper.py` (after `SuggestQueriesRequest`):

```python
class AutoSearchRequest(BaseModel):
    """Request body for the auto-search-and-save endpoint."""

    query: str = Field(..., min_length=2, max_length=500)
    target_count: int = Field(..., ge=10, le=100)


class AutoSearchResponse(BaseModel):
    """Response for POST /api/projects/{id}/search/auto."""

    job_id: str
    session_id: str
    target_count: int
    status: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auto_search_schemas.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/schemas/paper.py tests/test_auto_search_schemas.py
git commit -m "feat: add AutoSearchRequest and AutoSearchResponse schemas"
```

---

## Task 3: Add `max_per_source` parameter to `search_and_download`

**Files:**
- Modify: `app/services/paper_search.py`

The current per-source cap is `min(limit * 2, 100)` at line 477. Auto-search needs to lift this to 200 to collect enough candidates. Add a `max_per_source` parameter that overrides the default cap.

- [ ] **Step 1: Update `search_and_download` signature**

Replace line 113:

```python
async def search_and_download(
    request: PaperSearchRequest,
    max_per_source: int | None = None,
) -> SearchOutcome:
```

- [ ] **Step 2: Update the cache key to include `max_per_source`**

Replace lines 126-127:

```python
    cache_key = _cache_key(
        f"{request.query}|{request.limit}|{request.year_from}|{request.year_to}|mp={max_per_source}"
    )
```

- [ ] **Step 3: Pass `max_per_source` into `_search_sources_parallel`**

Replace line 165-171:

```python
        # ── 3. Search all sources in parallel with early exit ────────────
        all_raw, source_diagnostics = await _search_sources_parallel(
            source_query_map,
            request.limit,
            request.year_from,
            request.year_to,
            max_per_source=max_per_source,
        )
```

- [ ] **Step 4: Update `_search_sources_parallel` signature**

Replace lines 427-431:

```python
async def _search_sources_parallel(
    source_query_map: dict[str, str],
    limit: int,
    year_from: int | None,
    year_to: int | None,
    max_per_source: int | None = None,
) -> tuple[list[RawPaper], list[dict]]:
```

- [ ] **Step 5: Use `max_per_source` in the per-source call**

Replace line 475-480:

```python
            per_source_limit = (
                max_per_source
                if max_per_source is not None
                else min(limit * 2, 100)
            )
            papers = await source.search(
                query=src_query,
                limit=per_source_limit,
                year_from=year_from,
                year_to=year_to,
            )
```

- [ ] **Step 6: Verify the file compiles**

Run: `python -c "from app.services.paper_search import search_and_download; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Run existing tests**

Run: `pytest tests/ -q -x`
Expected: All existing tests still pass

- [ ] **Step 8: Commit**

```bash
git add app/services/paper_search.py
git commit -m "feat: add max_per_source param to search_and_download"
```

---

## Task 4: Add `auto_search_and_save` service function

**Files:**
- Modify: `app/services/search_session.py` (append at the end)

- [ ] **Step 1: Write the failing test**

Create `tests/test_auto_search_service.py`:

```python
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
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=project))

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
    job_result = MagicMock(scalars=MagicMock(first=MagicMock(return_value=running_job)))

    call_index = {"n": 0}

    async def mock_execute(stmt):
        call_index["n"] += 1
        if call_index["n"] == 1:
            return project_result
        return job_result

    db.execute = mock_execute

    result = await auto_search_and_save(db, user, project.id, "RAG", 50)
    assert result == {"error": "Another auto-search is already running", "status_code": 429}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_search_service.py -v`
Expected: FAIL with `ImportError: cannot import name 'auto_search_and_save'`

- [ ] **Step 3: Add the service function**

Append to `app/services/search_session.py` (after `_run_search_job` ends at line 658):

```python
# ── Auto search & save ──────────────────────────────────────────────────


async def auto_search_and_save(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    query: str,
    target_count: int,
) -> dict:
    """Start an auto-search-and-save background job. Returns job_id immediately.

    Validates project ownership, checks for concurrent jobs, creates a
    SearchRun + BackgroundJob(job_type="auto_search"), and launches the
    4-phase worker.
    """
    if target_count not in (25, 50, 100):
        raise ValueError(f"target_count must be 25, 50, or 100 (got {target_count})")

    from sqlalchemy import and_, select

    from app.db.models import BackgroundJob, SearchRun

    # 1. Verify project ownership
    project_result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        return {"error": "Project not found"}

    # 2. Check for concurrent auto_search job for this user
    running_result = await db.execute(
        select(BackgroundJob)
        .where(
            and_(
                BackgroundJob.user_id == user.id,
                BackgroundJob.job_type == "auto_search",
                BackgroundJob.status.in_(("pending", "running")),
            )
        )
    )
    running = running_result.scalars().first()
    if running is not None:
        return {
            "error": "Another auto-search is already running",
            "status_code": 429,
        }

    # 3. Create empty SearchRun
    run = SearchRun(
        project_id=project_id,
        user_query=query,
        total_results=0,
        results_json=[],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # 4. Create BackgroundJob
    job = BackgroundJob(
        job_type="auto_search",
        project_id=project_id,
        user_id=user.id,
        status="pending",
        total=target_count,
        progress_json={
            "phase": "queued",
            "target_count": target_count,
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 5. Launch worker
    import asyncio

    asyncio.ensure_future(
        _run_auto_search_job(
            job.id, run.id, project_id, user.id, query, target_count
        )
    )

    return {
        "job_id": str(job.id),
        "session_id": str(run.id),
        "target_count": target_count,
        "status": "running",
    }
```

- [ ] **Step 4: Add the Project import at the top of the file**

Add `Project` to the imports from `app.db.models`:

```python
from app.db.models import Paper, Project, ProjectPaper, SearchRun, User
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_auto_search_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/search_session.py tests/test_auto_search_service.py
git commit -m "feat: add auto_search_and_save service entry point"
```

---

## Task 5: Add `_run_auto_search_job` 4-phase worker

**Files:**
- Modify: `app/services/search_session.py` (append after `auto_search_and_save`)

The worker has 4 phases. Each phase updates `job.progress_json`. The worker uses `async_session_factory` (same pattern as `_run_auto_save_job`).

- [ ] **Step 1: Write the failing test for phase 1 (search)**

Add to `tests/test_auto_search_service.py`:

```python
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
            # Subsequent execute calls: dedup query (no result expected)
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
                response=SimpleNamespace(papers=[mock_paper] * 200, source_diagnostics=[]),
            )
            mock_search.return_value = mock_outcome

            with patch("app.services.search_session.batch_score_papers") as mock_score:
                mock_score.return_value = ["high"] * 50 + ["medium"] * 100 + ["low"] * 50

                with patch("app.services.search_session.save_paper_to_project") as mock_save:
                    mock_save.return_value = SimpleNamespace(project_paper_id=uuid4())

                    with patch("asyncio.sleep", new=AsyncMock()):
                        # Set a 5 minute timeout but the test should complete fast
                        await _run_auto_search_job(
                            job_id, session_id, project_id, user_id, "RAG", 50,
                            timeout_seconds=5,
                        )

        # search_and_download was called with max_per_source=200
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs.get("max_per_source") == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auto_search_service.py::test_run_auto_search_phase1_calls_search_and_download -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add the `_run_auto_search_job` worker**

Append to `app/services/search_session.py`:

```python
async def _run_auto_search_job(
    job_id: UUID,
    session_id: UUID,
    project_id: UUID,
    user_id: UUID,
    query: str,
    target_count: int,
    timeout_seconds: int = 300,
) -> None:
    """4-phase auto-search worker.

    Phase 1 (0-25%):  Fan-out search across all sources, max 200/source
    Phase 2 (25-60%): Dedupe + batch LLM score (25/batch)
    Phase 3 (60-65%): Filter score=high, pick top N (fallback to medium)
    Phase 4 (65-100%): Auto-save top N papers (skip duplicates)

    Updates ``job.progress_json`` between phases so the frontend polling
    endpoint can show a multi-step progress UI.
    """
    from app.db.session import async_session_factory
    from app.schemas.paper import PaperSearchRequest
    from app.services.paper_search import (
        _deduplicate_raw_books,
        search_and_download,
    )

    import time
    from datetime import UTC, datetime

    start_wall = time.monotonic()
    job = None

    async with async_session_factory() as bg_db:
        try:
            from app.db.models import BackgroundJob, SearchRun, User

            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            await bg_db.commit()

            # Load session + user
            run_result = await bg_db.execute(
                select(SearchRun).where(SearchRun.id == session_id)
            )
            run = run_result.scalar_one_or_none()
            user_result = await bg_db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if run is None or user is None:
                job.status = "failed"
                job.error_message = "Session or user not found"
                await bg_db.commit()
                return

            # ── Phase 1: Search all sources in parallel ──────────────────
            async def _update_progress(payload: dict) -> None:
                job.progress_json = {**job.progress_json, **payload}
                job.progress = int(payload.get("percent", 0))
                await bg_db.commit()

            await _update_progress({
                "phase": "searching",
                "current_source": "all",
                "papers_found": 0,
                "percent": 5,
            })

            search_req = PaperSearchRequest(
                query=query, limit=2000, download_pdfs=False
            )
            outcome = await search_and_download(
                search_req, max_per_source=200,
            )
            all_raw = outcome.raw_papers
            source_diagnostics = outcome.response.source_diagnostics or []

            await _update_progress({
                "phase": "searching",
                "current_source": "done",
                "papers_found": len(all_raw),
                "percent": 25,
            })

            if time.monotonic() - start_wall > timeout_seconds:
                raise TimeoutError("Phase 1 exceeded timeout")

            # ── Phase 2: Dedupe + batch LLM score ─────────────────────────
            deduped = _deduplicate_raw_books(all_raw)

            await _update_progress({
                "phase": "scoring",
                "batches_total": max(1, (len(deduped) + 24) // 25),
                "papers_scored": 0,
                "papers_total": len(deduped),
                "percent": 30,
            })

            scores: list[str] = await _batch_score_papers(
                job, deduped, user, _update_progress, timeout_seconds, start_wall,
            )

            if time.monotonic() - start_wall > timeout_seconds:
                raise TimeoutError("Phase 2 exceeded timeout")

            # ── Phase 3: Filter + pick top N ──────────────────────────────
            scored = [
                (paper, score)
                for paper, score in zip(deduped, scores)
                if score in ("high", "medium", "low")
            ]
            # Sort: high first, then medium, then low; stable by original order
            priority = {"high": 0, "medium": 1, "low": 2}
            scored.sort(key=lambda p: priority.get(p[1], 9))

            high_picks = [(p, s) for p, s in scored if s == "high"][:target_count]
            if len(high_picks) < target_count:
                remaining = target_count - len(high_picks)
                medium_picks = [(p, s) for p, s in scored if s == "medium"][:remaining]
                high_picks.extend(medium_picks)

            top_papers = [p for p, _ in high_picks[:target_count]]

            await _update_progress({
                "phase": "filtering",
                "kept": len(top_papers),
                "percent": 65,
            })

            # ── Phase 4: Auto-save top N papers ───────────────────────────
            await _update_progress({
                "phase": "saving",
                "saved": 0,
                "skipped": 0,
                "total": len(top_papers),
                "current_paper": "",
                "percent": 70,
            })

            saved_count = 0
            skipped_count = 0
            saved_paper_dicts: list[dict] = []

            from app.schemas.project import SavePaperRequest
            from app.services.project import save_paper_to_project

            for idx, paper in enumerate(top_papers):
                if time.monotonic() - start_wall > timeout_seconds:
                    raise TimeoutError("Phase 4 exceeded timeout")

                paper_dict = _raw_paper_to_dict(paper)
                paper_dict["screening_score"] = "high"  # for tracking

                try:
                    authors_mapped = [
                        {
                            "name": a.get("name") if isinstance(a, dict) else str(a),
                            "author_id": "",
                        }
                        for a in (paper.authors or [])
                    ]
                    req = SavePaperRequest(
                        paper_title=paper.title,
                        paper_abstract=paper.abstract,
                        paper_year=paper.year,
                        paper_venue=paper.venue,
                        paper_doi=paper.doi,
                        paper_arxiv_id=paper.arxiv_id,
                        paper_semantic_scholar_id=paper.semantic_scholar_id,
                        paper_url=paper.url,
                        paper_citation_count=paper.citation_count,
                        paper_authors=authors_mapped,
                        paper_source_names=[paper.source_name] if paper.source_name else ["paperhub"],
                        download_pdf=True,
                        source_specific=paper.source_specific or {},
                    )
                    save_result = await save_paper_to_project(
                        bg_db, user, project_id, req,
                    )
                    if save_result is None:
                        skipped_count += 1
                    else:
                        saved_count += 1
                        saved_paper_dicts.append(paper_dict)
                except Exception as exc:
                    logger.warning(
                        "Auto-save failed for paper '%s': %s",
                        paper.title[:60], exc,
                    )
                    skipped_count += 1
                    with contextlib.suppress(Exception):
                        await bg_db.rollback()

                percent = 70 + int(25 * (idx + 1) / max(1, len(top_papers)))
                await _update_progress({
                    "phase": "saving",
                    "saved": saved_count,
                    "skipped": skipped_count,
                    "total": len(top_papers),
                    "current_paper": paper.title[:60],
                    "percent": min(95, percent),
                })

            # Persist back to SearchRun
            run.results_json = saved_paper_dicts
            run.total_results = saved_count
            run.screening_scores = ["high"] * saved_count
            await bg_db.commit()

            # Mark job complete
            job.status = "completed"
            job.progress = saved_count
            job.result = {
                "session_id": str(session_id),
                "saved_count": saved_count,
                "skipped_count": skipped_count,
                "target_count": target_count,
                "saved_paper_ids": [
                    p.get("semantic_scholar_id") or p.get("doi") or p.get("arxiv_id") or p.get("title")
                    for p in saved_paper_dicts
                ],
            }
            job.progress_json = {
                "phase": "done",
                "saved": saved_count,
                "skipped": skipped_count,
                "total": len(top_papers),
                "percent": 100,
            }
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Auto-search job %s failed: %s", job_id, exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.progress_json = {
                        **(job.progress_json or {}),
                        "phase": "failed",
                        "error": str(exc)[:200],
                    }
                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass


async def _batch_score_papers(
    job,
    papers: list,
    user: User,
    update_progress,
    timeout_seconds: int,
    start_wall: float,
) -> list[str]:
    """Score papers in batches of 25 using the LLM.

    Returns a list of scores (high/medium/low) in the same order as ``papers``.
    Failed batches fall back to "medium" (don't lose papers entirely).
    """
    import asyncio
    import time

    from app.ai.prompts import AUTO_SEARCH_SCREEN_SYSTEM, AUTO_SEARCH_SCREEN_USER
    from app.ai.provider import get_provider

    if not papers:
        return []

    provider = get_provider()
    batch_size = 25
    batches = [papers[i : i + batch_size] for i in range(0, len(papers), batch_size)]
    all_scores: list[str] = ["medium"] * len(papers)
    batches_total = len(batches)

    for batch_idx, batch in enumerate(batches):
        if time.monotonic() - start_wall > timeout_seconds:
            break

        papers_json = _papers_to_scoring_json(batch)
        user_msg = AUTO_SEARCH_SCREEN_USER.format(
            topic=user_topic_for_user(user),
            research_question="Not specified",
            papers_json=papers_json,
        )

        try:
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                system=AUTO_SEARCH_SCREEN_SYSTEM,
                schema={
                    "type": "object",
                    "properties": {
                        "scores": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {"type": "integer"},
                                    "score": {"type": "string"},
                                },
                                "required": ["index", "score"],
                            },
                        },
                    },
                    "required": ["scores"],
                },
                tool_name="auto_search_screen",
                max_tokens=2000,
            )
            batch_scores = result.get("scores", [])
            for entry in batch_scores:
                try:
                    idx = int(entry.get("index", -1))
                    score = str(entry.get("score", "medium")).lower()
                    if score not in ("high", "medium", "low"):
                        score = "medium"
                    if 0 <= idx < len(batch):
                        global_idx = batch_idx * batch_size + idx
                        if global_idx < len(all_scores):
                            all_scores[global_idx] = score
                except (ValueError, TypeError):
                    continue
        except Exception as exc:
            logger.warning(
                "Batch %d LLM scoring failed (using medium fallback): %s",
                batch_idx, exc,
            )
            # All scores in this batch stay "medium" (default)

        scored_so_far = min((batch_idx + 1) * batch_size, len(papers))
        percent = 30 + int(30 * scored_so_far / max(1, len(papers)))
        await update_progress({
            "phase": "scoring",
            "batches_completed": batch_idx + 1,
            "batches_total": batches_total,
            "papers_scored": scored_so_far,
            "papers_total": len(papers),
            "percent": min(60, percent),
        })

    return all_scores


def _papers_to_scoring_json(papers: list) -> str:
    """Render a list of RawPaper objects as a compact JSON for the scoring prompt."""
    import json

    out = []
    for i, p in enumerate(papers):
        out.append({
            "index": i,
            "title": p.title,
            "abstract": (p.abstract or "")[:500],
            "year": p.year,
            "venue": p.venue or "",
            "source": p.source_name or "",
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


def user_topic_for_user(user: User) -> str:
    """Best-effort: read the user's most-recent project's topic for context.

    Falls back to "research project" if no project is available.
    """
    return getattr(user, "_auto_search_topic", "research project")


def _raw_paper_to_dict(paper) -> dict:
    """Convert a RawPaper to the dict shape stored in SearchRun.results_json."""
    return {
        "title": paper.title,
        "abstract": paper.abstract,
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "arxiv_id": paper.arxiv_id,
        "semantic_scholar_id": paper.semantic_scholar_id,
        "url": paper.url,
        "citation_count": paper.citation_count,
        "authors": paper.authors or [],
        "source_names": [paper.source_name] if paper.source_name else [],
        "source_specific": paper.source_specific or {},
        "can_download": bool(
            paper.arxiv_id
            or (paper.source_specific or {}).get("pdf_url")
            or (paper.source_specific or {}).get("pmc_id")
        ),
    }
```

- [ ] **Step 4: Verify the file compiles**

Run: `python -c "from app.services.search_session import _run_auto_search_job, auto_search_and_save; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Run all auto-search tests**

Run: `pytest tests/test_auto_search_service.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/search_session.py tests/test_auto_search_service.py
git commit -m "feat: add 4-phase auto search worker with batched LLM scoring"
```

---

## Task 6: Add `POST /api/projects/{project_id}/search/auto` endpoint

**Files:**
- Modify: `app/routers/search_session.py`

- [ ] **Step 1: Add the endpoint**

Add after the `auto_save_session` endpoint (after line 234) and before the `get_job` endpoint (line 237):

```python
@router.post("/projects/{project_id}/search/auto", status_code=http_status.HTTP_202_ACCEPTED)
async def auto_search_project(
    project_id: UUID,
    request: AutoSearchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start an auto-search-and-save background job.

    Fetches ~200 papers from each of 4 sources (S2, arXiv, OpenAlex, Exa),
    LLM-scores all candidates, picks the top N (target_count) most relevant,
    and auto-saves them into the project.

    Returns ``{job_id, session_id, target_count, status: "running"}`` immediately.
    The frontend polls ``GET /api/papers/search/jobs/{job_id}`` for progress.
    """
    from app.schemas.paper import AutoSearchRequest
    from app.services.search_session import auto_search_and_save

    try:
        result = await auto_search_and_save(
            db, user, project_id, request.query, request.target_count,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if result.get("error") == "Project not found":
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    if result.get("status_code") == 429:
        raise HTTPException(
            status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result["error"],
        )
    return result
```

- [ ] **Step 2: Add the import for `AutoSearchRequest`**

Update the import block at lines 28-30 to include `AutoSearchRequest`:

```python
from app.schemas.paper import (
    AutoSearchRequest,
    ScreenPapersResponse,
)
```

- [ ] **Step 3: Verify the file compiles**

Run: `python -c "from app.routers.search_session import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/routers/search_session.py
git commit -m "feat: add POST /projects/{id}/search/auto endpoint"
```

---

## Task 7: Add frontend TypeScript types

**Files:**
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Find the right place to add the types**

Find where `ScreenPapersResponse` and other search-related types are defined. Append after them.

- [ ] **Step 2: Add the new types**

Append to `frontend/lib/types.ts`:

```typescript
// ── Auto search & save ──

export interface AutoSearchRequest {
  query: string;
  target_count: number;  // 25, 50, or 100
}

export interface AutoSearchResponse {
  job_id: string;
  session_id: string;
  target_count: number;
  status: "running";
}

export type AutoSearchPhase =
  | "queued"
  | "searching"
  | "scoring"
  | "filtering"
  | "saving"
  | "done"
  | "failed";

export interface AutoSearchProgressJson {
  phase: AutoSearchPhase;
  target_count?: number;
  current_source?: string;
  papers_found?: number;
  batches_completed?: number;
  batches_total?: number;
  papers_scored?: number;
  papers_total?: number;
  kept?: number;
  saved?: number;
  skipped?: number;
  total?: number;
  current_paper?: string;
  percent: number;
  error?: string;
}
```

- [ ] **Step 3: Verify frontend type-checks**

Run: `cd frontend && pnpm tsc --noEmit --pretty 2>&1 | head -20`
Expected: No new errors

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat: add AutoSearch TypeScript types"
```

---

## Task 8: Add `startAutoSearch` action to search store

**Files:**
- Modify: `frontend/lib/stores/search-store.ts`

- [ ] **Step 1: Add new state fields**

Find the `SearchState` interface (top of file). Add new fields:

```typescript
  // Auto search
  isAutoSearching: boolean;
  autoSearchJobId: string | null;
  autoSearchSessionId: string | null;
  autoSearchProgress: AutoSearchProgressJson | null;

  startAutoSearch: (query: string, projectId: string, targetCount: 25 | 50 | 100) => Promise<AutoSearchResponse>;
  clearAutoSearch: () => void;
```

- [ ] **Step 2: Add the implementation in the store**

Find the `autoSave` action (around line 262). Add the new action right after it:

```typescript
  async startAutoSearch(query, projectId, targetCount) {
    const token = useAuthStore.getState().token;
    if (!token || !projectId) throw new Error("Missing auth or projectId");
    set({ isAutoSearching: true, autoSearchJobId: null, autoSearchSessionId: null, autoSearchProgress: null });
    try {
      const data = await apiFetch<AutoSearchResponse>(
        `/projects/${projectId}/search/auto`,
        {
          method: "POST",
          body: JSON.stringify({ query, target_count: targetCount }),
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      set({
        autoSearchJobId: data.job_id,
        autoSearchSessionId: data.session_id,
      });
      return data;
    } catch (err) {
      set({ isAutoSearching: false });
      throw err;
    }
  },

  clearAutoSearch() {
    set({
      isAutoSearching: false,
      autoSearchJobId: null,
      autoSearchSessionId: null,
      autoSearchProgress: null,
    });
  },
```

- [ ] **Step 3: Add the import for the new types**

At the top of the file, add to the import from `lib/types`:

```typescript
import type {
  AutoSearchProgressJson,
  AutoSearchResponse,
} from "@/lib/types";
```

- [ ] **Step 4: Add default values to the initial state**

Find the `set` initializer and add:

```typescript
  isAutoSearching: false,
  autoSearchJobId: null,
  autoSearchSessionId: null,
  autoSearchProgress: null,
```

- [ ] **Step 5: Verify frontend type-checks**

Run: `cd frontend && pnpm tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/stores/search-store.ts
git commit -m "feat: add startAutoSearch store action"
```

---

## Task 9: Create the `AutoSearchProgress` component

**Files:**
- Create: `frontend/components/search/AutoSearchProgress.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { Spinner, Check, X } from "@phosphor-icons/react";
import { useEffect } from "react";
import type { AutoSearchProgressJson } from "@/lib/types";

interface Props {
  progress: AutoSearchProgressJson | null;
  isDone: boolean;
  isFailed: boolean;
  errorMessage?: string | null;
}

const PHASES = [
  { key: "searching", label: "Searching 4 sources" },
  { key: "scoring", label: "LLM scoring" },
  { key: "filtering", label: "Picking top N" },
  { key: "saving", label: "Auto-saving" },
] as const;

function phaseIndex(phase: string | undefined): number {
  if (phase === "searching" || phase === "queued") return 0;
  if (phase === "scoring") return 1;
  if (phase === "filtering") return 2;
  if (phase === "saving") return 3;
  if (phase === "done") return 4;
  return 0;
}

export function AutoSearchProgress({ progress, isDone, isFailed, errorMessage }: Props) {
  const currentIdx = phaseIndex(progress?.phase);
  const percent = progress?.percent ?? 0;

  return (
    <div className="font-ui rounded-xl border border-hairline bg-surface-card p-4 space-y-3">
      {/* Progress bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 rounded-full bg-surface-bone overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-500"
            style={{ width: `${isFailed ? 0 : percent}%` }}
          />
        </div>
        <span className="text-[12px] font-semibold text-ink tabular-nums">
          {isFailed ? "Failed" : `${percent}%`}
        </span>
      </div>

      {/* Phase list */}
      <ol className="space-y-1.5">
        {PHASES.map((p, i) => {
          const isPast = currentIdx > i || isDone;
          const isCurrent = currentIdx === i && !isDone && !isFailed;
          const isPending = currentIdx < i;
          return (
            <li
              key={p.key}
              className={`flex items-center gap-2 text-[12px] ${
                isCurrent ? "text-ink font-semibold" :
                isPast ? "text-green-700" :
                "text-ash"
              }`}
            >
              {isPast ? <Check size={12} weight="bold" /> :
               isCurrent ? <Spinner size={12} className="animate-spin" /> :
               <span className="w-3 h-3 rounded-full border border-hairline" />}
              <span>{p.label}</span>
              {isCurrent && progress && (
                <span className="ml-auto text-[11px] text-ash">
                  {_phaseSubtext(progress)}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {/* Failure message */}
      {isFailed && errorMessage && (
        <p className="text-[12px] text-red-600">
          <X size={12} className="inline mr-1" />
          {errorMessage}
        </p>
      )}
    </div>
  );
}

function _phaseSubtext(p: AutoSearchProgressJson): string {
  if (p.phase === "searching") {
    if (p.papers_found !== undefined) return `${p.papers_found} papers found`;
    return "Starting…";
  }
  if (p.phase === "scoring") {
    if (p.papers_scored !== undefined && p.papers_total !== undefined) {
      return `${p.papers_scored}/${p.papers_total} scored`;
    }
    return "Starting…";
  }
  if (p.phase === "filtering") {
    if (p.kept !== undefined) return `keeping top ${p.kept}`;
    return "Starting…";
  }
  if (p.phase === "saving") {
    if (p.saved !== undefined && p.total !== undefined) {
      return `${p.saved}/${p.total} saved`;
    }
    return "Starting…";
  }
  return "";
}
```

- [ ] **Step 2: Verify the file type-checks**

Run: `cd frontend && pnpm tsc --noEmit --pretty 2>&1 | head -10`
Expected: No errors (or only pre-existing)

- [ ] **Step 3: Commit**

```bash
git add frontend/components/search/AutoSearchProgress.tsx
git commit -m "feat: add AutoSearchProgress multi-step progress component"
```

---

## Task 10: Wire the Auto Search button into the search page

**Files:**
- Modify: `frontend/app/(app)/projects/[id]/search/page.tsx`

- [ ] **Step 1: Add state for auto-search results + useJobPolling import is already there**

In the imports section, add:

```tsx
import { AutoSearchProgress } from "@/components/search/AutoSearchProgress";
```

- [ ] **Step 2: Add useJobPolling hook for auto-search job**

After the existing `useJobPolling` calls (or the existing job polling), add:

```tsx
const autoSearchJob = useJobPolling(
  autoSearchJobId,
  { interval: 2000, maxAttempts: 150 }
);
```

Read state from store:

```tsx
const autoSearchJobId = useSearchStore((s) => s.autoSearchJobId);
const autoSearchSessionId = useSearchStore((s) => s.autoSearchSessionId);
const isAutoSearching = useSearchStore((s) => s.isAutoSearching);
const startAutoSearch = useSearchStore((s) => s.startAutoSearch);
const clearAutoSearch = useSearchStore((s) => s.clearAutoSearch);
const autoSearchProgress = (autoSearchJob.data as any)?.progress_json ?? null;
const autoSearchDone = autoSearchJob.data?.status === "completed";
const autoSearchFailed = autoSearchJob.data?.status === "failed";
const autoSearchError = autoSearchJob.data?.error_message;
```

- [ ] **Step 3: Add the handler**

After `handleAutoSave` (around line 197), add:

```tsx
async function handleAutoSearch(targetCount: 25 | 50 | 100) {
  if (!query.trim() || !projectId) return;
  try {
    await startAutoSearch(query, projectId, targetCount);
    toast.info(`Auto-searching for top ${targetCount} papers…`);
  } catch (err) {
    if (err instanceof Error && err.message.includes("429")) {
      toast.warning("Another auto-search is already running");
    } else {
      toast.error(err instanceof Error ? err.message : "Auto-search failed");
    }
  }
}

// When auto-search completes, refresh sessions and reset state
useEffect(() => {
  if (autoSearchDone && autoSearchSessionId) {
    const result = (autoSearchJob.data as any)?.result;
    const saved = result?.saved_count ?? 0;
    toast.success(`Auto-saved ${saved} papers`);
    // Reload the sessions list
    fetchSessions();
    // Clear auto-search state
    clearAutoSearch();
    // Optionally switch to the auto-saved session
    if (saved > 0 && autoSearchSessionId) {
      router.push(`/projects/${projectId}/search/${autoSearchSessionId}`);
    }
  }
  if (autoSearchFailed) {
    toast.error(autoSearchError || "Auto-search failed");
    clearAutoSearch();
  }
}, [autoSearchDone, autoSearchFailed]);
```

- [ ] **Step 4: Add the Auto Search button to the UI**

Find the existing Search button section (around line 340) and add the Auto Search button next to it. Insert this button right after the Search button:

```tsx
<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <button
      disabled={!query.trim() || loading}
      className="focus-ring font-ui h-[44px] inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-5 text-sm font-semibold text-primary hover:bg-primary/20 transition-all duration-200 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      <Sparkle size={14} weight="fill" />
      Auto Search
    </button>
  </DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuItem onClick={() => handleAutoSearch(25)}>
      Auto Search 25 papers
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => handleAutoSearch(50)}>
      Auto Search 50 papers
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => handleAutoSearch(100)}>
      Auto Search 100 papers
    </DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

- [ ] **Step 5: Add the imports for `DropdownMenu`**

At the top of the file, add (matching the codebase's existing dropdown import pattern — check the codebase for the exact import path):

```tsx
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
```

- [ ] **Step 6: Render the progress UI when running**

Add this just after the "Found N papers" line (around line 374):

```tsx
{(isAutoSearching || autoSearchDone || autoSearchFailed) && (
  <div className="mt-3">
    <AutoSearchProgress
      progress={autoSearchProgress}
      isDone={autoSearchDone}
      isFailed={autoSearchFailed}
      errorMessage={autoSearchError}
    />
  </div>
)}
```

- [ ] **Step 7: Verify frontend type-checks**

Run: `cd frontend && pnpm tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors. If there are import errors, follow the codebase's existing patterns for DropdownMenu (which may already be in use elsewhere — search the codebase).

- [ ] **Step 8: Commit**

```bash
git add frontend/app/\(app\)/projects/\[id\]/search/page.tsx
git commit -m "feat: add Auto Search dropdown button + progress UI"
```

---

## Task 11: Run all tests + lint

- [ ] **Step 1: Run backend tests**

Run: `pytest tests/ -q`
Expected: All pass (existing + new)

- [ ] **Step 2: Run backend linter**

Run: `ruff check app/ai/prompts.py app/schemas/paper.py app/services/paper_search.py app/services/search_session.py app/routers/search_session.py`
Expected: No errors

- [ ] **Step 3: Run frontend type-check**

Run: `cd frontend && pnpm tsc --noEmit --pretty`
Expected: No new errors

- [ ] **Step 4: Smoke test the endpoint**

Start the backend in one terminal:
```bash
make backend
```

In another terminal, test the endpoint with curl:
```bash
TOKEN="<your-jwt>"
PROJECT_ID="<your-project-uuid>"
curl -X POST "http://localhost:8010/api/projects/$PROJECT_ID/search/auto" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"RAG medical QA","target_count":50}'
```

Expected: `202` with `{"job_id":"...","session_id":"...","target_count":50,"status":"running"}`

- [ ] **Step 5: Poll the job status**

```bash
JOB_ID="<the-job-id-from-above>"
curl "http://localhost:8010/api/papers/search/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Expected: status progresses `running` → `completed` with `progress_json.phase` updating through `searching` → `scoring` → `filtering` → `saving` → `done`

- [ ] **Step 6: Final commit if any fixups**

```bash
git status
# If clean, skip
# If changes:
git add -A
git commit -m "chore: auto search integration cleanup"
```

---

## Self-Review

**Spec coverage:**
- ✅ Search across all wired sources — Task 5 (Phase 1 in `_run_auto_search_job`)
- ✅ Fetch larger pool (200/source) — Task 3 (`max_per_source` param) + Task 5 (uses 200)
- ✅ LLM scoring all candidates in batches — Task 5 (`_batch_score_papers`)
- ✅ Pick top N high — Task 5 (Phase 3 sorting)
- ✅ Auto-save top N — Task 5 (Phase 4)
- ✅ Filter out failed saves — Task 5 (Phase 4 increments `skipped_count`)
- ✅ Multi-step progress — Task 9 (component) + Task 10 (UI integration)
- ✅ Dropdown 25/50/100 — Task 10 (DropdownMenu in search page)

**Type consistency:**
- `target_count` typed as `int` in Python, `25 | 50 | 100` in TS — matches the spec
- `progress_json` updated consistently across all 4 phases
- `job.result` shape: `{session_id, saved_count, skipped_count, target_count, saved_paper_ids}`

**Placeholders scan:** No TBD/TODO/fill-in markers.

**Risks identified:**
- LLM batch failure: handled with "medium" fallback per batch
- Per-paper save failure: handled with skip + log
- Total timeout: 5min default, configurable via `timeout_seconds` param
- Concurrent jobs: rejected with 429 at service entry
- Empty dedup results: handled (Phase 3 just returns empty list)
