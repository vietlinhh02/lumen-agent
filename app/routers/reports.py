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


@router.post("/{project_id}/reports", response_model=ReportResponse)
async def create_report(
    project_id: str,
    request: CreateReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportResponse:
    """Generate a citation-safe literature review."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)

    # Verify ownership
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

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

    result = await generate_report(
        db=db,
        project_id=pid,
        user_id=user.id,
        topic=project.topic,
        research_question=project.research_question,
        title=request.title,
        include_gap_section=request.include_gap_section,
        selected_gap_ids=gap_ids,
    )

    if result.get("status") == "failed":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Report generation failed"),
        )

    return ReportResponse(**result)


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
