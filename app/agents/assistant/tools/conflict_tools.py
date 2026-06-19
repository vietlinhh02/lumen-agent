"""
Conflict tools for the Assistant.

Provides tools for detecting and listing conflicts between papers.

Use these when:
- The user wants to identify conflicting findings in their literature
- The user wants to see conflicting claims between papers
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


async def _detect_conflicts_impl(
    project_id: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    Detect conflicts between papers in a project by enqueuing a background job.
    
    Args:
        project_id: Project UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with job status and conflicts_found count.
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
            
            # Check matrix row count (need at least 4)
            count_stmt = select(func.count()).select_from(LiteratureMatrixRow).where(
                LiteratureMatrixRow.project_id == pid
            )
            matrix_count = (await db.execute(count_stmt)).scalar() or 0
            if matrix_count < 4:
                return _error_result(
                    "INSUFFICIENT_MATRIX",
                    f"Need at least 4 matrix rows for conflict detection. Current: {matrix_count}. "
                    "Generate a matrix first."
                )
            
            # Create background job
            job = BackgroundJob(
                job_type="conflict_generate",
                project_id=pid,
                user_id=user.id,
                status="pending",
                total=matrix_count,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
        
        # Launch background task
        from app.routers.conflicts import _run_conflict_job
        asyncio.ensure_future(_run_conflict_job(
            job.id, pid, user.id, project.topic, project.research_question
        ))
        
        # Poll for completion
        poll_result = await _poll_job(job.id)
        
        conflicts_found = poll_result.get("result", {}).get("conflict_count", 0)
        
        if poll_result["status"] == "completed":
            return _ok_result(
                f"Conflict detection completed. Found {conflicts_found} conflicts.",
                {"status": "completed", "conflicts_found": conflicts_found}
            )
        elif poll_result["status"] == "failed":
            return _error_result(
                "CONFLICT_DETECTION_FAILED",
                f"Conflict detection failed: {poll_result.get('error', 'Unknown error')}"
            )
        else:
            return _error_result(
                "CONFLICT_TIMEOUT",
                f"Conflict detection timed out. {conflicts_found} conflicts may have been found."
            )
            
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("DETECT_CONFLICTS_FAILED", str(exc))


async def _list_conflicts_impl(
    project_id: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    List conflicts for a project.
    
    Args:
        project_id: Project UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with conflicts list.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID

        from sqlalchemy import select

        from app.db.models import ConflictingFinding, Paper, Project, ProjectPaper
        from app.db.session import async_session_factory
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Get conflicts
            stmt = (
                select(ConflictingFinding)
                .where(ConflictingFinding.project_id == pid)
                .order_by(ConflictingFinding.created_at.desc())
            )
            result = await db.execute(stmt)
            conflicts = result.scalars().all()
        
        conflict_list = []
        for conflict in conflicts:
            # Get paper titles
            pa_title = ""
            pb_title = ""
            
            if conflict.paper_a_id:
                pp_result = await db.execute(
                    select(ProjectPaper).where(ProjectPaper.id == conflict.paper_a_id)
                )
                pp = pp_result.scalar_one_or_none()
                if pp:
                    paper_result = await db.execute(
                        select(Paper).where(Paper.id == pp.paper_id)
                    )
                    paper = paper_result.scalar_one_or_none()
                    if paper:
                        pa_title = paper.title
            
            if conflict.paper_b_id:
                pp_result = await db.execute(
                    select(ProjectPaper).where(ProjectPaper.id == conflict.paper_b_id)
                )
                pp = pp_result.scalar_one_or_none()
                if pp:
                    paper_result = await db.execute(
                        select(Paper).where(Paper.id == pp.paper_id)
                    )
                    paper = paper_result.scalar_one_or_none()
                    if paper:
                        pb_title = paper.title
            
            conflict_list.append({
                "conflict_id": str(conflict.id),
                "title": conflict.title,
                "description": conflict.description,
                "paper_ids": [
                    str(conflict.paper_a_id) if conflict.paper_a_id else None,
                    str(conflict.paper_b_id) if conflict.paper_b_id else None,
                ],
                "paper_titles": [pa_title, pb_title],
                "severity": conflict.confidence,
                "shared_context": conflict.shared_context,
                "claim_a": conflict.claim_a,
                "claim_b": conflict.claim_b,
                "possible_explanation": conflict.possible_explanation,
            })
        
        return _ok_result(
            f"Found {len(conflict_list)} conflicts",
            {"conflicts": conflict_list}
        )
        
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("LIST_CONFLICTS_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
async def detect_conflicts(
    project_id: str,
) -> dict[str, Any]:
    """
    Detect conflicts between papers in a project.

    Use this when the user wants to identify contradictory findings,
    disagreements in methodology, or inconsistent results.

    Prerequisites:
    - Project must have at least 4 matrix rows (generate matrix first if needed)

    Returns:
        Status and number of conflicts detected.

    Args:
        project_id: The project UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _detect_conflicts_impl(project_id, uid, user)


@tool
async def list_conflicts(
    project_id: str,
) -> dict[str, Any]:
    """
    List all conflicts between papers for a project.

    Use this when the user wants to see identified conflicts,
    including the papers involved, the claims, and possible explanations.

    Returns:
        List of conflicts with details.

    Args:
        project_id: The project UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _list_conflicts_impl(project_id, uid, user)


# ── Toolkit Registration ─────────────────────────────────────────────────────


from app.agents.assistant.tools.base import BaseToolkit, register_toolkit


@register_toolkit
class ConflictToolkit(BaseToolkit):
    """Toolkit for conflict detection."""

    def get_tools(self):
        return [detect_conflicts, list_conflicts]
