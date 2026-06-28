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
    
    # 1. Global counts in a single round-trip
    global_counts_stmt = select(
        select(func.count()).select_from(Project).where(Project.owner_id == user.id).scalar_subquery().label("proj_count"),
        select(func.count()).select_from(ProjectPaper).join(Project, Project.id == ProjectPaper.project_id).where(Project.owner_id == user.id, ProjectPaper.status == "saved").scalar_subquery().label("paper_count"),
        select(func.count()).select_from(LiteratureMatrixRow).join(Project, Project.id == LiteratureMatrixRow.project_id).where(Project.owner_id == user.id).scalar_subquery().label("matrix_count"),
        select(func.count()).select_from(ResearchGap).join(Project, Project.id == ResearchGap.project_id).where(Project.owner_id == user.id).scalar_subquery().label("gap_count"),
        select(func.count()).select_from(ReviewReport).where(ReviewReport.created_by == user.id).scalar_subquery().label("report_count"),
    )
    
    global_row = (await db.execute(global_counts_stmt)).first()
    proj_count = getattr(global_row, "proj_count", 0) or 0
    paper_count = getattr(global_row, "paper_count", 0) or 0
    matrix_count = getattr(global_row, "matrix_count", 0) or 0
    gap_count = getattr(global_row, "gap_count", 0) or 0
    report_count = getattr(global_row, "report_count", 0) or 0
    
    recent_stmt = (
        select(Project)
        .where(Project.owner_id == user.id)
        .order_by(Project.updated_at.desc())
        .limit(8)
    )
    recent_projects = (await db.execute(recent_stmt)).scalars().all()
    
    workflow_counts: dict[str, dict[str, int]] = {}
    recent_project_ids = [project.id for project in recent_projects]

    if recent_project_ids:
        # Combine all per-project counts into a single UNION ALL query to save round-trips
        from sqlalchemy import text
        
        # Build raw sql for union all because SQLAlchemy's union of grouped selects can be tricky
        p_ids = [f"'{pid}'" for pid in recent_project_ids]
        p_ids_str = ",".join(p_ids)
        
        union_sql = f"""
        SELECT 'paper_count' as type, project_id, count(*) as cnt FROM project_papers WHERE project_id IN ({p_ids_str}) AND status = 'saved' GROUP BY project_id
        UNION ALL
        SELECT 'full_text_count' as type, project_id, count(*) as cnt FROM project_papers WHERE project_id IN ({p_ids_str}) AND status = 'saved' AND full_text_status IN ('completed', 'raw_extracted') GROUP BY project_id
        UNION ALL
        SELECT 'raw_text_count' as type, project_id, count(*) as cnt FROM project_papers WHERE project_id IN ({p_ids_str}) AND status = 'saved' AND full_text_status = 'raw_extracted' GROUP BY project_id
        UNION ALL
        SELECT 'matrix_count' as type, project_id, count(*) as cnt FROM literature_matrix_rows WHERE project_id IN ({p_ids_str}) GROUP BY project_id
        UNION ALL
        SELECT 'gap_count' as type, project_id, count(*) as cnt FROM research_gaps WHERE project_id IN ({p_ids_str}) GROUP BY project_id
        UNION ALL
        SELECT 'conflict_count' as type, project_id, count(*) as cnt FROM conflicting_findings WHERE project_id IN ({p_ids_str}) GROUP BY project_id
        UNION ALL
        SELECT 'report_count' as type, project_id, count(*) as cnt FROM review_reports WHERE project_id IN ({p_ids_str}) AND created_by = '{user.id}' GROUP BY project_id
        """
        
        results = await db.execute(text(union_sql))
        for row in results:
            type_key, pid, count = row
            workflow_counts.setdefault(str(pid), {})[type_key] = count

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
