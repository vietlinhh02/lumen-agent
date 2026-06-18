"""
Report tools for the Assistant.

Provides tools for generating, viewing, and exporting literature review reports.

Use these when:
- The user wants to generate a literature review report
- The user wants to see existing reports
- The user wants to export a report as markdown
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.tools import tool

from app.agents.assistant.tools.context import get_user, get_user_id

if TYPE_CHECKING:
    from uuid import UUID


def _ok_result(message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a success result dict."""
    result = {"ok": True, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _error_result(error_code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create an error result dict that the LLM can reason about."""
    result = {"ok": False, "error_code": error_code, "message": message}
    if details is not None:
        result["details"] = details
    return result


# ── Polling helper ──────────────────────────────────────────────────────────


async def _poll_job(
    job_id: "UUID",
    max_wait: float = 120.0,
    interval: float = 2.0,
) -> Dict[str, Any]:
    """
    Poll a background job until completion or failure.
    """
    from app.db.session import async_session_factory
    from sqlalchemy import select
    from app.db.models import BackgroundJob
    
    elapsed = 0.0
    async with async_session_factory() as db:
        while elapsed < max_wait:
            await asyncio.sleep(interval)
            elapsed += interval
            
            result = await db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return {"status": "failed", "error": "Job not found"}
            
            if job.status in ("completed", "failed"):
                return {
                    "status": job.status,
                    "result": job.result or {},
                    "error": job.error_message,
                }
    
    return {"status": "timeout", "error": f"Job did not complete within {max_wait}s"}


# ── Implementations ────────────────────────────────────────────────────────


async def _generate_report_impl(
    project_id: str,
    title: Optional[str],
    include_gap_section: bool,
    selected_gap_ids: Optional[List[str]],
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    Generate a literature review report for a project.
    
    Args:
        project_id: Project UUID string.
        title: Optional report title.
        include_gap_section: Whether to include research gaps section.
        selected_gap_ids: Specific gaps to include.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with report_id, validation_status, and citation counts.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import func, select
        from app.db.models import BackgroundJob, Project, LiteratureMatrixRow
        
        pid = PyUUID(project_id)
        
        # Parse gap IDs
        gap_ids = None
        if selected_gap_ids:
            try:
                gap_ids = [PyUUID(gid) for gid in selected_gap_ids]
            except ValueError:
                return _error_result("INVALID_GAP_ID", "Invalid gap ID format in selected_gap_ids")
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            project = project_result.scalar_one_or_none()
            if project is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Check matrix rows exist
            count_stmt = select(func.count()).select_from(LiteratureMatrixRow).where(
                LiteratureMatrixRow.project_id == pid
            )
            matrix_count = (await db.execute(count_stmt)).scalar() or 0
            if matrix_count == 0:
                return _error_result(
                    "NO_MATRIX",
                    "No matrix rows found. Generate a matrix first before creating a report."
                )
            
            # Create background job
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
        from app.routers.reports import _run_report_job
        asyncio.ensure_future(_run_report_job(
            job.id,
            pid,
            user.id,
            project.topic,
            project.research_question,
            title,
            include_gap_section,
            gap_ids,
        ))
        
        # Poll for completion
        poll_result = await _poll_job(job.id)
        
        result_data = poll_result.get("result", {})
        report_id = result_data.get("report_id", str(job.id))
        validation_status = result_data.get("validation_status", "unchecked")
        total_citations = result_data.get("total_citations", 0)
        invalid_citations = result_data.get("invalid_citations", 0)
        
        if poll_result["status"] == "completed":
            return _ok_result(
                f"Report generated successfully. Validation: {validation_status}.",
                {
                    "report_id": report_id,
                    "validation_status": validation_status,
                    "total_citations": total_citations,
                    "invalid_citations": invalid_citations,
                }
            )
        elif poll_result["status"] == "failed":
            return _error_result(
                "REPORT_GENERATION_FAILED",
                f"Report generation failed: {poll_result.get('error', 'Unknown error')}"
            )
        else:
            return _error_result(
                "REPORT_TIMEOUT",
                f"Report generation timed out. Report may still be processing."
            )
            
    except ValueError as exc:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("GENERATE_REPORT_FAILED", str(exc))


async def _list_reports_impl(
    project_id: str,
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    List reports for a project.
    
    Args:
        project_id: Project UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with reports list.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models import Project, ReviewReport
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Get reports
            stmt = (
                select(ReviewReport)
                .where(ReviewReport.project_id == pid)
                .order_by(ReviewReport.created_at.desc())
            )
            result = await db.execute(stmt)
            reports = result.scalars().all()
        
        report_list = []
        for report in reports:
            report_list.append({
                "report_id": str(report.id),
                "title": report.title,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "validation_status": report.validation_status,
            })
        
        return _ok_result(
            f"Found {len(report_list)} reports",
            {"reports": report_list}
        )
        
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("LIST_REPORTS_FAILED", str(exc))


async def _get_report_impl(
    project_id: str,
    report_id: str,
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    Get full report content with references.
    
    Args:
        project_id: Project UUID string.
        report_id: Report UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with report content and references.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models import Project, ReviewReport, ReportCitation
        from app.services.report_generation import _build_references
        
        pid = PyUUID(project_id)
        rid = PyUUID(report_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Get report
            stmt = select(ReviewReport).where(
                ReviewReport.id == rid,
                ReviewReport.project_id == pid,
            )
            result = await db.execute(stmt)
            report = result.scalar_one_or_none()
            
            if report is None:
                return _error_result("REPORT_NOT_FOUND", f"Report {report_id} not found")
            
            # Get citations
            citation_stmt = select(ReportCitation).where(ReportCitation.report_id == rid)
            citation_result = await db.execute(citation_stmt)
            citations = citation_result.scalars().all()
            
            cited_ids = {c.project_paper_id for c in citations}
            references = await _build_references(db, cited_ids)
        
        return _ok_result(
            f"Retrieved report: {report.title}",
            {
                "report_id": str(report.id),
                "title": report.title,
                "content": report.content_markdown,
                "references": references,
                "validation_status": report.validation_status,
            }
        )
        
    except ValueError:
        return _error_result("INVALID_ID", "Invalid project or report ID format")
    except Exception as exc:
        return _error_result("GET_REPORT_FAILED", str(exc))


async def _export_report_markdown_impl(
    project_id: str,
    report_id: str,
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    Export a report as markdown.
    
    Args:
        project_id: Project UUID string.
        report_id: Report UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with markdown content.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models import Project, ReviewReport
        
        pid = PyUUID(project_id)
        rid = PyUUID(report_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Get report
            stmt = select(ReviewReport).where(
                ReviewReport.id == rid,
                ReviewReport.project_id == pid,
            )
            result = await db.execute(stmt)
            report = result.scalar_one_or_none()
            
            if report is None:
                return _error_result("REPORT_NOT_FOUND", f"Report {report_id} not found")
        
        return _ok_result(
            f"Exported report as markdown",
            {
                "markdown": report.content_markdown,
                "title": report.title,
            }
        )
        
    except ValueError:
        return _error_result("INVALID_ID", "Invalid project or report ID format")
    except Exception as exc:
        return _error_result("EXPORT_REPORT_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
async def generate_report(
    project_id: str,
    title: Optional[str] = None,
    include_gap_section: bool = True,
    selected_gap_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate a literature review report for a project.

    Use this when the user wants to create a comprehensive literature review
    based on their saved papers and extracted matrix.

    Prerequisites:
    - Project must have matrix rows (generate matrix first if needed)
    - Optional: Research gaps detected (will be included if include_gap_section=True)

    Returns:
        Report ID and citation validation status.

    Args:
        project_id: The project UUID.
        title: Optional report title.
        include_gap_section: Whether to include research gaps section (default True).
        selected_gap_ids: Specific gap IDs to include in the report.
    """
    user = get_user()
    uid = get_user_id()
    return await _generate_report_impl(
        project_id, title, include_gap_section, selected_gap_ids, uid, user
    )


@tool
async def list_reports(
    project_id: str,
) -> Dict[str, Any]:
    """
    List all reports for a project.

    Use this when the user wants to see existing reports or find a specific
    report to retrieve or export.

    Returns:
        List of reports with metadata.

    Args:
        project_id: The project UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _list_reports_impl(project_id, uid, user)


@tool
async def get_report(
    project_id: str,
    report_id: str,
) -> Dict[str, Any]:
    """
    Get the full content of a report with references.

    Use this when the user wants to read a specific report, including its
    full markdown content and the reference list.

    Returns:
        Report content and references.

    Args:
        project_id: The project UUID.
        report_id: The report UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _get_report_impl(project_id, report_id, uid, user)


@tool
async def export_report_markdown(
    project_id: str,
    report_id: str,
) -> Dict[str, Any]:
    """
    Export a report as a markdown string.

    Use this when the user wants to copy or download the report in markdown format.

    Returns:
        Report as markdown string.

    Args:
        project_id: The project UUID.
        report_id: The report UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _export_report_markdown_impl(project_id, report_id, uid, user)


# ── Toolkit Registration ─────────────────────────────────────────────────────


from app.agents.assistant.tools.base import BaseToolkit, register_toolkit


@register_toolkit
class ReportToolkit(BaseToolkit):
    """Toolkit for report generation."""

    def get_tools(self):
        return [generate_report, list_reports, get_report, export_report_markdown]
