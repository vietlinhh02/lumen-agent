"""Search session persistence service.

Stores search results, screening scores, and handles auto-save of
high-relevance papers for a project.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Paper, ProjectPaper, SearchRun, User

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
                saved.append(sid or doi or arxiv)
                break

    return saved


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
                    try:
                        await bg_db.rollback()
                    except Exception:
                        pass
                    skipped += 1

            job.status = "completed"
            job.result = {"saved": saved, "skipped": skipped}
            from datetime import datetime

            job.completed_at = datetime.utcnow()
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background auto-save job failed: %s", exc)
            try:
                if job is not None:
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

    asyncio.ensure_future(
        _run_search_job(job.id, run.id, project_id, user.id, query, limit)
    )

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
    from datetime import datetime

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

            # Run search — always try to download PDFs in parallel so the
            # user immediately sees which papers are downloadable (sorted to top)
            from app.services.paper_search import search_and_download

            search_req = PaperSearchRequest(query=query, limit=limit, download_pdfs=True)
            outcome = await search_and_download(search_req)
            results_dicts = [p.model_dump() for p in outcome.response.papers]

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
            job.completed_at = datetime.utcnow()
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background search job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.completed_at = datetime.utcnow()
                    await bg_db.commit()
            except Exception:
                pass
