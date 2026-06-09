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
) -> SearchRun:
    run = SearchRun(
        project_id=project_id,
        user_query=query,
        total_results=total_found,
        results_json=results,
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
    """Return which papers (by identifier) are already saved to the project."""
    saved = []
    for p in paper_dicts:
        sid = p.get("semantic_scholar_id")
        doi = p.get("doi")
        arxiv = p.get("arxiv_id")
        if sid:
            result = await db.execute(select(Paper).where(Paper.semantic_scholar_id == sid))
            paper = result.scalar_one_or_none()
            if paper:
                existing = await db.execute(
                    select(ProjectPaper).where(
                        ProjectPaper.project_id == project_id,
                        ProjectPaper.paper_id == paper.id,
                    )
                )
                if existing.scalar_one_or_none():
                    saved.append(sid)
                    continue
        if doi:
            result = await db.execute(select(Paper).where(Paper.doi == doi))
            paper = result.scalar_one_or_none()
            if paper:
                existing = await db.execute(
                    select(ProjectPaper).where(
                        ProjectPaper.project_id == project_id,
                        ProjectPaper.paper_id == paper.id,
                    )
                )
                if existing.scalar_one_or_none():
                    saved.append(doi)
                    continue
        if arxiv:
            result = await db.execute(select(Paper).where(Paper.arxiv_id == arxiv))
            paper = result.scalar_one_or_none()
            if paper:
                existing = await db.execute(
                    select(ProjectPaper).where(
                        ProjectPaper.project_id == project_id,
                        ProjectPaper.paper_id == paper.id,
                    )
                )
                if existing.scalar_one_or_none():
                    saved.append(arxiv)
                    continue
    return saved


async def auto_save_high_papers(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    session_id: UUID,
) -> dict:
    result = await db.execute(
        select(SearchRun).where(
            SearchRun.id == session_id,
            SearchRun.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        return {"saved": 0, "skipped": 0, "error": "Session not found"}

    scores = run.screening_scores or []
    results = run.results_json or []

    if not scores:
        return {"saved": 0, "skipped": len(results), "error": "No screening scores available"}

    saved = 0
    skipped = 0

    for i, paper_dict in enumerate(results):
        score = scores[i] if i < len(scores) else "medium"
        if score != "high":
            skipped += 1
            continue

        try:
            # Map search-result dict to SavePaperRequest
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
            save_result = await save_paper_to_project(db, user, project_id, req)
            if save_result is None:
                skipped += 1
                continue
            saved += 1
        except Exception as exc:
            logger.warning("Failed to auto-save paper %s: %s", paper_dict.get("title", "?"), exc)
            skipped += 1

    return {"saved": saved, "skipped": skipped}
