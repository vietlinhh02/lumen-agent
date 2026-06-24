"""T7 Claim Synthesis service.

Lifts first-class Claim objects from existing ConflictingFinding and
LiteratureMatrixRow data.  Phase-1 slice: read-only extraction with no
clustering or LLM canonicalization.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Claim,
    ClaimEvidence,
    ConflictingFinding,
    LiteratureMatrixRow,
    Paper,
    ProjectPaper,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_paper_title(db: AsyncSession, project_paper_id: uuid.UUID) -> str:
    """Return paper title for a given project_paper_id (empty string if not found)."""
    pp = (
        await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    ).scalar_one_or_none()
    if not pp:
        return ""
    paper = (
        await db.execute(select(Paper).where(Paper.id == pp.paper_id))
    ).scalar_one_or_none()
    return paper.title if paper else ""


def _map_confidence(extraction_confidence: str) -> str:
    """Map matrix extraction_confidence to claim confidence."""
    if extraction_confidence == "high":
        return "high"
    if extraction_confidence == "low":
        return "low"
    return "medium"


# ---------------------------------------------------------------------------
# Lift: conflicts → claims
# ---------------------------------------------------------------------------


async def lift_claims_from_conflicts(
    db: AsyncSession, project_id: uuid.UUID
) -> list[Claim]:
    """Extract Claim rows from existing ConflictingFinding records.

    Each conflict produces two Claim rows:
      - claim_a text → support for paper_a, contradict for paper_b
      - claim_b text → support for paper_b, contradict for paper_a
    Both get claim_type='contradict' since they are part of a contradiction.
    """
    stmt = select(ConflictingFinding).where(ConflictingFinding.project_id == project_id)
    conflicts = (await db.execute(stmt)).scalars().all()

    results: list[Claim] = []
    for cf in conflicts:
        for text, own_paper_id, other_paper_id, field in [
            (cf.claim_a, cf.paper_a_id, cf.paper_b_id, "claim_a"),
            (cf.claim_b, cf.paper_b_id, cf.paper_a_id, "claim_b"),
        ]:
            if not text or not text.strip():
                continue

            claim = Claim(
                project_id=project_id,
                canonical_text=text.strip(),
                claim_type="contradict",
                support_count=1,
                contradict_count=1,
                neutral_count=0,
                confidence=cf.confidence or "medium",
                field_origin=field,
                source_type="conflict",
            )
            db.add(claim)
            await db.flush()

            # Supporting evidence: own paper
            db.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    project_paper_id=own_paper_id,
                    polarity="support",
                    snippet=text[:500] if text else None,
                )
            )
            # Contradicting evidence: the other paper
            db.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    project_paper_id=other_paper_id,
                    polarity="contradict",
                    snippet=None,
                )
            )
            results.append(claim)

    return results


# ---------------------------------------------------------------------------
# Lift: matrix rows → claims
# ---------------------------------------------------------------------------


async def lift_claims_from_matrix(
    db: AsyncSession, project_id: uuid.UUID
) -> list[Claim]:
    """Extract Claim rows from LiteratureMatrixRow.key_result and .limitation fields."""
    stmt = (
        select(LiteratureMatrixRow)
        .where(LiteratureMatrixRow.project_id == project_id)
    )
    rows = (await db.execute(stmt)).scalars().all()

    results: list[Claim] = []
    for row in rows:
        for text, field, ctype in [
            (row.key_result, "key_result", "support"),
            (row.limitation, "limitation", "weak"),
        ]:
            if not text or not text.strip():
                continue

            confidence = _map_confidence(row.extraction_confidence or "medium")
            claim = Claim(
                project_id=project_id,
                canonical_text=text.strip(),
                claim_type=ctype,
                support_count=1,
                contradict_count=0,
                neutral_count=0,
                confidence=confidence,
                field_origin=field,
                source_type="matrix",
            )
            db.add(claim)
            await db.flush()

            db.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    project_paper_id=row.project_paper_id,
                    polarity="support",
                    snippet=text[:500] if text else None,
                )
            )
            results.append(claim)

    return results


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_claim_synthesis(db: AsyncSession, project_id: uuid.UUID) -> int:
    """Main entry point: clear existing claims for project, then lift from all sources.

    Returns the total number of claims created.
    """
    # Delete existing claims (cascades to claim_evidence)
    await db.execute(delete(Claim).where(Claim.project_id == project_id))

    conflict_claims = await lift_claims_from_conflicts(db, project_id)
    matrix_claims = await lift_claims_from_matrix(db, project_id)

    await db.commit()

    total = len(conflict_claims) + len(matrix_claims)
    logger.info(
        "Claim synthesis for project %s: %d from conflicts, %d from matrix = %d total",
        project_id,
        len(conflict_claims),
        len(matrix_claims),
        total,
    )
    return total
