"""REST endpoints for report generation and export."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import Project, User
from app.db.session import get_db
from app.schemas.reports import (
    CitationAuditResponse,
    CreateReportRequest,
    ReferenceResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportResponse,
)
from app.services.report_generation import (
    generate_report,
    get_report_by_id,
    get_reports_by_project,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


@router.post("/{project_id}/reports")
async def create_report(
    project_id: str,
    request: CreateReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start report generation as a background job. Returns job info immediately."""
    import asyncio

    from sqlalchemy import func, select

    from app.db.models import BackgroundJob, LiteratureMatrixRow

    pid = uuid.UUID(project_id)

    # Verify ownership
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check matrix rows exist
    matrix_count = (
        await db.execute(
            select(func.count())
            .select_from(LiteratureMatrixRow)
            .where(LiteratureMatrixRow.project_id == pid)
        )
    ).scalar()
    if not matrix_count:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No matrix rows. Generate a literature matrix first.",
        )

    # Parse selected gap IDs
    gap_ids = None
    if request.selected_gap_ids:
        try:
            gap_ids = [uuid.UUID(gid) for gid in request.selected_gap_ids]
        except ValueError as err:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid gap ID format",
            ) from err

    # Create a background job record
    job = BackgroundJob(
        job_type="report_generate",
        project_id=pid,
        user_id=user.id,
        status="pending",
        total=1,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background task
    asyncio.ensure_future(
        _run_report_job(
            job.id,
            pid,
            user.id,
            project.topic,
            project.research_question,
            request.title,
            request.include_gap_section,
            gap_ids,
        )
    )

    return {"job_id": str(job.id), "status": "running"}


async def _run_report_job(
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    topic: str,
    research_question: str | None,
    title: str | None,
    include_gap_section: bool,
    selected_gap_ids: list[uuid.UUID] | None,
) -> None:
    """Background worker: run report generation."""
    from datetime import UTC, datetime

    from app.db.session import async_session_factory

    async with async_session_factory() as bg_db:
        job = None
        try:
            from sqlalchemy import select as sa_select

            from app.db.models import BackgroundJob

            job_result = await bg_db.execute(
                sa_select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            await bg_db.commit()

            result = await generate_report(
                db=bg_db,
                project_id=project_id,
                user_id=user_id,
                topic=topic,
                research_question=research_question,
                title=title,
                include_gap_section=include_gap_section,
                selected_gap_ids=selected_gap_ids,
            )

            if result.get("status") == "failed":
                job.status = "failed"
                job.error_message = result.get("error", "Report generation failed")
            else:
                job.status = "completed"
                job.result = {
                    "report_id": result.get("id"),
                    "validation_status": result.get("validation_status"),
                    "total_citations": result.get("citation_audit", {}).get("total_citations", 0),
                }
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background report job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass


@router.get("/{project_id}/reports", response_model=ReportListResponse)
async def list_reports(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportListResponse:
    """List reports for a project."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    reports = await get_reports_by_project(db, pid)

    items = []
    for r in reports:
        total = len(r.citations)
        items.append(
            ReportResponse(
                id=str(r.id),
                title=r.title,
                validation_status=r.validation_status,
                content_markdown=r.content_markdown,
                references=[],
                citation_audit=CitationAuditResponse(
                    total_citations=total,
                    invalid_citations=0 if r.validation_status == "valid" else -1,
                    valid_citations=total if r.validation_status == "valid" else 0,
                    uncited_saved_papers=0,
                ),
            )
        )

    return ReportListResponse(items=items, total=len(items))


@router.get("/{project_id}/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportDetailResponse:
    """Get a report with references and citation audit."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)
    rid = uuid.UUID(report_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    report = await get_report_by_id(db, pid, rid)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Report not found")

    from app.services.report_generation import _build_references

    cited_ids = {c.project_paper_id for c in report.citations}
    references = await _build_references(db, cited_ids)

    total = len(report.citations)
    return ReportDetailResponse(
        id=str(report.id),
        title=report.title,
        validation_status=report.validation_status,
        content_markdown=report.content_markdown,
        references=[ReferenceResponse(**ref) for ref in references],
        citation_audit=CitationAuditResponse(
            total_citations=total,
            invalid_citations=0 if report.validation_status == "valid" else total,
            valid_citations=total if report.validation_status == "valid" else 0,
            uncited_saved_papers=0,
        ),
        created_at=str(report.created_at),
    )


@router.get("/{project_id}/reports/{report_id}/export")
async def export_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Export a report as Markdown."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)
    rid = uuid.UUID(report_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    report = await get_report_by_id(db, pid, rid)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Report not found")

    return {
        "title": report.title,
        "format": "markdown",
        "content": report.content_markdown,
    }
