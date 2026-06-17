"""REST endpoints for search sessions.

``POST /api/papers/search/sessions``              — create search session with results
``GET  /api/papers/search/sessions``              — list sessions for a project
``GET  /api/papers/search/sessions/{id}``        — get session with paginated results
``POST /api/papers/search/sessions/{id}/screen`` — AI screen papers in session
``POST /api/papers/search/sessions/{id}/auto-save`` — auto-save high-relevance papers
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import PAPER_SCREEN_SYSTEM, PAPER_SCREEN_USER
from app.ai.provider import get_provider
from app.core.security import get_current_user
from app.db.models import Paper, ProjectPaper, User
from app.db.session import get_db
from app.routers.paper import _parse_screening_scores
from app.schemas.paper import (
    ScreenPapersResponse,
)
from app.services.search_session import (
    auto_save_high_papers,
    get_saved_paper_ids,
    get_search_session,
    list_search_sessions,
    save_screening_scores,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search sessions"])


# ── Schemas ──────────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    project_id: UUID
    query: str = Field(..., min_length=2, max_length=500)
    limit: int = Field(default=100, ge=1, le=500)


class SessionListItem(BaseModel):
    id: UUID
    project_id: UUID
    user_query: str
    total_results: int
    created_at: str
    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]


class SessionDetailResponse(BaseModel):
    id: UUID
    project_id: UUID
    user_query: str
    total_results: int
    screening_scores: list[str]
    created_at: str
    page: int
    page_size: int
    total_pages: int
    papers: list[dict]
    saved_paper_ids: list[str] = []
    detected_language: str | None = None
    query_variants: list[dict] = []
    language_bias_audit: dict | None = None
    source_diagnostics: list[dict] = []


# ── Routes ───────────────────────────────────────────────────────────────


@router.post("/search/sessions", status_code=http_status.HTTP_202_ACCEPTED)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start a search in the background.

    Returns ``{job_id, session_id, status}`` immediately.
    The frontend polls ``GET /api/papers/search/jobs/{job_id}`` for completion,
    then loads the session detail via ``GET /api/papers/search/sessions/{session_id}``.
    """
    from app.services.search_session import start_search_job

    result = await start_search_job(
        db,
        user,
        request.project_id,
        request.query,
        request.limit,
    )
    return result


@router.get("/search/sessions")
async def list_sessions(
    project_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionListResponse:
    runs = await list_search_sessions(db, user, project_id)
    items = [
        SessionListItem(
            id=r.id,
            project_id=r.project_id,
            user_query=r.user_query,
            total_results=r.total_results,
            created_at=str(r.created_at),
        )
        for r in runs
    ]
    return SessionListResponse(sessions=items)


@router.get("/search/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionDetailResponse:
    run = await get_search_session(db, user, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Session not found")

    results = run.results_json or []
    scores = run.screening_scores or []
    page_size = 20
    total = len(results)
    total_pages = max(1, (total + page_size - 1) // page_size)

    start = (page - 1) * page_size
    page_result = results[start : start + page_size]
    saved_ids = await get_saved_paper_ids(db, run.project_id, page_result)

    return SessionDetailResponse(
        id=run.id,
        project_id=run.project_id,
        user_query=run.user_query,
        total_results=run.total_results,
        screening_scores=scores,
        created_at=str(run.created_at),
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        papers=page_result,
        saved_paper_ids=saved_ids,
        detected_language=run.detected_language,
        query_variants=run.query_variants or [],
        language_bias_audit=run.language_bias_audit,
        source_diagnostics=run.source_diagnostics or [],
    )


@router.post("/search/sessions/{session_id}/screen")
async def screen_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenPapersResponse:
    run = await get_search_session(db, user, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Session not found")

    results = run.results_json or []
    if not results:
        return ScreenPapersResponse(scores=[])

    provider = get_provider()

    paper_list = "\n\n".join(
        f"[{i}] {p.get('title', 'Untitled')}\nAbstract: {p.get('abstract') or 'N/A'}"
        for i, p in enumerate(results)
    )

    user_msg = PAPER_SCREEN_USER.format(
        topic=run.user_query,
        research_question="Not specified",
        paper_list=paper_list,
    )

    try:
        raw_text = await provider.complete(
            messages=[{"role": "user", "content": user_msg}],
            system=PAPER_SCREEN_SYSTEM,
            max_tokens=500,
        )
        scores = _parse_screening_scores(raw_text, len(results))
    except Exception as exc:
        logger.exception("Session screening failed for %s", session_id)
        raise HTTPException(status_code=502, detail=f"Screening failed: {exc}") from exc

    await save_screening_scores(db, session_id, scores)
    return ScreenPapersResponse(scores=scores)


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


class UnsavePaperBody(BaseModel):
    semantic_scholar_id: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None


@router.delete("/search/sessions/{session_id}/unsave")
async def unsave_paper(
    session_id: UUID,
    body: UnsavePaperBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = await get_search_session(db, user, session_id)
    if not run:
        raise HTTPException(status_code=404, detail="Session not found")

    paper = None
    if body.semantic_scholar_id:
        r = await db.execute(
            select(Paper).where(Paper.semantic_scholar_id == body.semantic_scholar_id)
        )
        paper = r.scalar_one_or_none()
    if not paper and body.doi:
        r = await db.execute(select(Paper).where(Paper.doi == body.doi))
        paper = r.scalar_one_or_none()
    if not paper and body.arxiv_id:
        r = await db.execute(select(Paper).where(Paper.arxiv_id == body.arxiv_id))
        paper = r.scalar_one_or_none()

    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    r = await db.execute(
        select(ProjectPaper).where(
            ProjectPaper.project_id == run.project_id,
            ProjectPaper.paper_id == paper.id,
        )
    )
    pp = r.scalar_one_or_none()
    if not pp:
        raise HTTPException(status_code=404, detail="Paper not in project")

    await db.delete(pp)
    await db.commit()
    return {"ok": True}
