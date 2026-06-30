"""Search session persistence service.

Stores search results, screening scores, and handles auto-save of
high-relevance papers for a project.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from asyncio import ensure_future
from pathlib import Path
from time import monotonic
from typing import Literal, TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import AUTO_SEARCH_SCREEN_SYSTEM, AUTO_SEARCH_SCREEN_USER
from app.ai.provider import get_provider
from app.db.models import Paper, Project, ProjectPaper, SearchRun, User
from app.db.session import async_session_factory
from app.schemas.paper import PaperSearchRequest
from app.schemas.project import SavePaperRequest
from app.services.paper_search import search_and_download
from app.services.project import save_paper_to_project

logger = logging.getLogger(__name__)

_MAX_AUTO_SEARCH_SCORE_CANDIDATES = 180


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

    # Cap at a maximum of 25 papers
    if high_count > 25:
        high_count = 25

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
                # Cap at a maximum of 25 papers
                if saved >= 25:
                    skipped += 1
                    continue

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


async def _generate_queries_from_project(project) -> list[str]:
    """Use the LLM to generate multiple high-quality search queries for the
    given project. Returns 4-6 queries covering different angles
    (methodology, application, comparative, recent trends).

    Falls back to a single-element list with the project topic on any LLM
    error or when the LLM returns nothing usable.
    """
    from app.ai.prompts import (
        SEARCH_SUGGEST_SYSTEM,
        SEARCH_SUGGEST_USER,
        format_protocol_for_prompt,
    )
    from app.ai.provider import get_provider

    fallback = [(project.topic or "").strip()] if (project.topic or "").strip() else []

    try:
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
        cleaned = [
            q.strip() for q in queries
            if isinstance(q, str) and q.strip()
        ]
        # Dedupe (case-insensitive) but preserve order
        seen: set[str] = set()
        unique: list[str] = []
        for q in cleaned:
            key = q.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(q)
        if unique:
            return unique[:6]
    except Exception as exc:
        logger.warning("Auto-query generation failed, falling back to topic: %s", exc)

    return fallback


# Backwards-compatible alias for tests/older callers. Returns the first
# query as a string (the legacy single-query contract).
async def _generate_query_from_project(project) -> str:
    """Deprecated: prefer ``_generate_queries_from_project`` (list of 4-6)."""
    queries = await _generate_queries_from_project(project)
    return queries[0] if queries else (project.topic or "").strip()


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
    if target_count not in (5, 15, 25):
        raise ValueError(f"Target count must be 5, 15, or 25 (got {target_count})")

    from sqlalchemy import and_

    from app.db.models import BackgroundJob

    # 1. Verify project ownership
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        return {"error": "Project not found"}

    # 1b. If no query provided, auto-generate a SET of queries from the
    # project's topic + research question + review protocol. We search
    # each query and pick the top-scoring papers across the union — this
    # gives much better angle diversity than a single query (a single
    # query tends to over-fit to one phrasing and miss relevant papers
    # that use different terminology).
    effective_queries: list[str]
    if (query or "").strip():
        effective_queries = [(query or "").strip()]
    else:
        try:
            effective_queries = await _generate_queries_from_project(project)
        except Exception as exc:
            logger.warning("Auto-query generation failed, falling back to topic: %s", exc)
            effective_queries = [(project.topic or "").strip()] if (project.topic or "").strip() else []
        if not effective_queries:
            return {
                "error": (
                    "Cannot auto-search: no query provided and project has no "
                    "topic. Please enter a search query."
                ),
                "status_code": 400,
            }
        logger.info(
            "Auto-search: generated %d queries from project: %s",
            len(effective_queries),
            " | ".join(q[:40] for q in effective_queries),
        )
    # Primary query for the SearchRun record / progress display.
    effective_query = effective_queries[0]   # used only for status payload

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

    # 5. Launch worker — pass the full list of queries (not just the first)
    ensure_future(
        _run_auto_search_job(
            job.id,
            run.id,
            project_id,
            user.id,
            effective_queries,
            target_count,
            timeout_seconds=_auto_search_timeout_seconds(target_count),
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
    queries: list[str] | str,
    target_count: int,
    timeout_seconds: int = 300,
) -> None:
    """4-phase auto-search worker.

    Phase 1 (0-25%):  Fan-out search across all sources for EACH query in
                     the list, then dedupe across queries. A paper that
                     matches multiple queries is preferred (it gets a
                     higher boost in scoring) because that signals robust
                     relevance across phrasings.
    Phase 2 (25-60%): Dedupe + batch LLM score (25/batch)
    Phase 3 (60-65%): Filter score=high, pick top N (fallback to medium)
    Phase 4 (65-100%): Auto-save top N papers (skip duplicates)

    Updates ``job.progress_json`` between phases so the frontend polling
    endpoint can show a multi-step progress UI.
    """
    from app.db.models import BackgroundJob

    from datetime import UTC, datetime

    # Defensive: callers (tests, future code) might still pass a single string.
    if isinstance(queries, str):
        queries = [queries]

    start_wall = monotonic()
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
            project_result = await bg_db.execute(select(Project).where(Project.id == project_id))
            project = project_result.scalar_one_or_none()
            if run is None or user is None or project is None:
                job.status = "failed"
                job.error_message = "Session, user, or project not found"
                await bg_db.commit()
                return

            async def _update_progress(payload: dict) -> None:
                job.progress_json = {**(job.progress_json or {}), **payload}
                job.progress = int(payload.get("percent", job.progress or 0))
                await bg_db.commit()

            # ── Phase 1: Multi-query search, dedupe across queries ───────
            #
            # Each query fans out to all sources in parallel. We then dedupe
            # by canonical identifier (S2 / arxiv / DOI / title). A paper
            # that appears for multiple queries gets ``match_count`` bumped
            # — the dedupe function returns that as a side-channel so we
            # can use it as a relevance signal later.
            n_queries = len(queries)
            await _update_progress({
                "phase": "searching",
                "current_source": f"queries 0/{n_queries}",
                "papers_found": 0,
                "queries_total": n_queries,
                "queries_done": 0,
                "percent": 5,
            })

            # Smaller per-query budget since we now run N of them in parallel.
            # 200/source was designed for a single query; with 4-6 queries we
            # would balloon the dedupe + scoring cost, so cap each at 60/source.
            per_query_cap = 60
            all_raw: list = []
            query_search_tasks = []
            for q in queries:
                search_req = PaperSearchRequest(
                    query=q, limit=per_query_cap * 5, download_pdfs=False,
                )
                query_search_tasks.append(
                    search_and_download(search_req, max_per_source=per_query_cap)
                )

            # Run all queries' searches concurrently (each query itself
            # fans out across sources internally).
            per_query_outcomes = await asyncio.gather(
                *query_search_tasks, return_exceptions=True,
            )
            for idx, outcome in enumerate(per_query_outcomes):
                if isinstance(outcome, BaseException):
                    logger.warning(
                        "Query %d/%d search failed: %s",
                        idx + 1, n_queries, outcome,
                    )
                    continue
                all_raw.extend(outcome.raw_papers)
                await _update_progress({
                    "phase": "searching",
                    "current_source": f"queries {idx + 1}/{n_queries}",
                    "papers_found": len(all_raw),
                    "queries_total": n_queries,
                    "queries_done": idx + 1,
                    "percent": 5 + int(15 * (idx + 1) / max(1, n_queries)),
                })

            # Dedupe across all queries. ``_deduplicate_with_match_counts``
            # also returns a dict: canonical_key -> match_count, which the
            # downstream score step can use to bump papers that matched
            # multiple queries.
            deduped, match_counts = _deduplicate_with_match_counts(all_raw)

            await _update_progress({
                "phase": "searching",
                "current_source": "done",
                "papers_found": len(deduped),
                "queries_total": n_queries,
                "queries_done": n_queries,
                "multi_match_papers": sum(1 for c in match_counts.values() if c > 1),
                "percent": 25,
            })

            if monotonic() - start_wall > timeout_seconds:
                raise TimeoutError("Phase 1 exceeded timeout")

            # ── Phase 2: Batch LLM score ──────────────────────────────────
            # ``deduped`` and ``match_counts`` already come from Phase 1.

            score_limit = _auto_search_score_candidate_limit(target_count)
            candidates_to_score = _rank_auto_search_candidates(
                deduped,
                match_counts,
                queries,
                score_limit,
            )
            batches_total = max(1, (len(candidates_to_score) + 24) // 25)
            await _update_progress({
                "phase": "scoring",
                "batches_total": batches_total,
                "papers_scored": 0,
                "papers_total": len(candidates_to_score),
                "candidate_pool_total": len(deduped),
                "candidate_pool_scored": len(candidates_to_score),
                "percent": 30,
            })

            scores: list[str] = await batch_score_papers(
                candidates_to_score,
                project.topic or "research project",
                project.research_question or "Not specified",
                _update_progress,
                timeout_seconds,
                start_wall,
            )

            scoring_exceeded_timeout = monotonic() - start_wall > timeout_seconds
            if scoring_exceeded_timeout:
                logger.warning(
                    "Auto-search job %s exceeded scoring budget; continuing "
                    "with %d scored/defaulted candidates",
                    job_id,
                    len(candidates_to_score),
                )

            # ── Phase 3: Filter + pick top N ──────────────────────────────
            #
            # Build a (paper, score, match_count) triple. match_count comes
            # from Phase 1 dedupe — a paper that matched across multiple
            # queries is more robustly relevant, so we apply a small boost:
            #
            #   match_count >= 2 AND original_score in ("medium", "low")
            #     -> bump to "medium" if it was "low", leave "medium" alone
            #     (we don't bump medium→high to avoid inflating uncertain hits)
            #
            # We never OVERRIDE a "high" downward. And we never promote a
            # "low" to "high" — match_count > 1 only means the paper is
            # robustly found across phrasings; it doesn't change its
            # topical relevance judgment from the LLM.
            eligibility_signals = {
                "off_topic_condition": 0,
                "methodology_only": 0,
                "clinical_or_domain_evidence": 0,
                "neutral": 0,
            }
            scored: list[tuple] = []
            for paper, raw_score in zip(candidates_to_score, scores, strict=False):
                if raw_score not in ("high", "medium", "low"):
                    continue
                mcount = match_counts.get(_canonical_paper_key(paper), 1)
                effective_score = raw_score
                eligibility = _score_auto_search_eligibility(paper, queries)
                eligibility_signals[eligibility["category"]] += 1
                if eligibility["category"] == "off_topic_condition":
                    effective_score = "low"
                elif eligibility["category"] == "methodology_only":
                    effective_score = "medium" if raw_score == "high" else "low"
                if (
                    mcount >= 2
                    and raw_score == "low"
                    and eligibility["category"] == "neutral"
                ):
                    effective_score = "medium"
                scored.append((paper, effective_score, mcount, eligibility["boost"]))

            # Sort: high first, then medium, then low; tiebreak by
            # evidence signal + match_count desc, then by stable order.
            priority = {"high": 0, "medium": 1, "low": 2}
            scored.sort(
                key=lambda t: (priority.get(t[1], 9), -t[3], -t[2]),
            )

            high_picks = [(p, s) for p, s, _, _ in scored if s == "high"]
            medium_picks = [(p, s) for p, s, _, _ in scored if s == "medium"]
            candidate_pool = [p for p, _ in high_picks] + [p for p, _ in medium_picks]

            await _update_progress({
                "phase": "filtering",
                "kept": min(target_count, len(candidate_pool)),
                "percent": 65,
            })

            # ── Phase 4: Auto-save top N papers ───────────────────────────
            await _update_progress({
                "phase": "saving",
                "saved": 0,
                "skipped": 0,
                "total": target_count,
                "current_paper": "",
                "percent": 70,
            })

            saved_count = 0
            skipped_count = 0
            saved_paper_dicts: list[dict] = []

            for idx, paper in enumerate(candidate_pool):
                if saved_count >= target_count:
                    break

                if (
                    not scoring_exceeded_timeout
                    and monotonic() - start_wall > timeout_seconds
                ):
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
                        bg_db, user, project_id, req, wait_for_ingestion=True
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

                percent = 70 + int(25 * min(1.0, (saved_count + skipped_count) / max(1, target_count)))
                await _update_progress({
                    "phase": "saving",
                    "saved": saved_count,
                    "skipped": skipped_count,
                    "total": target_count,
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
                "queries_used": list(queries),
                "queries_count": len(queries),
                "candidates_after_dedupe": len(deduped),
                "candidates_scored": len(candidates_to_score),
                "eligibility_signals": eligibility_signals,
                "multi_match_papers": sum(
                    1 for c in match_counts.values() if c > 1
                ),
                "saved_paper_ids": [
                    p.get("semantic_scholar_id") or p.get("doi") or p.get("arxiv_id") or p.get("title")
                    for p in saved_paper_dicts
                ],
            }
            job.progress_json = {
                "phase": "done",
                "saved": saved_count,
                "skipped": skipped_count,
                "total": target_count,
                "queries_used": len(queries),
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
    topic: str,
    research_question: str,
    update_progress,
    timeout_seconds: int,
    start_wall: float,
) -> list[str]:
    """Score papers in batches of 25 using the LLM.

    Returns a list of scores (high/medium/low) in the same order as ``papers``.
    Failed batches fall back to "medium" (don't lose papers entirely).
    """
    if not papers:
        return []

    provider = get_provider()
    batch_size = 25
    batches = [papers[i : i + batch_size] for i in range(0, len(papers), batch_size)]
    all_scores: list[str] = ["medium"] * len(papers)
    batches_total = len(batches)

    for batch_idx, batch in enumerate(batches):
        if monotonic() - start_wall > timeout_seconds:
            break

        papers_json = _papers_to_scoring_json(batch)
        user_msg = AUTO_SEARCH_SCREEN_USER.format(
            topic=topic,
            research_question=research_question,
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


def _auto_search_timeout_seconds(target_count: int) -> int:
    """Return a wall-clock budget that scales with the requested corpus size."""
    if target_count <= 25:
        return 300
    if target_count <= 50:
        return 600
    return 900


def _auto_search_score_candidate_limit(target_count: int) -> int:
    """Bound LLM scoring work while keeping enough candidates for fallback."""
    return min(_MAX_AUTO_SEARCH_SCORE_CANDIDATES, max(target_count * 3, target_count + 50))


def _canonical_paper_key(paper) -> str:
    """Return the strongest stable identifier for a raw paper-like object."""
    return (
        paper.semantic_scholar_id
        or paper.arxiv_id
        or paper.doi
        or (paper.title or "").lower().strip()
        or f"_unknown_{id(paper)}"
    )


def _rank_auto_search_candidates(
    papers: list,
    match_counts: dict[str, int],
    queries: list[str],
    limit: int,
) -> list:
    """Pre-rank candidates before expensive LLM scoring.

    Auto-search can retrieve hundreds of candidates across multiple queries.
    Scoring all of them is slow and was the cause of 50-paper jobs timing out.
    This keeps the LLM focused on candidates with obvious eligibility signals,
    then multi-query agreement, citation count, and recency.
    """
    category_rank = {
        "clinical_or_domain_evidence": 0,
        "neutral": 1,
        "methodology_only": 2,
        "off_topic_condition": 3,
    }

    def sort_key(paper) -> tuple[int, int, int, int, int]:
        signal = _score_auto_search_eligibility(paper, queries)
        key = _canonical_paper_key(paper)
        # Note: arXiv API does not return citation counts, so we rely more on
        # exact topic match, review/domain boosts, multi-query matches, and year.
        return (
            category_rank[signal["category"]],
            -signal["boost"],
            -match_counts.get(key, 1),
            -(getattr(paper, "year", None) or 0),
        )

    return sorted(papers, key=sort_key)[:limit]


_CANCER_TERMS = (
    "cancer", "oncolog", "tumor", "tumour", "neoplasm", "carcinoma",
    "sarcoma", "melanoma", "leukemia", "leukaemia", "lymphoma", "myeloma",
    "glioblastoma", "astrocytoma", "glioma", "malignan", "breast cancer",
    "lung cancer", "colorectal", "nsclc",
)

_CLINICAL_EVIDENCE_TERMS = (
    "clinical trial", "randomized", "randomised", "cohort", "case-control",
    "observational", "patients with", "survival", "overall survival",
    "progression-free", "response rate", "adverse event", "toxicity",
    "safety", "tumor volume", "tumour volume", "cell viability",
    "xenograft", "in vivo", "in vitro", "phase 1", "phase 2",
    "phase i", "phase ii", "advanced solid tumors", "refractory",
)

_OUTCOME_TERMS = (
    "survival", "overall survival", "progression-free", "response rate",
    "adverse event", "toxicity", "safety", "tumor volume", "tumour volume",
    "cell viability",
)

_INTERVENTION_TERMS = (
    "immunotherapy", "car-t", "car t", "checkpoint inhibitor", "pd-1",
    "pd-l1", "ctla-4", "radiotherapy", "photodynamic", "oncolytic",
    "virotherapy", "ablation", "targeted therapy", "biomarker",
    "natural compound", "herbal", "non-chemotherapeutic",
)

_METHODOLOGY_ONLY_TERMS = (
    "statistical method", "statistical methodology", "trial design",
    "study design", "matched-pair", "matched pair", "covariate adjustment",
    "estimand", "sample size", "power calculation", "simulation study",
    "monte carlo", "randomization procedure", "randomisation procedure",
    "mathematical model", "mathematical modelling", "mathematical modeling",
    "computational model", "travelling waves", "phenotype-structured",
)


def _paper_text(paper) -> str:
    """Return searchable lowercase metadata text for an auto-search candidate."""
    source_specific = getattr(paper, "source_specific", None) or {}
    fields = source_specific.get("fields_of_study") or []
    if isinstance(fields, list):
        fields_text = " ".join(str(field) for field in fields)
    else:
        fields_text = str(fields)
    parts = [
        getattr(paper, "title", "") or "",
        getattr(paper, "abstract", "") or "",
        getattr(paper, "venue", "") or "",
        fields_text,
    ]
    return " ".join(parts).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


class _EligibilitySignal(TypedDict):
    category: Literal[
        "off_topic_condition",
        "methodology_only",
        "clinical_or_domain_evidence",
        "neutral",
    ]
    boost: int


def _score_auto_search_eligibility(paper, queries: list[str]) -> _EligibilitySignal:
    """Classify whether a search candidate satisfies obvious topic constraints.

    This is a deterministic guardrail layered after LLM scoring. It mirrors the
    systematic-review workflow: search broadly, then screen titles/abstracts
    against eligibility criteria before saving papers to the corpus.
    """
    query_text = " ".join(queries).lower()
    paper_text = _paper_text(paper)
    requires_cancer = _contains_any(query_text, _CANCER_TERMS)
    has_cancer = _contains_any(paper_text, _CANCER_TERMS)
    has_methodology = _contains_any(paper_text, _METHODOLOGY_ONLY_TERMS)
    has_evidence = _contains_any(paper_text, _CLINICAL_EVIDENCE_TERMS)
    has_intervention = _contains_any(paper_text, _INTERVENTION_TERMS)
    has_outcomes = _contains_any(paper_text, _OUTCOME_TERMS)

    if requires_cancer and not (has_cancer or has_intervention):
        return {"category": "off_topic_condition", "boost": 0}
    if has_methodology and not has_outcomes:
        return {"category": "methodology_only", "boost": 0}
    if has_evidence or has_intervention:
        return {"category": "clinical_or_domain_evidence", "boost": 1}
    return {"category": "neutral", "boost": 0}


def _deduplicate_with_match_counts(
    papers: list,
) -> tuple[list, dict[str, int]]:
    """Deduplicate a list of RawPaper objects by strongest identifier AND
    return how many times each canonical paper was matched across queries.

    Returns:
        (unique_papers, match_counts) where ``match_counts[key]`` is the
        number of times a paper with that canonical key appeared in the
        input list. A ``match_count > 1`` means the paper was found by more
        than one query — a strong relevance signal (the paper's topic is
        robust to phrasing).

    Order: preserves first-seen order, which keeps the original ranking
    stability for downstream scoring.
    """
    seen_order: list[str] = []
    seen_set: set[str] = set()
    match_counts: dict[str, int] = {}
    unique: list = []

    for p in papers:
        key = _canonical_paper_key(p)
        match_counts[key] = match_counts.get(key, 0) + 1
        if key in seen_set:
            continue
        seen_set.add(key)
        seen_order.append(key)
        unique.append(p)

    return unique, match_counts
