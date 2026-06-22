"""REST endpoints for research gap analysis."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.nodes import gap_analysis_node
from app.agents.state import ResearchState
from app.core.security import get_current_user
from app.db.models import (
    LiteratureMatrixRow,
    Paper,
    Project,
    ProjectPaper,
    ResearchGap,
    User,
)
from app.db.session import get_db
from app.schemas.gaps import GapEvidenceResponse, GapListResponse, GapResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gaps"])


@router.post("/{project_id}/gaps:generate")
async def generate_gaps(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start gap generation as a background job. Returns job info immediately."""
    import asyncio

    from app.db.models import BackgroundJob

    pid = uuid.UUID(project_id)

    # Verify ownership
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check matrix row count
    matrix_count = (
        await db.execute(
            select(func.count())
            .select_from(LiteratureMatrixRow)
            .where(LiteratureMatrixRow.project_id == pid)
        )
    ).scalar()
    if matrix_count < 5:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_MATRIX",
                "message": f"Need >= 5 matrix rows, got {matrix_count}",
                "details": {"current_matrix_rows": matrix_count},
            },
        )

    # Create a background job record
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
    asyncio.ensure_future(
        _run_gap_job(job.id, pid, user.id, project.topic, project.research_question)
    )

    return {"job_id": str(job.id), "status": "running", "total": matrix_count}


async def _run_gap_job(
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    topic: str,
    research_question: str | None,
) -> None:
    """Background worker: run gap analysis."""
    from app.db.session import async_session_factory

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
            await bg_db.commit()

            # Hydrate protocol from project so gap detection can anchor
            # "absence" claims to the protocol's specified scope.
            proj_reload = await bg_db.execute(
                select(Project).where(Project.id == project_id)
            )
            proj_row = proj_reload.scalar_one_or_none()
            protocol = (proj_row.review_protocol if proj_row else None) or None

            state = ResearchState(
                project_id=project_id,
                user_id=user_id,
                user_topic=topic,
                research_question=research_question,
                review_protocol=protocol,
            )

            result = await gap_analysis_node(state, bg_db)

            if result.get("gap_status") == "failed":
                job.status = "failed"
                job.error_message = "; ".join(result.get("errors", []))
            else:
                job.status = "completed"
                job.result = {"gap_count": len(result.get("gaps", []))}

            from datetime import UTC, datetime

            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background gap job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    from datetime import UTC, datetime

                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass


@router.get("/{project_id}/gaps", response_model=GapListResponse)
async def list_gaps(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GapListResponse:
    """List gaps for a project."""
    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    gaps = await _load_gaps_with_evidence(db, pid)
    return GapListResponse(items=gaps, total=len(gaps))


@router.delete("/{project_id}/gaps/{gap_id}")
async def remove_gap(
    project_id: str,
    gap_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Delete a single gap."""
    pid = uuid.UUID(project_id)
    gid = uuid.UUID(gap_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    from app.services.gap_detection import delete_gap

    deleted = await delete_gap(db, pid, gid)
    if not deleted:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Gap not found")

    return {"deleted": True}


async def _load_gaps_with_evidence(db: AsyncSession, project_id: uuid.UUID) -> list[GapResponse]:
    """Load gaps and format as GapResponse with evidence."""
    stmt = (
        select(ResearchGap)
        .options(selectinload(ResearchGap.evidence_entries))
        .where(ResearchGap.project_id == project_id)
        .order_by(ResearchGap.created_at.desc())
    )
    gaps = (await db.execute(stmt)).scalars().all()

    result = []
    for gap in gaps:
        evidence = []
        for ev in gap.evidence_entries:
            pp = (
                await db.execute(select(ProjectPaper).where(ProjectPaper.id == ev.project_paper_id))
            ).scalar_one_or_none()
            paper_title = ""
            if pp:
                paper = (
                    await db.execute(select(Paper).where(Paper.id == pp.paper_id))
                ).scalar_one_or_none()
                if paper:
                    paper_title = paper.title

            evidence.append(
                GapEvidenceResponse(
                    project_paper_id=str(ev.project_paper_id),
                    title=paper_title,
                    evidence_type=ev.evidence_type,
                    note=ev.note,
                )
            )

        result.append(
            GapResponse(
                id=str(gap.id),
                title=gap.title,
                description=gap.description,
                suggested_direction=gap.suggested_direction,
                evidence_summary=gap.evidence_summary,
                confidence=gap.confidence,
                evidence=evidence,
            )
        )

    return result
