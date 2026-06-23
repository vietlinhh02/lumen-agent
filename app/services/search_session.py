"""Search session persistence service.

Stores search results, screening scores, and handles auto-save of
high-relevance papers for a project.
"""

from __future__ import annotations

import contextlib
import logging
from asyncio import ensure_future
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import AUTO_SEARCH_SCREEN_SYSTEM, AUTO_SEARCH_SCREEN_USER
from app.ai.provider import get_provider
from app.db.models import Paper, Project, ProjectPaper, SearchRun, User
from app.db.session import async_session_factory
from app.schemas.paper import PaperSearchRequest
from app.schemas.project import SavePaperRequest
from app.services.paper_search import _deduplicate_raw_books, search_and_download
from app.services.project import save_paper_to_project

logger = logging.getLogger(__name__)


async def create_search_session(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    query: str,
    results: list[dict],
    total_found: int,
    detected_language: str | None = None,
    language_policy: str = "balanced",
    target_languages: list[str] | None = None,
    english_dominance_score: float | None = None,
    query_variants: list[dict] | None = None,
    language_bias_audit: dict | None = None,
    source_diagnostics: list[dict] | None = None,
) -> SearchRun:
    run = SearchRun(
        project_id=project_id,
        user_query=query,
        total_results=total_found,
        results_json=results,
        detected_language=detected_language,
        language_policy=language_policy,
        target_languages=target_languages or [],
        english_dominance_score=english_dominance_score,
        query_variants=query_variants or [],
        language_bias_audit=language_bias_audit,
        source_diagnostics=source_diagnostics or [],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_search_session(
    db: AsyncSession,
    user: User,
    session_id: UUID,
) -> SearchRun | None:
    result = await db.execute(select(SearchRun).where(SearchRun.id == session_id))
    return result.scalar_one_or_none()


async def list_search_sessions(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    limit: int = 10,
) -> list[SearchRun]:
    result = await db.execute(
        select(SearchRun)
        .where(SearchRun.project_id == project_id)
        .order_by(SearchRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def save_screening_scores(
    db: AsyncSession,
    session_id: UUID,
    scores: list[str],
) -> bool:
    result = await db.execute(select(SearchRun).where(SearchRun.id == session_id))
    run = result.scalar_one_or_none()
    if run is None:
        return False
    run.screening_scores = scores
    await db.commit()
    return True


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
                matched_id = sid or doi or arxiv
                if matched_id:
                    saved.append(matched_id)
                break

    return saved


async def find_paper_index_in_session(
    run: SearchRun,
    *,
    semantic_scholar_id: str | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
) -> int:
    """Find the index of a paper inside ``run.results_json``.

    Tries the strongest identifier first (ss_id → doi → arxiv_id → title).
    Returns ``-1`` if no match is found.
    """
    results = run.results_json or []
    for i, p in enumerate(results):
        if semantic_scholar_id and p.get("semantic_scholar_id") == semantic_scholar_id:
            return i
    for i, p in enumerate(results):
        if doi and p.get("doi") == doi:
            return i
    for i, p in enumerate(results):
        if arxiv_id and p.get("arxiv_id") == arxiv_id:
            return i
    if title:
        target = title.strip().lower()
        for i, p in enumerate(results):
            if (p.get("title") or "").strip().lower() == target:
                return i
    return -1


async def download_single_session_paper(
    db: AsyncSession,
    user: User,
    session_id: UUID,
    *,
    semantic_scholar_id: str | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str | None = None,
) -> dict:
    """Download a single paper's PDF on-demand from a search session.

    Updates ``SearchRun.results_json[index]`` with the new ``pdf_downloaded``,
    ``pdf_path`` and ``pdf_source`` fields and commits the change so the
    next GET to the session returns the updated state.

    Returns the updated paper dict.
    """
    run = await get_search_session(db, user, session_id)
    if not run:
        return {"error": "Session not found"}

    idx = await find_paper_index_in_session(
        run,
        semantic_scholar_id=semantic_scholar_id,
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
    )
    if idx < 0:
        return {"error": "Paper not found in session"}

    paper_dict = (run.results_json or [])[idx]
    if paper_dict.get("pdf_downloaded") and paper_dict.get("pdf_path"):
        # Idempotent: already downloaded
        return {"ok": True, "paper": paper_dict, "index": idx, "already_downloaded": True}

    from app.core.config import get_settings
    from app.services.paper_search import dict_to_raw_paper
    from app.services.pdf_downloader import PDFDownloader

    settings = get_settings()
    raw = dict_to_raw_paper(paper_dict)

    downloader = PDFDownloader(output_dir=Path(settings.paper_pdf_dir), timeout=90)
    pdf_path = await downloader.download(raw)

    if pdf_path is None:
        # Download failed — surface reason back to caller
        from app.services.paper_search import _failure_reason

        return {
            "ok": False,
            "paper": paper_dict,
            "index": idx,
            "error": _failure_reason(raw),
        }

    paper_dict["pdf_downloaded"] = True
    # Store the public URL path (mounted at /api/pdf-files) — matches the
    # convention used by /projects/{id}/papers so the frontend can render
    # the PDF directly.
    paper_dict["pdf_path"] = f"/api/pdf-files/{pdf_path.name}"

    # Best-effort classify the source
    if raw.arxiv_id:
        paper_dict["pdf_source"] = "arxiv_cdn"
    elif raw.source_specific.get("pdf_url"):
        paper_dict["pdf_source"] = "s2_oa"
    elif raw.source_specific.get("paperhub_source"):
        paper_dict["pdf_source"] = str(raw.source_specific["paperhub_source"])
    else:
        paper_dict["pdf_source"] = paper_dict.get("pdf_source") or "direct"

    # Persist back into the session
    results = list(run.results_json or [])
    results[idx] = paper_dict
    run.results_json = results
    await db.commit()
    await db.refresh(run)

    return {"ok": True, "paper": paper_dict, "index": idx}


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
    
    # Calculate high_count based on both "high" score and "can_download"
    high_count = 0
    for i, paper_dict in enumerate(results):
        score = scores[i] if i < len(scores) else "medium"
        if score == "high":
            can_download = paper_dict.get(
                "can_download",
                bool(paper_dict.get("arxiv_id") or paper_dict.get("source_specific", {}).get("pdf_url") or paper_dict.get("source_specific", {}).get("pmc_id"))
            )
            if can_download:
                high_count += 1

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
        job = None
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

                can_download = paper_dict.get(
                    "can_download",
                    bool(paper_dict.get("arxiv_id") or paper_dict.get("source_specific", {}).get("pdf_url") or paper_dict.get("source_specific", {}).get("pmc_id"))
                )
                if not can_download:
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
                    # Roll back so the session is usable for the next paper
                    with contextlib.suppress(Exception):
                        await bg_db.rollback()
                    skipped += 1

            job.status = "completed"
            job.result = {"saved": saved, "skipped": skipped}
            from datetime import UTC, datetime

            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background auto-save job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    from datetime import UTC, datetime

                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
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
        "progress_json": job.progress_json,
        "result": job.result,
        "error_message": job.error_message,
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }


# ── Background search job ──────────────────────────────────────────────────


async def start_search_job(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    query: str,
    limit: int = 100,
) -> dict:
    """Create a SearchRun + BackgroundJob and launch the search in background.

    Returns immediately with ``{job_id, session_id, status}`` so the caller
    can poll for completion.
    """
    from app.db.models import BackgroundJob

    # Create an empty SearchRun as a placeholder — results populate later
    run = SearchRun(
        project_id=project_id,
        user_query=query,
        total_results=0,
        results_json=[],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Create a background job record
    job = BackgroundJob(
        job_type="paper_search",
        project_id=project_id,
        user_id=user.id,
        status="pending",
        total=limit,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background worker
    import asyncio

    asyncio.ensure_future(_run_search_job(job.id, run.id, project_id, user.id, query, limit))

    return {
        "job_id": str(job.id),
        "session_id": str(run.id),
        "status": "running",
    }


async def _run_search_job(
    job_id: UUID,
    session_id: UUID,
    project_id: UUID,
    user_id: UUID,
    query: str,
    limit: int,
) -> None:
    """Background worker: run search_and_download, persist results to SearchRun."""
    from datetime import UTC, datetime

    from app.db.session import async_session_factory
    from app.schemas.paper import PaperSearchRequest

    async with async_session_factory() as bg_db:
        job = None
        try:
            from app.db.models import BackgroundJob, SearchRun

            # Load job
            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            await bg_db.commit()

            # Run search WITHOUT pre-downloading PDFs. The UI shows results
            # immediately and the user can request a PDF per-paper on demand
            # (see POST /api/papers/search/sessions/{id}/download-pdf).
            # We still mark `can_download` on each result from metadata so the
            # UI can sort / hint which papers are likely downloadable.
            from app.services.paper_search import search_and_download

            search_req = PaperSearchRequest(query=query, limit=limit, download_pdfs=False)
            outcome = await search_and_download(search_req)
            results_dicts = [p.model_dump() for p in outcome.response.papers]

            # Attach a lightweight `can_download` flag derived from metadata
            # (arxiv_id or open-access pdf_url) — no network calls.
            from app.services.paper_search import annotate_can_download

            annotate_can_download(results_dicts)

            audit_data = outcome.response.language_bias_audit

            # Update SearchRun with results
            session_result = await bg_db.execute(
                select(SearchRun).where(SearchRun.id == session_id)
            )
            run = session_result.scalar_one_or_none()
            if run is None:
                job.status = "failed"
                job.error_message = "Session not found"
                await bg_db.commit()
                return

            run.user_query = query
            run.total_results = len(results_dicts)
            run.results_json = results_dicts
            run.detected_language = outcome.response.detected_language
            run.query_variants = [v.model_dump() for v in outcome.response.query_variants]
            run.source_diagnostics = outcome.response.source_diagnostics or []
            if audit_data:
                run.english_dominance_score = audit_data.english_dominance_score
                run.language_bias_audit = audit_data.model_dump()
            await bg_db.commit()

            # Mark job complete
            job.status = "completed"
            job.progress = len(results_dicts)
            job.result = {
                "total_found": len(results_dicts),
                "session_id": str(session_id),
            }
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background search job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass


# ── Auto search & save ──────────────────────────────────────────────────


async def _generate_query_from_project(project) -> str:
    """Use the LLM to generate a single high-quality search query for the
    given project. Falls back to the project topic on any LLM error.
    """
    from app.ai.prompts import (
        SEARCH_SUGGEST_SYSTEM,
        SEARCH_SUGGEST_USER,
        format_protocol_for_prompt,
    )
    from app.ai.provider import get_provider

    provider = get_provider()
    protocol_text = format_protocol_for_prompt(project.review_protocol or {})
    user_msg = SEARCH_SUGGEST_USER.format(
        title=project.title or "",
        topic=project.topic or "",
        research_question=project.research_question or project.topic or "",
        protocol_context=protocol_text,
    )
    raw = await provider.complete_structured(
        messages=[{"role": "user", "content": user_msg}],
        system=SEARCH_SUGGEST_SYSTEM,
        schema={
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 4,
                    "maxItems": 6,
                },
            },
            "required": ["queries"],
        },
        tool_name="auto_search_generate_query",
        max_tokens=800,
    )
    queries = raw.get("queries", []) if isinstance(raw, dict) else []
    # Pick the first one; fall back to topic if empty.
    if queries and isinstance(queries[0], str) and queries[0].strip():
        return queries[0].strip()
    return (project.topic or "").strip()


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

    from sqlalchemy import and_

    from app.db.models import BackgroundJob

    # 1. Verify project ownership
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        return {"error": "Project not found"}

    # 1b. If no query provided, auto-generate one from the project's topic
    # + research question + review protocol.
    effective_query = (query or "").strip()
    if not effective_query:
        try:
            effective_query = await _generate_query_from_project(project)
        except Exception as exc:
            logger.warning("Auto-query generation failed, falling back to topic: %s", exc)
            effective_query = (project.topic or "").strip()
        if not effective_query:
            return {
                "error": (
                    "Cannot auto-search: no query provided and project has no "
                    "topic. Please enter a search query."
                ),
                "status_code": 400,
            }
        logger.info("Auto-search: generated query '%s' from project", effective_query[:80])

    # 2. Check for concurrent auto_search job for this user
    running_result = await db.execute(
        select(BackgroundJob).where(
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
        user_query=effective_query,
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
    ensure_future(
        _run_auto_search_job(
            job.id, run.id, project_id, user.id, effective_query, target_count
        )
    )

    return {
        "job_id": str(job.id),
        "session_id": str(run.id),
        "target_count": target_count,
        "query": effective_query,
        "query_was_generated": not (query or "").strip(),
        "status": "running",
    }


# ── 4-phase auto-search worker ──────────────────────────────────────────


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
    from app.db.models import BackgroundJob

    import time
    from datetime import UTC, datetime

    start_wall = time.monotonic()
    job = None

    async with async_session_factory() as bg_db:
        try:
            # ── Load job + session + user ────────────────────────────────
            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            await bg_db.commit()

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

            async def _update_progress(payload: dict) -> None:
                job.progress_json = {**(job.progress_json or {}), **payload}
                job.progress = int(payload.get("percent", job.progress or 0))
                await bg_db.commit()

            # ── Phase 1: Search all sources in parallel ──────────────────
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

            batches_total = max(1, (len(deduped) + 24) // 25)
            await _update_progress({
                "phase": "scoring",
                "batches_total": batches_total,
                "papers_scored": 0,
                "papers_total": len(deduped),
                "percent": 30,
            })

            scores: list[str] = await _batch_score_papers(
                deduped, user, _update_progress, timeout_seconds, start_wall,
            )

            if time.monotonic() - start_wall > timeout_seconds:
                raise TimeoutError("Phase 2 exceeded timeout")

            # ── Phase 3: Filter + pick top N ──────────────────────────────
            scored = [
                (paper, score)
                for paper, score in zip(deduped, scores, strict=False)
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

            for idx, paper in enumerate(top_papers):
                if time.monotonic() - start_wall > timeout_seconds:
                    raise TimeoutError("Phase 4 exceeded timeout")

                paper_dict = _raw_paper_to_dict(paper)

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
                        paper_dict["screening_score"] = "high"
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


# ── Auto-search helpers ─────────────────────────────────────────────────


async def _batch_score_papers(
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
    import time

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
            batch_scores = result.get("scores", []) if isinstance(result, dict) else []
            for entry in batch_scores:
                if not isinstance(entry, dict):
                    continue
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


# Public alias so tests can monkeypatch ``app.services.search_session.batch_score_papers``.
batch_score_papers = _batch_score_papers


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

    Falls back to ``"research project"`` if no project is available.
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
