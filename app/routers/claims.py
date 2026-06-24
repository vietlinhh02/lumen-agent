"""REST endpoints for T7 Claim and Consensus Synthesis."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import (
    BackgroundJob,
    Claim,
    LiteratureMatrixRow,
    Paper,
    Project,
    ProjectPaper,
    User,
)
from app.db.session import get_db
from app.schemas.claims import (
    ClaimAggregateResponse,
    ClaimEvidenceResponse,
    ClaimListResponse,
    ClaimResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["claims"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _paper_title(db: AsyncSession, project_paper_id: uuid.UUID) -> str:
    pp = (
        await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    ).scalar_one_or_none()
    if not pp:
        return ""
    paper = (
        await db.execute(select(Paper).where(Paper.id == pp.paper_id))
    ).scalar_one_or_none()
    return paper.title if paper else ""


async def _build_claim_response(db: AsyncSession, claim: Claim) -> ClaimResponse:
    evidence = []
    for ev in claim.evidence_entries:
        title = await _paper_title(db, ev.project_paper_id)
        evidence.append(
            ClaimEvidenceResponse(
                id=str(ev.id),
                project_paper_id=str(ev.project_paper_id),
                paper_title=title,
                polarity=ev.polarity,
                snippet=ev.snippet,
            )
        )
    return ClaimResponse(
        id=str(claim.id),
        canonical_text=claim.canonical_text,
        claim_type=claim.claim_type,
        support_count=claim.support_count,
        contradict_count=claim.contradict_count,
        neutral_count=claim.neutral_count,
        confidence=claim.confidence,
        field_origin=claim.field_origin,
        source_type=claim.source_type,
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{project_id}/claims", response_model=ClaimListResponse)
async def list_claims(
    project_id: str,
    claim_type: str | None = None,
    sort: str = "created_at",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClaimListResponse:
    """List claims for a project with optional ?claim_type= and ?sort= filters."""
    pid = uuid.UUID(project_id)
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    stmt = select(Claim).where(Claim.project_id == pid)
    if claim_type:
        stmt = stmt.where(Claim.claim_type == claim_type)
    if sort == "confidence":
        # confidence order: high > medium > low
        from sqlalchemy import case

        conf_order = case(
            (Claim.confidence == "high", 0),
            (Claim.confidence == "medium", 1),
            else_=2,
        )
        stmt = stmt.order_by(conf_order, Claim.created_at.desc())
    else:
        stmt = stmt.order_by(Claim.created_at.desc())

    claims = (await db.execute(stmt)).scalars().all()
    items = [await _build_claim_response(db, c) for c in claims]
    return ClaimListResponse(items=items, total=len(items))


@router.get("/{project_id}/claims:aggregate", response_model=ClaimAggregateResponse)
async def aggregate_claims(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClaimAggregateResponse:
    """Return count of claims by type for the project's header chips."""
    pid = uuid.UUID(project_id)
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    rows = (
        await db.execute(
            select(Claim.claim_type, func.count().label("n"))
            .where(Claim.project_id == pid)
            .group_by(Claim.claim_type)
        )
    ).all()
    counts = {r.claim_type: r.n for r in rows}
    return ClaimAggregateResponse(
        support=counts.get("support", 0),
        contradict=counts.get("contradict", 0),
        mixed=counts.get("mixed", 0),
        weak=counts.get("weak", 0),
    )


@router.get("/{project_id}/claims/{claim_id}", response_model=ClaimResponse)
async def get_claim(
    project_id: str,
    claim_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClaimResponse:
    """Get a single claim with full evidence list."""
    pid = uuid.UUID(project_id)
    cid = uuid.UUID(claim_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    claim = (
        await db.execute(select(Claim).where(Claim.id == cid, Claim.project_id == pid))
    ).scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Claim not found")

    return await _build_claim_response(db, claim)


@router.post("/{project_id}/claims:generate")
async def generate_claims(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Start claim synthesis as a background job. Returns job info immediately."""
    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    matrix_count = (
        await db.execute(
            select(func.count())
            .select_from(LiteratureMatrixRow)
            .where(LiteratureMatrixRow.project_id == pid)
        )
    ).scalar()
    if (matrix_count or 0) < 1:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_MATRIX",
                "message": "Need at least 1 matrix row to synthesize claims",
                "details": {"current_matrix_rows": matrix_count or 0},
            },
        )

    job = BackgroundJob(
        job_type="claim_generate",
        project_id=pid,
        user_id=user.id,
        status="pending",
        total=matrix_count or 0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    asyncio.ensure_future(_run_claim_job(job.id, pid))

    return {"job_id": str(job.id), "status": "running", "total": matrix_count or 0}


async def _run_claim_job(job_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Background worker: run claim synthesis."""
    from app.db.session import async_session_factory
    from app.services.claim_synthesis import run_claim_synthesis

    async with async_session_factory() as bg_db:
        job = None
        try:
            job_result = await bg_db.execute(
                select(BackgroundJob).where(BackgroundJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if not job:
                return

            job.status = "running"
            await bg_db.commit()

            total = await run_claim_synthesis(bg_db, project_id)

            job.status = "completed"
            job.result = {"claim_count": total}
            job.progress = total
            job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            await bg_db.commit()

        except Exception as exc:
            logger.exception("Background claim job failed: %s", exc)
            try:
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)[:500]
                    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
                    await bg_db.commit()
            except Exception:
                pass
