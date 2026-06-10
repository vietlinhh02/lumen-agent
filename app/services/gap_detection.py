"""CRUD operations for research_gaps and gap_evidence tables."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import GapEvidence, ProjectPaper, ResearchGap

logger = logging.getLogger(__name__)


async def upsert_gaps(
    db: AsyncSession,
    project_id: UUID,
    gaps: list[dict],
) -> int:
    """Delete existing gaps for project, insert new ones with evidence.

    Each dict in ``gaps`` must have:
        - title, description, suggested_direction, evidence_summary: str
        - confidence: 'high' | 'medium' | 'low'
        - evidence: list[{project_paper_id: UUID, evidence_type: str, note: str}]
    Returns count of gaps inserted.
    """
    if not gaps:
        return 0

    # Delete old gaps (cascade deletes gap_evidence)
    await db.execute(delete(ResearchGap).where(ResearchGap.project_id == project_id))

    count = 0
    for gap_data in gaps:
        gap = ResearchGap(
            project_id=project_id,
            title=gap_data["title"],
            description=gap_data["description"],
            suggested_direction=gap_data["suggested_direction"],
            evidence_summary=gap_data["evidence_summary"],
            confidence=gap_data.get("confidence", "medium"),
        )
        db.add(gap)
        await db.flush()  # get gap.id

        for ev in gap_data.get("evidence", []):
            evidence = GapEvidence(
                gap_id=gap.id,
                project_paper_id=ev["project_paper_id"],
                evidence_type=ev["evidence_type"],
                note=ev["note"],
            )
            db.add(evidence)

        count += 1

    await db.commit()
    return count


async def get_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[ResearchGap]:
    """Load gaps with evidence_entries eager-loaded."""
    stmt = (
        select(ResearchGap)
        .options(selectinload(ResearchGap.evidence_entries))
        .where(ResearchGap.project_id == project_id)
        .order_by(ResearchGap.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_gap(
    db: AsyncSession,
    project_id: UUID,
    gap_id: UUID,
) -> bool:
    """Delete single gap. Returns True if deleted."""
    stmt = select(ResearchGap).where(
        ResearchGap.id == gap_id,
        ResearchGap.project_id == project_id,
    )
    gap = (await db.execute(stmt)).scalar_one_or_none()
    if not gap:
        return False
    await db.delete(gap)
    await db.commit()
    return True


async def validate_evidence_ids(
    db: AsyncSession,
    project_id: UUID,
    evidence_paper_ids: list[UUID],
) -> set[UUID]:
    """Return the subset of evidence_paper_ids that are valid saved project_papers."""
    if not evidence_paper_ids:
        return set()
    stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
        ProjectPaper.id.in_(evidence_paper_ids),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return set(rows)
