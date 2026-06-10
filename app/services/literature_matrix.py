"""CRUD operations for literature_matrix_rows."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LiteratureMatrixRow, ProjectPaper

logger = logging.getLogger(__name__)


async def get_existing_paper_ids(
    db: AsyncSession,
    project_id: UUID,
) -> set[UUID]:
    """Return project_paper_ids that already have matrix rows."""
    stmt = select(LiteratureMatrixRow.project_paper_id).where(
        LiteratureMatrixRow.project_id == project_id
    )
    rows = (await db.execute(stmt)).scalars().all()
    return set(rows)


async def upsert_rows(
    db: AsyncSession,
    project_id: UUID,
    rows: list[dict],
) -> int:
    """Upsert matrix rows atomically. Returns count of rows inserted/updated.

    Each dict in ``rows`` must have:
        - project_paper_id: UUID
        - research_problem, method, dataset_or_context, key_result,
          limitation, contribution, relevance: str | None
        - extraction_confidence: str ('high', 'medium', 'low')
    """
    if not rows:
        return 0

    for row in rows:
        stmt = (
            pg_insert(LiteratureMatrixRow)
            .values(
                project_id=project_id,
                project_paper_id=row["project_paper_id"],
                research_problem=row.get("research_problem"),
                method=row.get("method"),
                dataset_or_context=row.get("dataset_or_context"),
                key_result=row.get("key_result"),
                limitation=row.get("limitation"),
                contribution=row.get("contribution"),
                relevance=row.get("relevance"),
                extraction_confidence=row.get("extraction_confidence", "medium"),
                created_by="ai",
            )
            .on_conflict_do_update(
                index_elements=["project_paper_id"],
                set_={
                    "research_problem": row.get("research_problem"),
                    "method": row.get("method"),
                    "dataset_or_context": row.get("dataset_or_context"),
                    "key_result": row.get("key_result"),
                    "limitation": row.get("limitation"),
                    "contribution": row.get("contribution"),
                    "relevance": row.get("relevance"),
                    "extraction_confidence": row.get("extraction_confidence", "medium"),
                    "created_by": "ai",
                },
            )
        )
        await db.execute(stmt)

    await db.commit()
    return len(rows)


async def get_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[LiteratureMatrixRow]:
    """Return all matrix rows for a project with paper metadata loaded."""
    from sqlalchemy.orm import selectinload

    stmt = (
        select(LiteratureMatrixRow)
        .options(selectinload(LiteratureMatrixRow.project_paper).selectinload(ProjectPaper.paper))
        .where(LiteratureMatrixRow.project_id == project_id)
        .order_by(LiteratureMatrixRow.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_row(
    db: AsyncSession,
    project_id: UUID,
    row_id: UUID,
) -> bool:
    """Delete a matrix row. Returns True if deleted."""
    stmt = select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.id == row_id,
        LiteratureMatrixRow.project_id == project_id,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
