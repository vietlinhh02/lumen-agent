"""
Matrix tools for the Assistant.

Provides tools for generating, listing, and updating literature matrix rows.

Use these when:
- The user wants to generate a literature matrix for their project
- The user wants to see matrix rows
- The user wants to edit a matrix row
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, TYPE_CHECKING

from langchain_core.tools import tool

from app.agents.assistant.tools.context import get_user, get_user_id
from app.agents.assistant.tools.schemas import (
    GenerateMatrixInput,
    GenerateMatrixOutput,
    ListMatrixRowsInput,
    ListMatrixRowsOutput,
    MatrixRow,
    UpdateMatrixRowInput,
    UpdateMatrixRowOutput,
)

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
    
    Args:
        job_id: The job UUID to poll.
        max_wait: Maximum time to wait in seconds.
        interval: Time between polls in seconds.
    
    Returns:
        Dict with job status, result, and any error message.
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


# ── Implementations ───────────────────────────────────────────────────────


async def _generate_matrix_impl(
    project_id: str,
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    Generate literature matrix for a project by enqueuing a background job.
    
    Args:
        project_id: Project UUID string.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with job status and rows_created count.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import func, select
        from app.db.models import BackgroundJob, Project, ProjectPaper
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            project = project_result.scalar_one_or_none()
            if project is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Check for saved papers
            count_stmt = select(func.count()).select_from(ProjectPaper).where(
                ProjectPaper.project_id == pid,
                ProjectPaper.status == "saved"
            )
            saved_count = (await db.execute(count_stmt)).scalar() or 0
            if saved_count == 0:
                return _error_result(
                    "NO_PAPERS",
                    "No saved papers to generate matrix from. Save some papers first."
                )
            
            # Create background job
            job = BackgroundJob(
                job_type="matrix_generate",
                project_id=pid,
                user_id=user.id,
                status="pending",
                total=saved_count,
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
        
        # Launch background task
        from app.routers.matrix import _run_matrix_job
        asyncio.ensure_future(_run_matrix_job(job.id, pid, user.id, project.topic))
        
        # Poll for completion
        poll_result = await _poll_job(job.id)
        
        rows_created = poll_result.get("result", {}).get("created_count", 0)
        
        if poll_result["status"] == "completed":
            return _ok_result(
                f"Matrix generated successfully. Created {rows_created} rows.",
                {"status": "completed", "rows_created": rows_created}
            )
        elif poll_result["status"] == "failed":
            return _error_result(
                "MATRIX_GENERATION_FAILED",
                f"Matrix generation failed: {poll_result.get('error', 'Unknown error')}"
            )
        else:
            return _error_result(
                "MATRIX_TIMEOUT",
                f"Matrix generation timed out. {rows_created} rows may have been created."
            )
            
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("GENERATE_MATRIX_FAILED", str(exc))


async def _list_matrix_rows_impl(
    project_id: str,
    limit: int,
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    List matrix rows for a project.
    
    Args:
        project_id: Project UUID string.
        limit: Maximum rows to return.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with matrix rows list.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models import Project, LiteratureMatrixRow
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            project = project_result.scalar_one_or_none()
            if project is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Get matrix rows
            stmt = (
                select(LiteratureMatrixRow)
                .where(LiteratureMatrixRow.project_id == pid)
                .order_by(LiteratureMatrixRow.updated_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()
        
        matrix_rows = []
        for row in rows:
            matrix_rows.append({
                "row_id": str(row.id),
                "dimension": row.research_problem or row.method or "Unknown",
                "cell_content": row.key_result or row.contribution or "",
                "source_paper_id": str(row.project_paper_id) if row.project_paper_id else None,
                # Extended fields for full data
                "research_problem": row.research_problem,
                "method": row.method,
                "dataset_or_context": row.dataset_or_context,
                "key_result": row.key_result,
                "limitation": row.limitation,
                "contribution": row.contribution,
                "relevance": row.relevance,
                "extraction_confidence": row.extraction_confidence,
            })
        
        return _ok_result(
            f"Found {len(matrix_rows)} matrix rows",
            {"rows": matrix_rows}
        )
        
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("LIST_MATRIX_ROWS_FAILED", str(exc))


async def _update_matrix_row_impl(
    row_id: str,
    field: str,
    new_value: str,
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    Update a matrix row field.
    
    Args:
        row_id: Matrix row UUID string.
        field: Field name to update.
        new_value: New value for the field.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with success status and updated row.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    # Validate field name
    valid_fields = {
        "research_problem", "method", "dataset_or_context", "key_result",
        "limitation", "contribution", "relevance"
    }
    if field not in valid_fields:
        return _error_result(
            "INVALID_FIELD",
            f"Invalid field '{field}'. Valid fields: {', '.join(sorted(valid_fields))}"
        )
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models import LiteratureMatrixRow, Project
        
        rid = PyUUID(row_id)
        
        async with async_session_factory() as db:
            # Get the row and verify ownership via project
            stmt = (
                select(LiteratureMatrixRow)
                .where(LiteratureMatrixRow.id == rid)
            )
            result = await db.execute(stmt)
            row = result.scalar_one_or_none()
            
            if row is None:
                return _error_result("ROW_NOT_FOUND", f"Matrix row {row_id} not found")
            
            # Verify project ownership
            project_result = await db.execute(
                select(Project).where(
                    Project.id == row.project_id,
                    Project.owner_id == user.id
                )
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("ACCESS_DENIED", "Access denied to this matrix row")
            
            # Update the field
            setattr(row, field, new_value)
            row.updated_by = user.id
            await db.commit()
            await db.refresh(row)
        
        return _ok_result(
            f"Updated {field} for matrix row",
            {
                "success": True,
                "row": {
                    "row_id": str(row.id),
                    "field": field,
                    "new_value": new_value,
                }
            }
        )
        
    except ValueError:
        return _error_result("INVALID_ROW_ID", f"Invalid matrix row ID format: {row_id}")
    except Exception as exc:
        return _error_result("UPDATE_MATRIX_ROW_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
async def generate_matrix(
    project_id: str,
) -> Dict[str, Any]:
    """
    Generate a literature matrix for a project by extracting information from saved papers.

    Use this when the user wants to create or regenerate a literature matrix.
    This runs AI extraction on all saved papers, which may take 1-2 minutes.

    Prerequisites:
    - Project must have at least 1 saved paper

    Returns:
        Status and number of rows created.

    Args:
        project_id: The project UUID.
    """
    user = get_user()
    uid = get_user_id()
    return await _generate_matrix_impl(project_id, uid, user)


@tool
async def list_matrix_rows(
    project_id: str,
    limit: int = 200,
) -> Dict[str, Any]:
    """
    List all literature matrix rows for a project.

    Use this when the user wants to see the extracted information from papers,
    or to review the current state of the matrix.

    Returns:
        List of matrix rows with extracted information.

    Args:
        project_id: The project UUID.
        limit: Maximum rows to return (default 200, max 500).
    """
    user = get_user()
    uid = get_user_id()
    return await _list_matrix_rows_impl(project_id, limit, uid, user)


@tool
async def update_matrix_row(
    row_id: str,
    field: str,
    new_value: str,
) -> Dict[str, Any]:
    """
    Update a specific field in a matrix row.

    Use this when the user wants to correct or improve extracted information
    in a matrix row.

    Valid fields:
    - research_problem: The research problem addressed
    - method: The methodology used
    - dataset_or_context: Dataset or experimental context
    - key_result: Main findings or results
    - limitation: Limitations of the study
    - contribution: Main contribution of the paper
    - relevance: How relevant this paper is to the research topic

    Returns:
        Success status and updated row info.

    Args:
        row_id: The matrix row UUID.
        field: Field name to update.
        new_value: New value for the field.
    """
    user = get_user()
    uid = get_user_id()
    return await _update_matrix_row_impl(row_id, field, new_value, uid, user)


# ── Toolkit Registration ─────────────────────────────────────────────────────


from app.agents.assistant.tools.base import BaseToolkit, register_toolkit


@register_toolkit
class MatrixToolkit(BaseToolkit):
    """Toolkit for literature matrix generation."""

    def get_tools(self):
        return [generate_matrix, list_matrix_rows, update_matrix_row]
