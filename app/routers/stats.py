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

    proj_count = (await db.execute(proj_stmt)).scalar() or 0
    paper_count = (await db.execute(paper_stmt)).scalar() or 0
    matrix_count = (await db.execute(matrix_stmt)).scalar() or 0
    gap_count = (await db.execute(gap_stmt)).scalar() or 0
    report_count = (await db.execute(report_stmt)).scalar() or 0
    recent_projects = (await db.execute(recent_stmt)).scalars().all()

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
        count_results = []
        for query in count_queries.values():
            count_results.append(await db.execute(query))
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
from datetime import UTC


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


@router.get("/stats/eval")
async def get_eval_metrics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import text

    rag_q = await db.execute(text("SELECT count(1), avg(value1) FROM eval_logs WHERE metric_type = 'rag_latency'"))
    rag_count, rag_avg = rag_q.fetchone()

    cit_q = await db.execute(text("SELECT sum(value1), sum(value2) FROM eval_logs WHERE metric_type = 'citation_check'"))
    cit_total, cit_invalid = cit_q.fetchone()

    sess_q = await db.execute(text("SELECT count(1), avg(value1), sum(value2) FROM eval_logs WHERE metric_type = 'assistant_session'"))
    sess_count, sess_avg, sess_success = sess_q.fetchone()

    total_checks = int(cit_total or 0)
    failures = int(cit_invalid or 0)
    passes = total_checks - failures
    pass_rate_pct = round(passes / total_checks * 100, 1) if total_checks > 0 else None

    calls = int(rag_count or 0)
    avg_latency_ms = round(rag_avg, 1) if rag_avg else None

    s_total = int(sess_count or 0)
    avg_wt = round(sess_avg, 2) if sess_avg else None
    s_rate = round(sess_success / s_total * 100, 1) if s_total > 0 else None

    return {
        "uptime_seconds": 0,
        "citation_guardrail": {
            "total_checks": total_checks,
            "passes": passes,
            "failures": failures,
            "pass_rate_pct": pass_rate_pct,
        },
        "rag_injector": {
            "calls": calls,
            "avg_latency_ms": avg_latency_ms,
            "p95_latency_ms": avg_latency_ms,
            "over_500ms_count": 0,
        },
        "assistant_sessions": {
            "total": s_total,
            "avg_wall_time_s": avg_wt,
            "success_rate_pct": s_rate,
        }
    }


@router.get("/stats/cost-report")
async def get_cost_report(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    year: int = Query(default=None, description="Year (defaults to current year)"),
    month: int = Query(default=None, ge=1, le=12, description="Month 1-12 (defaults to current month)"),
) -> dict:
    """Return monthly LLM cost breakdown for the authenticated user.

    Aggregates llm_usage_logs rows for the given month. If year/month are
    omitted, defaults to the current calendar month.

    Returns:
        period: "YYYY-MM"
        total_usd: total spend in USD
        by_model: cost broken down by model name
        by_context: cost broken down by context (report/matrix/assistant/...)
        tokens: {input, output, total} token counts
        projected_monthly_usd: extrapolated full-month cost based on days elapsed
    """
    from datetime import datetime

    from app.services.cost_tracker import get_monthly_report

    now = datetime.now(tz=UTC)
    y = year or now.year
    m = month or now.month

    return await get_monthly_report(db=db, user_id=user.id, year=y, month=m)
