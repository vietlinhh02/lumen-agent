"""REST endpoints for literature matrix CRUD."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import LiteratureMatrixRow, Project, ProjectPaper, User
from app.db.session import async_session_factory, get_db
from app.schemas.matrix import (
    MatrixGenerateRequest,
    MatrixListResponse,
    MatrixRowResponse,
    MatrixRowUpdate,
)
from app.services.literature_matrix import delete_row, get_by_project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["matrix"])
_PROGRESS_TITLE_LIMIT = 50


async def _verify_project_owner(
    db: AsyncSession,
    user: User,
    project_id: UUID,
) -> Project:
    """Load project and verify ownership. Raises 404 if not found or not owned."""
    stmt = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


# ── List Matrix Rows ─────────────────────────────────────────────────────


@router.get("/{project_id}/matrix", response_model=MatrixListResponse)
async def list_matrix_rows(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixListResponse:
    await _verify_project_owner(db, user, project_id)
    rows = await get_by_project(db, project_id)

    items = []
    for row in rows:
        # Load paper title from relationship
        paper_title = None
        if row.project_paper and row.project_paper.paper:
            paper_title = row.project_paper.paper.title
        items.append(
            MatrixRowResponse(
                id=row.id,
                project_id=row.project_id,
                project_paper_id=row.project_paper_id,
                paper_title=paper_title,
                research_problem=row.research_problem,
                method=row.method,
                dataset_or_context=row.dataset_or_context,
                key_result=row.key_result,
                limitation=row.limitation,
                contribution=row.contribution,
                relevance=row.relevance,
                extraction_confidence=row.extraction_confidence,
                created_by=row.created_by,
                updated_at=row.updated_at,
            )
        )

    return MatrixListResponse(items=items)


# ── Update Matrix Row ────────────────────────────────────────────────────


@router.patch("/{project_id}/matrix/{row_id}", response_model=MatrixRowResponse)
async def update_matrix_row(
    project_id: UUID,
    row_id: UUID,
    body: MatrixRowUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MatrixRowResponse:
    await _verify_project_owner(db, user, project_id)

    stmt = select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.id == row_id,
        LiteratureMatrixRow.project_id == project_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Matrix row not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(row, field, value)
    row.created_by = "user"
    row.updated_by = user.id

    await db.commit()
    await db.refresh(row)

    paper_title = None
    if row.project_paper and row.project_paper.paper:
        paper_title = row.project_paper.paper.title

    return MatrixRowResponse(
        id=row.id,
        project_id=row.project_id,
        project_paper_id=row.project_paper_id,
        paper_title=paper_title,
        research_problem=row.research_problem,
        method=row.method,
        dataset_or_context=row.dataset_or_context,
        key_result=row.key_result,
        limitation=row.limitation,
        contribution=row.contribution,
        relevance=row.relevance,
        extraction_confidence=row.extraction_confidence,
        created_by=row.created_by,
        updated_at=row.updated_at,
    )


# ── Delete Matrix Row ────────────────────────────────────────────────────


@router.delete("/{project_id}/matrix/{row_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_matrix_row(
    project_id: UUID,
    row_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await _verify_project_owner(db, user, project_id)
    deleted = await delete_row(db, project_id, row_id)
    if not deleted:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Matrix row not found",
        )


# ── Generate Matrix Rows (trigger AI extraction) ─────────────────────────


@router.post("/{project_id}/matrix:generate")
async def generate_matrix(
    project_id: UUID,
    body: MatrixGenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start matrix generation as a background job. Returns job info immediately."""
    import asyncio

    from app.db.models import BackgroundJob

    project = await _verify_project_owner(db, user, project_id)

    # Load saved papers count
    count_stmt = select(ProjectPaper).where(
        ProjectPaper.project_id == project_id, ProjectPaper.status == "saved"
    )
    saved_papers = (await db.execute(count_stmt)).scalars().all()
    if not saved_papers:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No saved papers to generate matrix from",
        )

    # Create a background job record
    job = BackgroundJob(
        job_type="matrix_generate",
        project_id=project_id,
        user_id=user.id,
        status="pending",
        total=len(saved_papers),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background task
    asyncio.ensure_future(_run_matrix_job(job.id, project_id, user.id, project.topic))

    return {"job_id": str(job.id), "status": "running", "total": len(saved_papers)}


async def _run_matrix_job(
    job_id: UUID,
    project_id: UUID,
    user_id: UUID,
    topic: str,
) -> None:
    """Background worker: run matrix extraction."""
    async with async_session_factory() as bg_db:
        job = None
        try:
            from app.db.models import BackgroundJob

            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            job.progress = 0
            job.progress_json = {"processed": 0, "total": job.total, "current": ""}
            await bg_db.commit()

            from app.agents.nodes import matrix_extraction_node
            from app.agents.state import ResearchState

            # Hydrate protocol from the project so matrix rows can be grounded
            # in inclusion/exclusion + population + outcome criteria.
            proj_reload = await bg_db.execute(
                select(Project).where(Project.id == project_id)
            )
            proj_row = proj_reload.scalar_one_or_none()
            protocol = (proj_row.review_protocol if proj_row else None) or None

            state = ResearchState(
                project_id=project_id,
                user_id=user_id,
                user_topic=topic,
                review_protocol=protocol,
            )

            async def _update_progress(processed: int, total: int, current_paper: str) -> None:
                progress_payload = {
                    "processed": processed,
                    "total": total,
                    "current": current_paper[:_PROGRESS_TITLE_LIMIT],
                }
                async with async_session_factory() as progress_db:
                    await progress_db.execute(
                        update(BackgroundJob)
                        .where(BackgroundJob.id == job_id)
                        .values(progress=processed, progress_json=progress_payload)
                    )
                    await progress_db.commit()

            result = await matrix_extraction_node(state, bg_db, progress_callback=_update_progress)

            created = len(result.get("matrix_rows", []))
            job.status = result.get("matrix_status", "failed")
            job.progress = job.total
            job.progress_json = {
                "processed": job.total,
                "total": job.total,
                "current": "Completed",
            }
            job.result = {
                "created_count": created,
                "skipped_count": job.total - created,
            }
            from datetime import UTC, datetime

            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background matrix job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.progress_json = {
                        "processed": job.progress,
                        "total": job.total,
                        "current": "Failed",
                    }
                    from datetime import UTC, datetime

                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass
