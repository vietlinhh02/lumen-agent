"""
Gap tools for the Assistant.

Provides tools for detecting and managing research gaps.

Use these when:
- The user wants to identify research gaps in their literature
- The user wants to see or delete identified gaps
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

from app.agents.assistant.tools.context import get_user, get_user_id

if TYPE_CHECKING:
    from uuid import UUID


def _ok_result(message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a success result dict."""
    result = {"ok": True, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _error_result(error_code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create an error result dict that the LLM can reason about."""
    result = {"ok": False, "error_code": error_code, "message": message}
    if details is not None:
        result["details"] = details
    return result


# ── Polling helper ──────────────────────────────────────────────────────────


async def _poll_job(
    job_id: UUID,
    max_wait: float = 120.0,
    interval: float = 2.0,
) -> dict[str, Any]:
    """
    Poll a background job until completion or failure.
    """
    from sqlalchemy import select

    from app.db.models import BackgroundJob
    from app.db.session import async_session_factory
    
    elapsed = 0.0
    while elapsed < max_wait:
        await asyncio.sleep(interval)
        elapsed += interval
        
        async with async_session_factory() as db:
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


async def _detect_gaps_impl(
    project_id: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    Detect research gaps for a project by enqueuing a background job.
    
    Args:
        project_id: Project UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with job status and gaps_found count.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID

        from sqlalchemy import func, select

        from app.db.models import BackgroundJob, LiteratureMatrixRow, Project
        from app.db.session import async_session_factory
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            project = project_result.scalar_one_or_none()
            if project is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Check matrix row count (need at least 5)
            count_stmt = select(func.count()).select_from(LiteratureMatrixRow).where(
                LiteratureMatrixRow.project_id == pid
            )
            matrix_count = (await db.execute(count_stmt)).scalar() or 0
            if matrix_count < 5:
                return _error_result(
                    "INSUFFICIENT_MATRIX",
                    f"Need at least 5 matrix rows for gap detection. Current: {matrix_count}. "
                    "Generate a matrix first."
                )
            
            # Create background job
            job = BackgroundJob(
                job_type="gap_generate",
                project_id=pid,
                user_id=user.id,
                status="pending",
                total=matrix_count,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
        
        # Launch background task
        from app.routers.gaps import _run_gap_job
        asyncio.ensure_future(_run_gap_job(
            job.id, pid, user.id, project.topic, project.research_question
        ))
        
        # Poll for completion
        poll_result = await _poll_job(job.id)
        
        gaps_found = poll_result.get("result", {}).get("gap_count", 0)
        
        if poll_result["status"] == "completed":
            return _ok_result(
                f"Gap detection completed. Found {gaps_found} research gaps.",
                {"status": "completed", "gaps_found": gaps_found}
            )
        elif poll_result["status"] == "failed":
            return _error_result(
                "GAP_DETECTION_FAILED",
                f"Gap detection failed: {poll_result.get('error', 'Unknown error')}"
            )
        else:
            return _error_result(
                "GAP_TIMEOUT",
                f"Gap detection timed out. {gaps_found} gaps may have been found."
            )
            
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("DETECT_GAPS_FAILED", str(exc))


async def _list_gaps_impl(
    project_id: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    List research gaps for a project.
    
    Args:
        project_id: Project UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with gaps list.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID

        from sqlalchemy import select

        from app.db.models import Paper, Project, ProjectPaper, ResearchGap
        from app.db.session import async_session_factory
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Get gaps with evidence
            stmt = (
                select(ResearchGap)
                .where(ResearchGap.project_id == pid)
                .order_by(ResearchGap.created_at.desc())
            )
            result = await db.execute(stmt)
            gaps = result.scalars().all()
        
            gap_list = []
            for gap in gaps:
                # Load evidence
                evidence_list = []
                for ev in gap.evidence_entries:
                    # Get paper title
                    pp_result = await db.execute(
                        select(ProjectPaper).where(ProjectPaper.id == ev.project_paper_id)
                    )
                    pp = pp_result.scalar_one_or_none()
                    paper_title = ""
                    if pp:
                        paper_result = await db.execute(
                            select(Paper).where(Paper.id == pp.paper_id)
                        )
                        paper = paper_result.scalar_one_or_none()
                        if paper:
                            paper_title = paper.title
                    
                    evidence_list.append({
                        "project_paper_id": str(ev.project_paper_id),
                        "title": paper_title,
                        "evidence_type": ev.evidence_type,
                        "note": ev.note,
                    })
                
                gap_list.append({
                    "gap_id": str(gap.id),
                    "title": gap.title,
                    "description": gap.description,
                    "severity": gap.confidence,  # Map confidence to severity
                    "evidence": evidence_list,
                    "suggested_direction": gap.suggested_direction,
                    "evidence_summary": gap.evidence_summary,
                })
            
            return _ok_result(
                f"Found {len(gap_list)} research gaps",
                {"gaps": gap_list}
            )
        
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("LIST_GAPS_FAILED", str(exc))


async def _delete_gap_impl(
    gap_id: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    Delete a research gap.
    
    Args:
        gap_id: Gap UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with success status.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID

        from sqlalchemy import select

        from app.db.models import Project, ResearchGap
        from app.db.session import async_session_factory
        from app.services.gap_detection import delete_gap
        
        gid = PyUUID(gap_id)
        
        async with async_session_factory() as db:
            # Get the gap and verify ownership via project
            stmt = select(ResearchGap).where(ResearchGap.id == gid)
            result = await db.execute(stmt)
            gap = result.scalar_one_or_none()
            
            if gap is None:
                return _error_result("GAP_NOT_FOUND", f"Gap {gap_id} not found")
            
            # Verify project ownership
            project_result = await db.execute(
                select(Project).where(
                    Project.id == gap.project_id,
                    Project.owner_id == user.id
                )
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("ACCESS_DENIED", "Access denied to this gap")
            
            # Delete the gap
            deleted = await delete_gap(db, gap.project_id, gid)
            
            if not deleted:
                return _error_result("DELETE_FAILED", "Failed to delete gap")
        
        return _ok_result("Gap deleted successfully", {"success": True})
        
    except ValueError:
        return _error_result("INVALID_GAP_ID", f"Invalid gap ID format: {gap_id}")
    except Exception as exc:
        return _error_result("DELETE_GAP_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
async def detect_research_gaps(
    project_id: str,
) -> dict[str, Any]:
    """
    Detect research gaps in the literature for a project.

    Use this when the user wants to identify unanswered questions or
    underexplored areas in their research domain.

    Prerequisites:
    - Project must have at least 5 matrix rows (generate matrix first if needed)

    Returns:
        Status and number of gaps detected.

    Args:
        project_id: The project UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _detect_gaps_impl(project_id, uid, user)


@tool
async def list_gaps(
    project_id: str,
) -> dict[str, Any]:
    """
    List all research gaps for a project.

    Use this when the user wants to see identified research gaps,
    including their descriptions, severity, and supporting evidence.

    Returns:
        List of research gaps with evidence.

    Args:
        project_id: The project UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _list_gaps_impl(project_id, uid, user)


@tool
async def delete_gap(
    gap_id: str,
) -> dict[str, Any]:
    """
    Delete a research gap.

    Use this when the user wants to remove a gap that is no longer
    relevant or was incorrectly identified.

    Returns:
        Success status.

    Args:
        gap_id: The gap UUID to delete.
    """
    user = get_user()
    uid = get_user_id()
    return await _delete_gap_impl(gap_id, uid, user)


# ── Toolkit Registration ─────────────────────────────────────────────────────


from app.agents.assistant.tools.base import BaseToolkit, register_toolkit


@register_toolkit
class GapToolkit(BaseToolkit):
    """Toolkit for research gap detection."""

    def get_tools(self):
        return [detect_research_gaps, list_gaps, delete_gap]
