"""REST endpoints for dashboard stats."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import (
    LiteratureMatrixRow,
    Paper,
    Project,
    ProjectPaper,
    ResearchGap,
    ReviewReport,
    User,
)
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return dashboard stats for the current user."""
    import asyncio

    proj_stmt = select(func.count()).select_from(Project).where(Project.owner_id == user.id)
    paper_stmt = select(func.count()).select_from(ProjectPaper).join(Project, Project.id == ProjectPaper.project_id).where(Project.owner_id == user.id, ProjectPaper.status == "saved")
    matrix_stmt = select(func.count()).select_from(LiteratureMatrixRow).join(Project, Project.id == LiteratureMatrixRow.project_id).where(Project.owner_id == user.id)
    gap_stmt = select(func.count()).select_from(ResearchGap).join(Project, Project.id == ResearchGap.project_id).where(Project.owner_id == user.id)
    report_stmt = select(func.count()).select_from(ReviewReport).where(ReviewReport.created_by == user.id)
    recent_stmt = select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc()).limit(5)

    results = await asyncio.gather(
        db.execute(proj_stmt),
        db.execute(paper_stmt),
        db.execute(matrix_stmt),
        db.execute(gap_stmt),
        db.execute(report_stmt),
        db.execute(recent_stmt),
    )

    proj_count = results[0].scalar() or 0
    paper_count = results[1].scalar() or 0
    matrix_count = results[2].scalar() or 0
    gap_count = results[3].scalar() or 0
    report_count = results[4].scalar() or 0
    recent_projects = results[5].scalars().all()

    return {
        "project_count": proj_count,
        "paper_count": paper_count,
        "matrix_count": matrix_count,
        "gap_count": gap_count,
        "report_count": report_count,
        "recent_projects": [
            {
                "id": str(p.id),
                "title": p.title,
                "status": p.status,
                "updated_at": str(p.updated_at),
            }
            for p in recent_projects
        ],
    }


from fastapi import Query
from sqlalchemy import or_, String, cast

@router.get("/papers/all")
async def list_all_papers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(500, le=1000),
    offset: int = 0,
    search: str | None = None,
    project_id: str | None = None,
    sort_key: str = "saved_at",
    sort_asc: bool = False,
) -> dict:
    """List all saved papers across all projects for the current user with pagination and sorting."""
    stmt = (
        select(ProjectPaper, Paper, Project)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .join(Project, Project.id == ProjectPaper.project_id)
        .where(
            Project.owner_id == user.id,
            ProjectPaper.status == "saved",
        )
    )

    if project_id:
        stmt = stmt.where(Project.id == project_id)

    if search:
        search_term = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Paper.title).like(search_term),
                func.lower(Paper.abstract).like(search_term),
                func.lower(Paper.venue).like(search_term),
                cast(Paper.authors, String).ilike(search_term),
            )
        )

    # Count total items matching criteria
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    # Sorting
    order_col = ProjectPaper.saved_at
    if sort_key == "title":
        order_col = Paper.title
    elif sort_key == "year":
        order_col = Paper.year
    elif sort_key == "citations":
        order_col = Paper.citation_count

    stmt = stmt.order_by(order_col.asc() if sort_asc else order_col.desc())
    
    # Pagination
    stmt = stmt.limit(limit).offset(offset)

    rows = (await db.execute(stmt)).all()

    items = []
    for pp, paper, project in rows:
        authors = []
        for a in paper.authors or []:
            if isinstance(a, dict):
                authors.append(a.get("name", str(a)))
            else:
                authors.append(str(a))

        items.append(
            {
                "id": str(pp.id),
                "paper_id": str(paper.id),
                "project_id": str(project.id),
                "project_title": project.title,
                "title": paper.title,
                "abstract": paper.abstract,
                "authors": authors,
                "year": paper.year,
                "venue": paper.venue,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "url": paper.url,
                "citation_count": paper.citation_count,
                "source_names": paper.source_names or [],
                "saved_at": str(pp.saved_at),
                "relevance_label": pp.relevance_label,
            }
        )

    return {"items": items, "total": total}
