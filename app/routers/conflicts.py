"""REST endpoints for conflict detection."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import conflict_detection_node
from app.agents.state import ResearchState
from app.core.security import get_current_user
from app.db.models import (
    ConflictingFinding,
    ConflictingFindingChunk,
    LiteratureMatrixRow,
    Paper,
    Project,
    ProjectPaper,
    User,
)
from app.db.session import get_db
from app.schemas.conflicts import (
    ConflictEvidenceResponse,
    ConflictListResponse,
    ConflictResponse,
)
from app.schemas.evidence import EvidenceChunkResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conflicts"])


@router.post("/{project_id}/conflicts:generate")
async def generate_conflicts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start conflict detection as a background job. Returns job info immediately."""
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
    if matrix_count < 4:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_MATRIX",
                "message": f"Need >= 4 matrix rows for conflict detection, got {matrix_count}",
                "details": {"current_matrix_rows": matrix_count},
            },
        )

    # Create a background job record
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
    asyncio.ensure_future(
        _run_conflict_job(job.id, pid, user.id, project.topic, project.research_question)
    )

    return {"job_id": str(job.id), "status": "running", "total": matrix_count}


async def _run_conflict_job(
    job_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    topic: str,
    research_question: str | None,
) -> None:
    """Background worker: run conflict detection."""
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

            # Hydrate protocol from project so conflict detection can
            # decide whether two papers truly disagree on protocol terms.
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

            result = await conflict_detection_node(state, bg_db)

            if result.get("conflict_status") == "failed":
                job.status = "failed"
                job.error_message = "; ".join(result.get("errors", []))
            else:
                job.status = "completed"
                job.result = {"conflict_count": len(result.get("conflicts", []))}

            from datetime import UTC, datetime

            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background conflict job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    from datetime import UTC, datetime

                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass


@router.get("/{project_id}/conflicts", response_model=ConflictListResponse)
async def list_conflicts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConflictListResponse:
    """List conflicts for a project."""
    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    conflicts = await _load_conflicts(db, pid)
    return ConflictListResponse(items=conflicts, total=len(conflicts))


@router.get(
    "/{project_id}/conflicts/{conflict_id}/evidence",
    response_model=ConflictEvidenceResponse,
)
async def get_conflict_evidence(
    project_id: str,
    conflict_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConflictEvidenceResponse:
    """Return the persisted chunks behind each side of a conflict.

    Conflicts detected before T3 Phase 2 have no chunks — re-running detection
    backfills them. Empty sides simply render an empty drawer.
    """
    pid = uuid.UUID(project_id)
    cid = uuid.UUID(conflict_id)

    finding = (
        await db.execute(
            select(ConflictingFinding).where(
                ConflictingFinding.id == cid,
                ConflictingFinding.project_id == pid,
            )
        )
    ).scalar_one_or_none()
    if not finding:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Conflict not found"
        )
    # Ownership check piggybacks on the project lookup.
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    chunks = (
        await db.execute(
            select(ConflictingFindingChunk)
            .where(ConflictingFindingChunk.conflict_id == cid)
            .order_by(ConflictingFindingChunk.score.desc())
        )
    ).scalars().all()

    def _to_item(ch: ConflictingFindingChunk) -> EvidenceChunkResponse:
        return EvidenceChunkResponse(
            chunk_id=ch.chunk_id,
            project_paper_id=ch.project_paper_id,
            chunk_text=ch.snippet,
            section_label=ch.section_label,
            content_type=ch.content_type,
            score=ch.score,
        )

    return ConflictEvidenceResponse(
        paper_a_title=await _get_paper_title(db, finding.paper_a_id),
        paper_b_title=await _get_paper_title(db, finding.paper_b_id),
        claim_a=[_to_item(c) for c in chunks if c.polarity == "a"],
        claim_b=[_to_item(c) for c in chunks if c.polarity == "b"],
    )


async def _load_conflicts(db: AsyncSession, project_id: uuid.UUID) -> list[ConflictResponse]:
    """Load conflicts and format as ConflictResponse."""
    stmt = (
        select(ConflictingFinding)
        .where(ConflictingFinding.project_id == project_id)
        .order_by(ConflictingFinding.created_at.desc())
    )
    findings = (await db.execute(stmt)).scalars().all()

    result = []
    for f in findings:
        pa_title = await _get_paper_title(db, f.paper_a_id)
        pb_title = await _get_paper_title(db, f.paper_b_id)

        result.append(
            ConflictResponse(
                id=str(f.id),
                title=f.title,
                description=f.description,
                paper_a_id=str(f.paper_a_id),
                paper_a_title=pa_title,
                paper_b_id=str(f.paper_b_id),
                paper_b_title=pb_title,
                shared_context=f.shared_context,
                claim_a=f.claim_a,
                claim_b=f.claim_b,
                possible_explanation=f.possible_explanation,
                confidence=f.confidence,
            )
        )

    return result


async def _get_paper_title(db: AsyncSession, project_paper_id: uuid.UUID) -> str:
    """Get paper title from project_paper_id."""
    pp = (
        await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    ).scalar_one_or_none()
    if not pp:
        return ""
    paper = (await db.execute(select(Paper).where(Paper.id == pp.paper_id))).scalar_one_or_none()
    return paper.title if paper else ""
