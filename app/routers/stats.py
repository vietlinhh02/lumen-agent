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

    # Projects
    proj_count = (
        await db.execute(
            select(func.count()).select_from(Project).where(Project.owner_id == user.id)
        )
    ).scalar() or 0

    # Papers saved across all projects
    paper_count = (
        await db.execute(
            select(func.count())
            .select_from(ProjectPaper)
            .join(Project, Project.id == ProjectPaper.project_id)
            .where(Project.owner_id == user.id, ProjectPaper.status == "saved")
        )
    ).scalar() or 0

    # Matrix rows
    matrix_count = (
        await db.execute(
            select(func.count())
            .select_from(LiteratureMatrixRow)
            .join(Project, Project.id == LiteratureMatrixRow.project_id)
            .where(Project.owner_id == user.id)
        )
    ).scalar() or 0

    # Gaps
    gap_count = (
        await db.execute(
            select(func.count())
            .select_from(ResearchGap)
            .join(Project, Project.id == ResearchGap.project_id)
            .where(Project.owner_id == user.id)
        )
    ).scalar() or 0

    # Reports
    report_count = (
        await db.execute(
            select(func.count()).select_from(ReviewReport).where(ReviewReport.created_by == user.id)
        )
    ).scalar() or 0

    # Recent projects (last 5)
    recent_stmt = (
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(5)
    )
    recent_projects = (await db.execute(recent_stmt)).scalars().all()

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


@router.get("/papers/all")
async def list_all_papers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """List all saved papers across all projects for the current user."""
    stmt = (
        select(ProjectPaper, Paper, Project)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .join(Project, Project.id == ProjectPaper.project_id)
        .where(
            Project.owner_id == user.id,
            ProjectPaper.status == "saved",
        )
        .order_by(ProjectPaper.saved_at.desc())
    )
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

    return {"items": items, "total": len(items)}
