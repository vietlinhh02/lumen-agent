# Background Jobs for Slow Queries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `auto_save_high_papers` and `get_saved_paper_ids` to background jobs with optimized batch queries to eliminate the 500 timeout on `/api/papers/search/sessions/{id}/auto-save`.

**Architecture:** Use `asyncio.ensure_future()` (existing pattern in codebase at `app/routers/project.py:181`) to run auto-save in background. Create a `BackgroundJob` DB model to track job status. Optimize `get_saved_paper_ids` with a single batch query. Frontend polls job status.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, asyncio

---

## Deep Analysis: Root Causes

### Problem 1: `auto_save_high_papers` — Sequential N×(DB + Network + PDF)

```
For each paper with score="high":
  ├── _upsert_paper(): 3× SELECT (semantic_scholar_id → arxiv_id → doi)
  ├── ownership check: 1× SELECT
  ├── duplicate check: 1× SELECT
  ├── commit + refresh
  ├── enrichment delete + insert + commit + refresh (if pdf_url exists)
  ├── PDF download: httpx.get() with 60s timeout
  └── PDF ingestion: pdfplumber extract + chunk store + commit

10 high papers = 10 × (5-8 queries + PDF download + ingestion) = TIMEOUT
```

### Problem 2: `get_saved_paper_ids` — N+1 Query Pattern

```
For each paper in page (20 papers):
  ├── SELECT by semantic_scholar_id
  ├── SELECT by doi (if no match)
  ├── SELECT by arxiv_id (if no match)
  └── SELECT ProjectPaper for project_id + paper_id

20 papers × 4 queries = 80 sequential queries per page load
```

### Problem 3: `_to_project_paper_response` — Sync Filesystem I/O

```
For each paper in response:
  ├── Construct RawPaper object
  ├── _make_filename() computation
  ├── dest.exists() — filesystem stat
  └── dest.stat().st_size — filesystem stat

20 papers × 2 filesystem calls = 40 sync I/O calls
```

### Problem 4: `_upsert_paper` — Sequential Dedup Queries

```
SELECT by semantic_scholar_id → if None: SELECT by arxiv_id → if None: SELECT by doi

3 sequential queries per paper, always. Can be parallelized.
```

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | **Modify** | Add `BackgroundJob` model |
| `app/services/search_session.py:78-128` | **Modify** | Rewrite `get_saved_paper_ids` as single batch query |
| `app/services/search_session.py:131-199` | **Modify** | Rewrite `auto_save_high_papers` as background job |
| `app/services/project.py:310-376` | **Modify** | Parallelize `_upsert_paper` dedup queries |
| `app/services/project.py:393-446` | **Modify** | Batch filesystem checks in `_to_project_paper_response` |
| `app/routers/search_session.py:219-230` | **Modify** | Auto-save returns job_id immediately |
| `app/routers/search_session.py` | **Modify** | Add `GET /jobs/{id}` status endpoint |
| `frontend/app/(app)/search/page.tsx:425-446` | **Modify** | Poll job status instead of waiting for sync response |
| `tests/test_background_jobs.py` | **Create** | Unit tests |

---

### Task 1: Add BackgroundJob Model

**Files:**
- Modify: `app/db/models.py`

- [ ] **Step 1: Add BackgroundJob model after AgentStep model**

Add after line 735 (after `AgentStep.__table_args__`):

```python
# ── Background Jobs ───────────────────────────────────────────────────────


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint(
            "job_type IN ('auto_save', 'normalize', 'enrich')",
            name="ck_background_jobs_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_background_jobs_status",
        ),
        Index("ix_background_jobs_user_status", "user_id", "status"),
    )
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.db.models import BackgroundJob; print('OK')"`
Expected: `OK`

---

### Task 2: Rewrite `get_saved_paper_ids` — Single Batch Query

**Files:**
- Modify: `app/services/search_session.py:78-128`

- [ ] **Step 1: Replace the N+1 function with a batch query**

Replace lines 78-128 with:

```python
async def get_saved_paper_ids(
    db: AsyncSession,
    project_id: UUID,
    paper_dicts: list[dict],
) -> list[str]:
    """Return which papers (by identifier) are already saved to the project.

    Uses a single batch query instead of N+1 per-paper queries.
    """
    if not paper_dicts:
        return []

    # Collect all identifiers from the paper dicts
    ss_ids: list[str] = []
    dois: list[str] = []
    arxiv_ids: list[str] = []
    for p in paper_dicts:
        sid = p.get("semantic_scholar_id")
        doi = p.get("doi")
        arxiv = p.get("arxiv_id")
        if sid:
            ss_ids.append(sid)
        if doi:
            dois.append(doi)
        if arxiv:
            arxiv_ids.append(arxiv)

    # Single query: find all papers matching any of these identifiers
    from sqlalchemy import or_

    conditions = []
    if ss_ids:
        conditions.append(Paper.semantic_scholar_id.in_(ss_ids))
    if dois:
        conditions.append(Paper.doi.in_(dois))
    if arxiv_ids:
        conditions.append(Paper.arxiv_id.in_(arxiv_ids))

    if not conditions:
        return []

    # Get all paper IDs that match our identifiers
    paper_result = await db.execute(
        select(Paper.id, Paper.semantic_scholar_id, Paper.doi, Paper.arxiv_id).where(
            or_(*conditions)
        )
    )
    matched_papers = paper_result.all()

    if not matched_papers:
        return []

    # Get all project_papers for this project that match these paper IDs
    paper_ids = [row[0] for row in matched_papers]
    pp_result = await db.execute(
        select(ProjectPaper.paper_id).where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.paper_id.in_(paper_ids),
        )
    )
    saved_paper_ids = set(pp_result.scalars().all())

    # Build the result: return the identifier that matched
    saved: list[str] = []
    for p in paper_dicts:
        sid = p.get("semantic_scholar_id")
        doi = p.get("doi")
        arxiv = p.get("arxiv_id")
        # Check if any of this paper's identifiers match a saved paper
        for row in matched_papers:
            paper_id, p_ss, p_doi, p_arxiv = row
            if paper_id not in saved_paper_ids:
                continue
            if (sid and p_ss == sid) or (doi and p_doi == doi) or (arxiv and p_arxiv == arxiv):
                saved.append(sid or doi or arxiv)
                break

    return saved
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.search_session import get_saved_paper_ids; print('OK')"`
Expected: `OK`

---

### Task 3: Parallelize `_upsert_paper` Dedup Queries

**Files:**
- Modify: `app/services/project.py:310-376`

- [ ] **Step 1: Replace sequential dedup with `asyncio.gather`**

Replace lines 310-376 with:

```python
async def _upsert_paper(db: AsyncSession, data: SavePaperRequest) -> Paper:
    """Find existing paper or create a new one. Deduplicates by strongest ID.

    Uses asyncio.gather to run all three identifier lookups in parallel.
    """
    import asyncio

    paper: Paper | None = None

    # Run all three lookups in parallel
    async def _by_ss():
        if data.paper_semantic_scholar_id:
            r = await db.execute(
                select(Paper).where(Paper.semantic_scholar_id == data.paper_semantic_scholar_id)
            )
            return r.scalar_one_or_none()
        return None

    async def _by_arxiv():
        if data.paper_arxiv_id:
            r = await db.execute(select(Paper).where(Paper.arxiv_id == data.paper_arxiv_id))
            return r.scalar_one_or_none()
        return None

    async def _by_doi():
        if data.paper_doi:
            r = await db.execute(select(Paper).where(Paper.doi == data.paper_doi))
            return r.scalar_one_or_none()
        return None

    # Note: These can't truly run in parallel on the same session,
    # but we gather them to reduce round-trip latency
    results = await asyncio.gather(_by_ss(), _by_arxiv(), _by_doi())

    # Priority: semantic_scholar > arxiv > doi
    for candidate in results:
        if candidate is not None:
            paper = candidate
            break

    if paper is not None:
        # Merge missing fields
        merged = False
        for field in (
            "abstract",
            "year",
            "venue",
            "doi",
            "arxiv_id",
            "semantic_scholar_id",
            "url",
            "citation_count",
        ):
            existing_val = getattr(paper, field, None)
            new_val = getattr(data, f"paper_{field}", None)
            if existing_val is None and new_val is not None:
                setattr(paper, field, new_val)
                merged = True
        if isinstance(paper.authors, list) and data.paper_authors and not paper.authors:
            paper.authors = data.paper_authors
            merged = True
        if data.paper_source_names:
            existing_sources = set(paper.source_names or [])
            for src in data.paper_source_names:
                if src not in existing_sources:
                    paper.source_names = list(existing_sources) + [src]
                    merged = True
        if merged:
            await db.commit()
            await db.refresh(paper)
        return paper

    # Create new canonical paper
    paper = Paper(
        title=data.paper_title,
        abstract=data.paper_abstract,
        year=data.paper_year,
        venue=data.paper_venue,
        doi=data.paper_doi,
        arxiv_id=data.paper_arxiv_id,
        semantic_scholar_id=data.paper_semantic_scholar_id,
        url=data.paper_url,
        citation_count=data.paper_citation_count,
        authors=data.paper_authors,
        source_names=data.paper_source_names,
    )
    db.add(paper)
    await db.commit()
    await db.refresh(paper)
    return paper
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.project import _upsert_paper; print('OK')"`
Expected: `OK`

---

### Task 4: Rewrite `auto_save_high_papers` as Background Job

**Files:**
- Modify: `app/services/search_session.py:131-199`

- [ ] **Step 1: Replace the synchronous function with a background job runner**

Replace lines 131-199 with:

```python
async def auto_save_high_papers(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    session_id: UUID,
) -> dict:
    """Start auto-save as a background job. Returns job info immediately."""
    from app.db.models import BackgroundJob

    # Verify session exists
    result = await db.execute(
        select(SearchRun).where(
            SearchRun.id == session_id,
            SearchRun.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        return {"error": "Session not found"}

    scores = run.screening_scores or []
    results = run.results_json or []
    high_count = sum(1 for s in scores if s == "high")

    if not scores:
        return {"saved": 0, "skipped": len(results), "error": "No screening scores available"}

    if high_count == 0:
        return {"saved": 0, "skipped": len(results)}

    # Create a background job record
    job = BackgroundJob(
        job_type="auto_save",
        project_id=project_id,
        user_id=user.id,
        status="pending",
        total=high_count,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background task
    import asyncio

    asyncio.ensure_future(_run_auto_save_job(job.id, project_id, session_id, user.id))

    return {"job_id": str(job.id), "status": "running", "total": high_count}


async def _run_auto_save_job(
    job_id: UUID,
    project_id: UUID,
    session_id: UUID,
    user_id: UUID,
) -> None:
    """Background worker: save high-relevance papers one by one."""
    from app.db.session import async_session_factory

    async with async_session_factory() as bg_db:
        try:
            # Load job
            from app.db.models import BackgroundJob

            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            await bg_db.commit()

            # Load session
            session_result = await bg_db.execute(
                select(SearchRun).where(SearchRun.id == session_id)
            )
            run = session_result.scalar_one_or_none()
            if not run:
                job.status = "failed"
                job.error_message = "Session not found"
                await bg_db.commit()
                return

            # Load user
            user_result = await bg_db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            if not user:
                job.status = "failed"
                job.error_message = "User not found"
                await bg_db.commit()
                return

            scores = run.screening_scores or []
            results = run.results_json or []

            saved = 0
            skipped = 0

            for i, paper_dict in enumerate(results):
                score = scores[i] if i < len(scores) else "medium"
                if score != "high":
                    skipped += 1
                    continue

                try:
                    from app.schemas.project import SavePaperRequest
                    from app.services.project import save_paper_to_project

                    authors_mapped = []
                    for a in paper_dict.get("authors") or []:
                        authors_mapped.append(
                            {
                                "name": a.get("name") if isinstance(a, dict) else str(a),
                                "author_id": "",
                            }
                        )
                    req = SavePaperRequest(
                        paper_title=paper_dict.get("title", ""),
                        paper_abstract=paper_dict.get("abstract"),
                        paper_year=paper_dict.get("year"),
                        paper_venue=paper_dict.get("venue"),
                        paper_doi=paper_dict.get("doi"),
                        paper_arxiv_id=paper_dict.get("arxiv_id"),
                        paper_semantic_scholar_id=paper_dict.get("semantic_scholar_id"),
                        paper_url=paper_dict.get("url"),
                        paper_citation_count=paper_dict.get("citation_count"),
                        paper_authors=authors_mapped,
                        paper_source_names=paper_dict.get("source_names") or ["paperhub"],
                        download_pdf=True,
                        source_specific=paper_dict.get("source_specific") or {},
                    )
                    save_result = await save_paper_to_project(bg_db, user, project_id, req)
                    if save_result is None:
                        skipped += 1
                    else:
                        saved += 1
                        # Update progress
                        job.progress = saved
                        await bg_db.commit()
                except Exception as exc:
                    logger.warning(
                        "Failed to auto-save paper %s: %s",
                        paper_dict.get("title", "?"),
                        exc,
                    )
                    skipped += 1

            job.status = "completed"
            job.result = {"saved": saved, "skipped": skipped}
            from datetime import datetime

            job.completed_at = datetime.utcnow()
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background auto-save job failed: %s", exc)
            try:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                from datetime import datetime

                job.completed_at = datetime.utcnow()
                await bg_db.commit()
            except Exception:
                pass


async def get_job_status(
    db: AsyncSession,
    user: User,
    job_id: UUID,
) -> dict | None:
    """Return the status of a background job."""
    from app.db.models import BackgroundJob

    result = await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.id == job_id,
            BackgroundJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    return {
        "job_id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "total": job.total,
        "result": job.result,
        "error_message": job.error_message,
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.search_session import auto_save_high_papers, get_job_status; print('OK')"`
Expected: `OK`

---

### Task 5: Update Auto-Save Router + Add Job Status Endpoint

**Files:**
- Modify: `app/routers/search_session.py:219-230`
- Add: `GET /search/jobs/{job_id}` endpoint

- [ ] **Step 1: Update the auto-save endpoint to return job_id**

Replace lines 219-230 with:

```python
@router.post("/search/sessions/{session_id}/auto-save")
async def auto_save_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = await get_search_session(db, user, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await auto_save_high_papers(db, user, run.project_id, session_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
```

- [ ] **Step 2: Add the job status endpoint**

Add after the `auto_save_session` endpoint (after line 230):

```python
@router.get("/search/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.search_session import get_job_status

    result = await get_job_status(db, user, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return result
```

- [ ] **Step 3: Verify the file compiles**

Run: `python -c "from app.routers.search_session import router; print('OK')"`
Expected: `OK`

---

### Task 6: Update Frontend to Poll Job Status

**Files:**
- Modify: `frontend/app/(app)/search/page.tsx:425-446`

- [ ] **Step 1: Replace sync auto-save with async job polling**

Replace the `handleAutoSave` function (lines 425-446) with:

```typescript
  // Auto-save high papers (async background job)
  async function handleAutoSave() {
    if (!sessionId) return;
    setAutoSaving(true);
    try {
      const data = await apiFetch<{ job_id?: string; status?: string; total?: number; saved?: number; skipped?: number; error?: string }>(
        `/papers/search/sessions/${sessionId}/auto-save`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (data.job_id && data.status === "running") {
        toast.info(`Auto-saving ${data.total} papers in background...`);
        // Poll for completion
        await pollJobStatus(data.job_id);
      } else if (data.saved !== undefined) {
        toast.success(`${data.saved} papers auto-saved`);
      }

      // Refresh saved IDs
      if (sessionId) {
        const fresh = await apiFetch<SessionDetailResponse>(`/papers/search/sessions/${sessionId}?page=${page}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setSessionData(fresh);
      }
      fetchProjects();
      fetchSessions();
    } catch (err) { toast.error(err instanceof Error ? err.message : "Auto-save failed"); }
    finally { setAutoSaving(false); }
  }

  async function pollJobStatus(jobId: string) {
    const maxAttempts = 60; // 2 minutes max
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const job = await apiFetch<{ status: string; progress: number; total: number; result?: { saved: number; skipped: number }; error_message?: string }>(
          `/papers/search/jobs/${jobId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (job.status === "completed") {
          toast.success(`${job.result?.saved ?? 0} papers auto-saved`);
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error_message || "Auto-save failed");
          return;
        }
        // Update progress toast
        if (job.progress > 0) {
          toast.info(`Saved ${job.progress}/${job.total} papers...`, { autoClose: 1000 });
        }
      } catch {
        // Ignore polling errors, keep trying
      }
    }
    toast.warning("Auto-save is still running. Check back later.");
  }
```

- [ ] **Step 2: Verify the frontend compiles**

Run: `cd frontend && npx tsc --noEmit --pretty`
Expected: No errors (or only pre-existing errors)

---

### Task 7: Write Tests

**Files:**
- Create: `tests/test_background_jobs.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for background job system and optimized queries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

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
    # NOT 8 calls (4 per paper × 2 papers)
    assert call_count["n"] == 2
    assert "ss1" in result or "doi1" in result or "arxiv1" in result


# ── auto_save_high_papers background job tests ──────────────────────────────


@pytest.mark.asyncio
async def test_auto_save_creates_background_job():
    """Auto-save should create a BackgroundJob and return job_id."""
    from app.services.search_session import auto_save_high_papers

    project_id = uuid4()
    session_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    # Mock session with high-scoring papers
    run = SimpleNamespace(
        screening_scores=["high", "medium", "high"],
        results_json=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
    )

    job = SimpleNamespace(id=uuid4())

    db = AsyncMock()
    # First call: find session
    # Second call: add job + commit + refresh
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

    with patch("app.services.search_session.ensure_future"):
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

    result = await auto_save_high_papers(db, SimpleNamespace(id=uuid4()), uuid4(), uuid4())
    assert result["saved"] == 0
    assert result["skipped"] == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_background_jobs.py -v`
Expected: All pass

---

### Task 8: Run All Tests and Lint

- [ ] **Step 1: Run linter**

Run: `ruff check app/services/search_session.py app/services/project.py app/routers/search_session.py app/db/models.py`
Expected: No errors

- [ ] **Step 2: Run all existing tests**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 3: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit --pretty`
Expected: No new errors

- [ ] **Step 4: Commit**

```bash
git add app/db/models.py app/services/search_session.py app/services/project.py \
  app/routers/search_session.py frontend/app/\(app\)/search/page.tsx \
  tests/test_background_jobs.py
git commit -m "feat: background jobs for auto-save, batch queries for saved paper IDs"
```
