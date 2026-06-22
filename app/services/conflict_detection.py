"""Conflict detection from literature matrix rows + full-text evidence."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    CONTRADICTION_DETECTION_CHUNK_SYSTEM,
    CONTRADICTION_DETECTION_CHUNK_USER,
)
from app.ai.provider import get_provider
from app.db.models import ConflictingFinding, LiteratureMatrixRow, ProjectPaper
from app.services.hybrid_retrieval import retrieve_paper_evidence

logger = logging.getLogger(__name__)

_MIN_MATRIX_ROWS = 4
_MAX_CHUNKS_PER_CONFLICT_PAPER = 4
_MAX_CHUNK_CHARS_PER_PAPER = 2000

# Parallel processing constants
_CONFLICT_CONCURRENCY = 5  # Bound by LLM rate limit
_MAX_CONFLICT_GROUPS = 10  # Limit groups to process


# ── Helper Functions ────────────────────────────────────────────────────────


def _dedup_conflicts(conflicts: list[dict]) -> list[dict]:
    """Deduplicate conflicts by (paper_a_id, paper_b_id) pair.

    If the same pair appears multiple times, prefer the one with higher
    confidence. This handles cases where 2+ groups detect the same conflict.
    """
    seen: dict[tuple[str, str], dict] = {}
    for c in conflicts:
        key = (str(c["paper_a_id"]), str(c["paper_b_id"]))
        existing = seen.get(key)
        if existing is None or c.get("confidence") == "high" or c.get("confidence") == "medium" and existing.get("confidence") == "low":
            seen[key] = c
    return list(seen.values())


async def _detect_one_group(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
    shared_context: str,
    group: list,
    valid_pp_ids: set[UUID],
    provider,
    protocol_text: str | None = None,
) -> list[dict]:
    """Detect conflicts for a single candidate group (parallel worker).

    Returns list of validated conflict dicts, or empty list on failure.
    """
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

    # Per-paper retrieval: get top chunks for each paper in the group
    chunk_context = await _build_group_chunk_context(db, project_id, group, shared_context)

    try:
        user_msg = CONTRADICTION_DETECTION_CHUNK_USER.format(
            project_topic=topic,
            protocol_context=protocol_text or "Not provided",
            paper_ids_json=paper_ids_json,
            matrix_rows_json=rows_json,
            chunk_context=chunk_context,
        )
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=CONTRADICTION_DETECTION_CHUNK_SYSTEM,
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
            max_tokens=4000,
        )
        detected = result.get("conflicts", [])
    except Exception as exc:
        logger.warning("Conflict detection failed for group '%s': %s", shared_context[:40], exc)
        return []

    # Validate paper IDs + evidence coverage guards
    conflicts: list[dict] = []
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

        # Guard: shared_context must not be empty
        conflict_shared = c.get("shared_context", shared_context)
        if not conflict_shared or not conflict_shared.strip():
            logger.warning("Conflict has empty shared_context, skipping")
            continue

        # Guard: lower confidence if no chunk evidence was available
        confidence = c.get("confidence", "medium")
        has_chunk_evidence = chunk_context != "No full-text sections available."
        if not has_chunk_evidence and confidence == "high":
            confidence = "medium"
            logger.info("Downgraded conflict confidence to 'medium' — no chunk evidence")

        conflicts.append(
            {
                "title": c.get("title", "Potential conflict"),
                "description": c.get("description", ""),
                "paper_a_id": pa_id,
                "paper_b_id": pb_id,
                "shared_context": conflict_shared,
                "claim_a": c.get("claim_a"),
                "claim_b": c.get("claim_b"),
                "possible_explanation": c.get("possible_explanation"),
                "confidence": confidence,
            }
        )

    return conflicts


async def detect_and_persist_conflicts(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
    protocol_text: str | None = None,
) -> list[dict]:
    """Load matrix rows, group by shared method/dataset, retrieve per-paper
    full-text evidence, detect conflicts via LLM, validate paper IDs,
    persist to conflicting_findings table.

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

    # 5. Detect conflicts via LLM with per-paper chunk evidence
    # Parallel processing: 10 groups × 2s = 20s → ~5s with concurrency=5
    provider = get_provider()
    sem = asyncio.Semaphore(_CONFLICT_CONCURRENCY)

    async def _detect_with_semaphore(ctx: str, grp: list) -> list[dict]:
        """Wrapper to bound concurrency per group."""
        async with sem:
            return await _detect_one_group(
                db=db,
                project_id=project_id,
                topic=topic,
                shared_context=ctx,
                group=grp,
                valid_pp_ids=valid_pp_ids,
                provider=provider,
                protocol_text=protocol_text,
            )

    # Fan out all groups in parallel (bounded by semaphore)
    limited_groups = candidate_groups[:_MAX_CONFLICT_GROUPS]
    tasks = [_detect_with_semaphore(ctx, grp) for ctx, grp in limited_groups]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten results, filter out exceptions
    all_conflicts: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_conflicts.extend(r)
        elif isinstance(r, Exception):
            logger.warning("Group detection raised exception: %s", r)

    # 6. Cross-group deduplication (same paper_a + paper_b pair)
    conflicts = _dedup_conflicts(all_conflicts)
    logger.info(
        "Conflict detection complete: %d groups → %d conflicts (after dedup)",
        len(limited_groups),
        len(conflicts),
    )

    # 7. Persist to DB
    if conflicts:
        await _persist_conflicts(db, project_id, conflicts)

    return _serialize_conflicts(conflicts)


async def _build_group_chunk_context(
    db: AsyncSession,
    project_id: UUID,
    group: list,
    shared_context: str,
) -> str:
    """Retrieve per-paper chunks for a candidate conflict group.

    Builds a context query from shared_context + key_result + limitation +
    "conflicting findings different results" to find relevant evidence.
    """
    parts: list[str] = []
    total_chars = 0

    graph_context = await _build_project_graph_context(db, project_id, shared_context)
    if graph_context != "No knowledge graph context available.":
        parts.append(graph_context)
        total_chars += len(graph_context)

    for row in group:
        pp_id = row.project_paper_id

        # Build query from shared context + row fields
        query_parts = [
            shared_context,
            row.key_result or "",
            row.limitation or "",
            "conflicting findings different results",
        ]
        query = " ".join(p for p in query_parts if p.strip())

        chunks = await retrieve_paper_evidence(
            db,
            pp_id,
            query,
            limit=_MAX_CHUNKS_PER_CONFLICT_PAPER,
            content_types=["method", "results", "limitation", "narrative"],
        )

        if not chunks:
            continue

        paper_parts: list[str] = []
        for c in chunks:
            label = c.section_label or c.content_type or "section"
            block = f"---{label}---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CHARS_PER_PAPER * len(group):
                break
            paper_parts.append(block)
            total_chars += len(block)

        if paper_parts:
            header = f"Paper {str(pp_id)[:8]}:"
            parts.append(header + "\n" + "\n\n".join(paper_parts))

    return "\n\n".join(parts) if parts else "No full-text sections available."


async def _build_project_graph_context(db: AsyncSession, project_id: UUID, query: str) -> str:
    try:
        from app.services.knowledge_graph import build_graph_context

        return await build_graph_context(db, project_id, query=query)
    except Exception as exc:
        logger.warning("Knowledge graph context skipped for conflicts: %s", exc)
        return "No knowledge graph context available."


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
