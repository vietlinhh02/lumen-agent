"""Conflict detection from literature matrix rows."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import CONTRADICTION_DETECTION_SYSTEM, CONTRADICTION_DETECTION_USER
from app.ai.provider import get_provider
from app.db.models import ConflictingFinding, LiteratureMatrixRow, ProjectPaper

logger = logging.getLogger(__name__)

_MIN_MATRIX_ROWS = 4


async def detect_and_persist_conflicts(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
) -> list[dict]:
    """Load matrix rows, group by shared method/dataset, detect conflicts via LLM,
    validate paper IDs, persist to conflicting_findings table.

    Returns list of conflict dicts for state.
    """
    # 1. Load matrix rows
    stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == project_id)
    rows = (await db.execute(stmt)).scalars().all()

    if len(rows) < _MIN_MATRIX_ROWS:
        logger.info("Too few matrix rows (%d) for conflict detection", len(rows))
        return []

    # 2. Load valid project_paper_ids
    pp_stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(pp_stmt)).scalars().all())

    # 3. Group rows by shared method or dataset
    by_method: dict[str, list] = defaultdict(list)
    by_dataset: dict[str, list] = defaultdict(list)

    for row in rows:
        method = (row.method or "").strip().lower()
        dataset = (row.dataset_or_context or "").strip().lower()
        if method and method != "not specified":
            by_method[method].append(row)
        if dataset and dataset != "not specified":
            by_dataset[dataset].append(row)

    # 4. Collect candidate groups (2+ rows with same method or dataset)
    candidate_groups: list[tuple[str, list]] = []
    for key, group in by_method.items():
        if len(group) >= 2:
            candidate_groups.append((f"method: {key}", group))
    for key, group in by_dataset.items():
        if len(group) >= 2:
            candidate_groups.append((f"dataset: {key}", group))

    if not candidate_groups:
        logger.info("No shared method/dataset groups found for conflict detection")
        return []

    # 5. Detect conflicts via LLM
    provider = get_provider()
    conflicts: list[dict] = []

    for shared_context, group in candidate_groups[:10]:  # limit groups
        paper_ids_json = json.dumps([str(r.project_paper_id) for r in group])
        rows_json = json.dumps(
            [
                {
                    "project_paper_id": str(r.project_paper_id),
                    "method": r.method,
                    "dataset_or_context": r.dataset_or_context,
                    "key_result": r.key_result,
                    "limitation": r.limitation,
                }
                for r in group
            ],
            indent=2,
        )

        try:
            user_msg = CONTRADICTION_DETECTION_USER.format(
                project_topic=topic,
                paper_ids_json=paper_ids_json,
                matrix_rows_json=rows_json,
            )
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                system=CONTRADICTION_DETECTION_SYSTEM,
                schema={
                    "type": "object",
                    "properties": {
                        "conflicts": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "paper_a_id": {"type": "string"},
                                    "paper_b_id": {"type": "string"},
                                    "shared_context": {"type": "string"},
                                    "claim_a": {"type": "string"},
                                    "claim_b": {"type": "string"},
                                    "possible_explanation": {"type": "string"},
                                    "confidence": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"],
                                    },
                                },
                                "required": ["title", "description", "paper_a_id", "paper_b_id"],
                            },
                        }
                    },
                },
                tool_name="conflict_detection",
                max_tokens=2000,
            )
            detected = result.get("conflicts", [])
        except Exception as exc:
            logger.warning("Conflict detection failed for group '%s': %s", shared_context[:40], exc)
            continue

        # 6. Validate paper IDs and persist
        for c in detected:
            try:
                pa_id = UUID(c["paper_a_id"])
                pb_id = UUID(c["paper_b_id"])
            except (ValueError, KeyError):
                logger.warning("Invalid paper IDs in conflict: %s", c)
                continue

            if pa_id not in valid_pp_ids or pb_id not in valid_pp_ids:
                logger.warning("Conflict references invalid project_paper IDs, skipping")
                continue

            conflicts.append(
                {
                    "title": c.get("title", "Potential conflict"),
                    "description": c.get("description", ""),
                    "paper_a_id": pa_id,
                    "paper_b_id": pb_id,
                    "shared_context": c.get("shared_context", shared_context),
                    "claim_a": c.get("claim_a"),
                    "claim_b": c.get("claim_b"),
                    "possible_explanation": c.get("possible_explanation"),
                    "confidence": c.get("confidence", "medium"),
                }
            )

    # 7. Persist to DB
    if conflicts:
        await _persist_conflicts(db, project_id, conflicts)

    return _serialize_conflicts(conflicts)


async def _persist_conflicts(
    db: AsyncSession,
    project_id: UUID,
    conflicts: list[dict],
) -> None:
    """Delete old conflicts for project, insert new ones."""
    await db.execute(delete(ConflictingFinding).where(ConflictingFinding.project_id == project_id))
    for c in conflicts:
        finding = ConflictingFinding(
            project_id=project_id,
            title=c["title"],
            description=c["description"],
            paper_a_id=c["paper_a_id"],
            paper_b_id=c["paper_b_id"],
            shared_context=c.get("shared_context"),
            claim_a=c.get("claim_a"),
            claim_b=c.get("claim_b"),
            possible_explanation=c.get("possible_explanation"),
            confidence=c.get("confidence", "medium"),
        )
        db.add(finding)
    await db.commit()


def _serialize_conflicts(conflicts: list[dict]) -> list[dict]:
    """Convert UUID fields to strings for JSON serialization."""
    return [{k: str(v) if isinstance(v, UUID) else v for k, v in c.items()} for c in conflicts]


async def get_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[ConflictingFinding]:
    """Load conflicts for a project."""
    stmt = (
        select(ConflictingFinding)
        .where(ConflictingFinding.project_id == project_id)
        .order_by(ConflictingFinding.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())
