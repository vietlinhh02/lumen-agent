"""CRUD operations for literature_matrix_rows."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LiteratureMatrixRow, ProjectPaper

logger = logging.getLogger(__name__)

# Reserved field keys that can be addressed by their literal column.
RESERVED_FIELD_KEYS: tuple[str, ...] = (
    "research_problem",
    "method",
    "dataset_or_context",
    "key_result",
    "limitation",
    "contribution",
    "relevance",
    "extraction_confidence",
    "created_by",
    "paper_title",
)


def build_content_hash(project_paper_id: UUID, paper_updated_at: datetime | None) -> str:
    """Build a short content hash for matrix cache invalidation."""
    updated_at = paper_updated_at.isoformat() if paper_updated_at else "unknown"
    raw = f"{project_paper_id}:{updated_at}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


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
        - custom_fields: dict (T4 — project-defined typed field values,
          keyed by schema ``key``). May be empty.
        - content_hash: str | None
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
                custom_fields=row.get("custom_fields") or {},
                content_hash=row.get("content_hash"),
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
                    "custom_fields": row.get("custom_fields") or {},
                    "content_hash": row.get("content_hash"),
                    "extraction_confidence": row.get("extraction_confidence", "medium"),
                    "created_by": "ai",
                },
            )
        )
        await db.execute(stmt)

        # NOTE: We intentionally do NOT auto-set ``ProjectPaper.relevance_label``
        # to "low" here. ``extraction_confidence`` measures extraction quality
        # (did we manage to fill in the matrix fields?), not topic relevance.
        # A user-saved paper should not silently flip to "low" because the LLM
        # had a hard time parsing its abstract. If a paper is genuinely
        # off-topic, that decision belongs to the user (via the review-protocol
        # exclusion workflow), not to the matrix extractor.

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


async def bulk_delete_by_confidence(
    db: AsyncSession,
    project_id: UUID,
    confidence: str = "low",
) -> int:
    """Delete every matrix row in ``project_id`` whose extraction_confidence
    matches ``confidence``. Returns the number of rows deleted.

    Used by the "Remove Low" quick action so users can clear out rows whose
    extraction the LLM admitted was poor, before re-generating. Only deletes
    the matrix row — the underlying saved paper is left in place so the user
    can re-generate the matrix later.
    """
    from sqlalchemy import delete as sa_delete

    stmt = sa_delete(LiteratureMatrixRow).where(
        LiteratureMatrixRow.project_id == project_id,
        LiteratureMatrixRow.extraction_confidence == confidence,
    )
    result = await db.execute(stmt)
    await db.commit()
    # SQLAlchemy 2.x: ``result.rowcount`` reflects affected rows.
    return int(result.rowcount or 0)


async def count_by_confidence(
    db: AsyncSession,
    project_id: UUID,
    confidence: str,
) -> int:
    """Return the number of matrix rows in ``project_id`` whose
    extraction_confidence matches ``confidence``."""
    from sqlalchemy import func

    stmt = select(func.count(LiteratureMatrixRow.id)).where(
        LiteratureMatrixRow.project_id == project_id,
        LiteratureMatrixRow.extraction_confidence == confidence,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


# ── T4: filter / aggregate over typed fields ────────────────────────────


def _coerce_for_compare(value: Any) -> str | float | bool | None:
    """Coerce a filter value to a scalar the SQL / Python comparison can use."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value)


def _value_to_python(field: str, raw: Any) -> Any:
    """Coerce a stored value to a Python value suitable for in-Python compare."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return raw


def _field_to_value(row: LiteratureMatrixRow, field: str) -> Any:
    """Resolve a field key to its stored value on a row (reserved col or custom JSON key)."""
    if field in RESERVED_FIELD_KEYS:
        return getattr(row, field, None)
    return (row.custom_fields or {}).get(field)


async def filter_rows(
    db: AsyncSession,
    project_id: UUID,
    field: str,
    op: str,
    value: Any,
) -> list[str]:
    """Return row IDs that match ``field op value``.

    Implementation note: we load the project's matrix rows once and
    evaluate the predicate in Python. This is fine for MVP-sized corpora
    (≤ 200 rows per project) and avoids per-row JSONB access. A
    GIN-indexed SQL version is a future optimization once corpora grow.
    """
    if not field:
        raise ValueError("`field` is required")

    rows = await get_by_project(db, project_id)
    hits: list[str] = []
    # For ``op='in'`` keep the list shape — we need to test membership
    # against each element, not join them. The other ops can use the
    # scalar coercion path.
    if op == "in":
        target = list(value) if value is not None else []
    else:
        target = _coerce_for_compare(value)

    for row in rows:
        candidate = _value_to_python(field, _field_to_value(row, field))
        if candidate is None and op in ("eq", "neq", "contains", "in"):
            if op == "eq" and target is None:
                hits.append(str(row.id))
            continue
        if op == "eq":
            if candidate == target:
                hits.append(str(row.id))
        elif op == "neq":
            if candidate != target:
                hits.append(str(row.id))
        elif op == "contains":
            if isinstance(candidate, str) and isinstance(target, str) and target in candidate:
                hits.append(str(row.id))
        elif op in ("gt", "gte", "lt", "lte"):
            try:
                cand_num = float(candidate)
                tgt_num = float(target)
            except (TypeError, ValueError):
                continue
            if (
                op == "gt"
                and cand_num > tgt_num
                or op == "gte"
                and cand_num >= tgt_num
                or op == "lt"
                and cand_num < tgt_num
                or op == "lte"
                and cand_num <= tgt_num
            ):
                hits.append(str(row.id))
        elif op == "in" and isinstance(target, list) and candidate in target:
            hits.append(str(row.id))
    return hits


async def aggregate_by_field(
    db: AsyncSession,
    project_id: UUID,
    field: str,
    group_by: str | None = None,
) -> tuple[dict[str, int], int]:
    """Aggregate matrix rows by ``field`` value, optionally cross-tabulated
    against ``group_by``.

    Returns ``(buckets, total)`` where ``buckets`` maps the
    ``"<field_value>"`` (or ``"<field_value>|<group_value>"``) key to a
    count. ``total`` is the number of rows included in the aggregation
    (rows where the field is missing are excluded from the buckets but
    still count toward ``total``).
    """
    if not field:
        raise ValueError("`field` is required")

    rows = await get_by_project(db, project_id)
    counter: Counter[str] = Counter()
    for row in rows:
        fval = _value_to_python(field, _field_to_value(row, field))
        if fval is None or fval == "" or fval == []:
            continue
        fkey = str(fval)
        if group_by:
            gval = _value_to_python(group_by, _field_to_value(row, group_by))
            if gval is None or gval == "":
                continue
            counter[f"{fkey}|{gval}"] += 1
        else:
            counter[fkey] += 1
    return dict(counter), len(rows)


def field_coverage(
    rows: list[LiteratureMatrixRow],
    fields: list,  # list[ExtractionField]
) -> dict[str, Any]:
    """Compute per-field population coverage for the audit + matrix UI.

    For each schema field, returns:
      - ``rows_total`` — number of rows considered
      - ``populated`` — rows where the value is non-empty
      - ``coverage_rate`` — populated / rows_total
    Custom fields are read from ``custom_fields``; reserved fields are
    read from the top-level column.
    """
    if not rows:
        return {"rows_total": 0, "fields": []}

    out: list[dict[str, Any]] = []
    for f in fields:
        is_reserved = f.key in RESERVED_FIELD_KEYS
        populated = 0
        for r in rows:
            v = _field_to_value(r, f.key)
            if v is None or v == "" or v == []:
                continue
            populated += 1
        out.append(
            {
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "is_reserved": is_reserved,
                "required": getattr(f, "required", False),
                "populated": populated,
                "rows_total": len(rows),
                "coverage_rate": (round(populated / len(rows), 3) if rows else 0),
            }
        )
    return {"rows_total": len(rows), "fields": out}
