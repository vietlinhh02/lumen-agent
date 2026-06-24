"""REST endpoints for T3 evidence ratings (accepted / weak / wrong per chunk).

Ratings are PRIVATE per user: every query and the upsert key are scoped to the
authenticated user, so two reviewers never overwrite each other's marks.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import EvidenceRating, Project, User
from app.db.session import get_db
from app.schemas.evidence import (
    EvidenceRatingCreate,
    EvidenceRatingListResponse,
    EvidenceRatingResponse,
    EvidenceRatingSummary,
    SourceKind,
)

router = APIRouter(tags=["evidence-ratings"])


async def _verify_project_owner(db: AsyncSession, user: User, project_id: UUID) -> Project:
    """Load project and verify ownership. Raises 404 if not found or not owned."""
    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.owner_id == user.id)
        )
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _to_response(r: EvidenceRating) -> EvidenceRatingResponse:
    return EvidenceRatingResponse(
        id=r.id,
        source_kind=r.source_kind,
        source_id=r.source_id,
        project_paper_id=r.project_paper_id,
        chunk_id=r.chunk_id,
        rating=r.rating,
        note=r.note,
        updated_at=r.updated_at,
    )


@router.post("/{project_id}/evidence-ratings", response_model=EvidenceRatingResponse)
async def upsert_evidence_rating(
    project_id: UUID,
    body: EvidenceRatingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EvidenceRatingResponse:
    """Create or update this user's rating for one chunk under one source."""
    await _verify_project_owner(db, user, project_id)

    existing = (
        await db.execute(
            select(EvidenceRating).where(
                EvidenceRating.user_id == user.id,
                EvidenceRating.source_kind == body.source_kind,
                EvidenceRating.source_id == body.source_id,
                EvidenceRating.chunk_id == body.chunk_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.rating = body.rating
        existing.note = body.note
        existing.project_paper_id = body.project_paper_id
        rating = existing
    else:
        rating = EvidenceRating(
            project_id=project_id,
            user_id=user.id,
            source_kind=body.source_kind,
            source_id=body.source_id,
            project_paper_id=body.project_paper_id,
            chunk_id=body.chunk_id,
            rating=body.rating,
            note=body.note,
        )
        db.add(rating)

    await db.commit()
    await db.refresh(rating)
    return _to_response(rating)


@router.get("/{project_id}/evidence-ratings", response_model=EvidenceRatingListResponse)
async def list_evidence_ratings(
    project_id: UUID,
    source_kind: SourceKind,
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EvidenceRatingListResponse:
    """Return this user's ratings for one claim surface (drawer load)."""
    await _verify_project_owner(db, user, project_id)

    rows = (
        await db.execute(
            select(EvidenceRating).where(
                EvidenceRating.project_id == project_id,
                EvidenceRating.user_id == user.id,
                EvidenceRating.source_kind == source_kind,
                EvidenceRating.source_id == source_id,
            )
        )
    ).scalars().all()
    return EvidenceRatingListResponse(items=[_to_response(r) for r in rows])


@router.get("/{project_id}/evidence-ratings/summary", response_model=EvidenceRatingSummary)
async def evidence_rating_summary(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EvidenceRatingSummary:
    """Tally this user's ratings across the whole project (header chip)."""
    await _verify_project_owner(db, user, project_id)

    rows = (
        await db.execute(
            select(EvidenceRating.rating, func.count())
            .where(
                EvidenceRating.project_id == project_id,
                EvidenceRating.user_id == user.id,
            )
            .group_by(EvidenceRating.rating)
        )
    ).all()
    counts = {rating: count for rating, count in rows}
    return EvidenceRatingSummary(
        accepted=counts.get("accepted", 0),
        weak=counts.get("weak", 0),
        wrong=counts.get("wrong", 0),
    )
