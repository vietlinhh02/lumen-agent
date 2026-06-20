"""REST endpoints for dashboard stats."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import (
    ConflictingFinding,
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
    paper_stmt = (
        select(func.count())
        .select_from(ProjectPaper)
        .join(Project, Project.id == ProjectPaper.project_id)
        .where(Project.owner_id == user.id, ProjectPaper.status == "saved")
    )
    matrix_stmt = (
        select(func.count())
        .select_from(LiteratureMatrixRow)
        .join(Project, Project.id == LiteratureMatrixRow.project_id)
        .where(Project.owner_id == user.id)
    )
    gap_stmt = (
        select(func.count())
        .select_from(ResearchGap)
        .join(Project, Project.id == ResearchGap.project_id)
        .where(Project.owner_id == user.id)
    )
    report_stmt = (
        select(func.count()).select_from(ReviewReport).where(ReviewReport.created_by == user.id)
    )
    recent_stmt = (
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(8)
    )

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
    recent_project_ids = [project.id for project in recent_projects]

    workflow_counts: dict[str, dict[str, int]] = {}
    if recent_project_ids:
        count_queries = {
            "paper_count": (
                select(ProjectPaper.project_id, func.count(ProjectPaper.id))
                .where(
                    ProjectPaper.project_id.in_(recent_project_ids),
                    ProjectPaper.status == "saved",
                )
                .group_by(ProjectPaper.project_id)
            ),
            "full_text_count": (
                select(ProjectPaper.project_id, func.count(ProjectPaper.id))
                .where(
                    ProjectPaper.project_id.in_(recent_project_ids),
                    ProjectPaper.status == "saved",
                    ProjectPaper.full_text_status.in_(("completed", "raw_extracted")),
                )
                .group_by(ProjectPaper.project_id)
            ),
            "raw_text_count": (
                select(ProjectPaper.project_id, func.count(ProjectPaper.id))
                .where(
                    ProjectPaper.project_id.in_(recent_project_ids),
                    ProjectPaper.status == "saved",
                    ProjectPaper.full_text_status == "raw_extracted",
                )
                .group_by(ProjectPaper.project_id)
            ),
            "matrix_count": (
                select(LiteratureMatrixRow.project_id, func.count(LiteratureMatrixRow.id))
                .where(LiteratureMatrixRow.project_id.in_(recent_project_ids))
                .group_by(LiteratureMatrixRow.project_id)
            ),
            "gap_count": (
                select(ResearchGap.project_id, func.count(ResearchGap.id))
                .where(ResearchGap.project_id.in_(recent_project_ids))
                .group_by(ResearchGap.project_id)
            ),
            "conflict_count": (
                select(ConflictingFinding.project_id, func.count(ConflictingFinding.id))
                .where(ConflictingFinding.project_id.in_(recent_project_ids))
                .group_by(ConflictingFinding.project_id)
            ),
            "report_count": (
                select(ReviewReport.project_id, func.count(ReviewReport.id))
                .where(
                    ReviewReport.project_id.in_(recent_project_ids),
                    ReviewReport.created_by == user.id,
                )
                .group_by(ReviewReport.project_id)
            ),
        }
        count_results = await asyncio.gather(
            *(db.execute(query) for query in count_queries.values())
        )
        for key, result in zip(count_queries, count_results, strict=True):
            for project_id, count in result.all():
                workflow_counts.setdefault(str(project_id), {})[key] = count

    project_workflows = []
    for project in recent_projects:
        counts = workflow_counts.get(str(project.id), {})
        project_workflows.append(
            {
                "id": str(project.id),
                "title": project.title,
                "topic": project.topic,
                "status": project.status,
                "updated_at": str(project.updated_at),
                "paper_count": counts.get("paper_count", 0),
                "full_text_count": counts.get("full_text_count", 0),
                "raw_text_count": counts.get("raw_text_count", 0),
                "matrix_count": counts.get("matrix_count", 0),
                "gap_count": counts.get("gap_count", 0),
                "conflict_count": counts.get("conflict_count", 0),
                "report_count": counts.get("report_count", 0),
            }
        )

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
        "project_workflows": project_workflows,
    }


from fastapi import Query
from sqlalchemy import String, cast, or_


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
