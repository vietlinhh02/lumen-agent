"""Tool: detect_gaps — detect evidence-based research gaps from matrix rows."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.ai.provider import get_provider
from app.db.models import LiteratureMatrixRow
from app.services.gap_detection import upsert_gaps, validate_evidence_ids

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)

_MIN_MATRIX_ROWS = 5


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    max_gaps = args.get("max_gaps", 5)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "gaps",
                "status": "running",
                "percent": 0,
                "label": "Detecting gaps",
            }
        )

    # Load matrix rows
    mr_stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == project_id)
    matrix_rows = (await db.execute(mr_stmt)).scalars().all()

    if len(matrix_rows) < _MIN_MATRIX_ROWS:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "gaps",
                    "status": "failed",
                    "percent": 0,
                    "label": "Not enough matrix rows",
                }
            )
        return {
            "gaps_created": 0,
            "status": "failed",
            "error": f"need >= {_MIN_MATRIX_ROWS} matrix rows, got {len(matrix_rows)}",
        }

    # Load valid project_paper_ids
    valid_pp_ids = await validate_evidence_ids(
        db, project_id, [r.project_paper_id for r in matrix_rows]
    )

    # Group by method/dataset for richer LLM context
    by_method: dict[str, list] = defaultdict(list)
    for r in matrix_rows:
        m = (r.method or "").strip().lower()
        if m and m != "not specified":
            by_method[m].append(r)

    method_summary = {
        method: [
            {
                "project_paper_id": str(r.project_paper_id),
                "key_result": r.key_result,
                "limitation": r.limitation,
            }
            for r in rows[:3]
        ]
        for method, rows in by_method.items()
    }

    # Ask LLM for gaps
    system = (
        "You are a research gap analyst. Identify 2-5 evidence-backed research gaps "
        "from the literature matrix rows. Each gap must reference at least one paper "
        "(by project_paper_id) and explain what is missing. Return JSON with 'gaps' list. "
        "Each gap: title, description, suggested_direction, evidence_summary, "
        "evidence_paper_ids (list), confidence (high/medium/low)."
    )
    user_msg = (
        f"Project ID: {project_id}\n\n"
        f"Matrix rows ({len(matrix_rows)} total):\n"
        f"{json.dumps([{'project_paper_id': str(r.project_paper_id), 'method': r.method, 'dataset_or_context': r.dataset_or_context, 'key_result': r.key_result, 'limitation': r.limitation} for r in matrix_rows], indent=2, default=str)}\n\n"
        f"Method clusters:\n{json.dumps(method_summary, indent=2, default=str)}\n\n"
        f"Valid project_paper_ids: {json.dumps([str(pid) for pid in valid_pp_ids])}\n"
    )

    try:
        provider = get_provider()
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            schema={
                "type": "object",
                "properties": {
                    "gaps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "suggested_direction": {"type": "string"},
                                "evidence_summary": {"type": "string"},
                                "evidence_paper_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                            },
                            "required": ["title", "description", "evidence_paper_ids"],
                        },
                    },
                },
                "required": ["gaps"],
            },
            system=system,
            tool_name="gap_detection",
            max_tokens=3000,
        )
    except Exception as exc:
        logger.warning("Gap detection LLM call failed: %s", exc)
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "gaps",
                    "status": "failed",
                    "percent": 0,
                    "label": str(exc),
                }
            )
        return {"gaps_created": 0, "status": "failed", "error": str(exc)[:200]}

    raw_gaps = result.get("gaps", [])
    validated: list[dict] = []
    for g in raw_gaps[:max_gaps]:
        try:
            ev_ids = [UUID(i) if isinstance(i, str) else i for i in g.get("evidence_paper_ids", [])]
        except (ValueError, TypeError):
            continue
        valid_ids = [eid for eid in ev_ids if eid in valid_pp_ids]
        if not valid_ids:
            continue
        validated.append(
            {
                "title": g.get("title", "Untitled gap"),
                "description": g.get("description", ""),
                "suggested_direction": g.get("suggested_direction", ""),
                "evidence_summary": g.get("evidence_summary", ""),
                "confidence": g.get("confidence", "medium"),
                "evidence": [
                    {
                        "project_paper_id": eid,
                        "evidence_type": "limitation",
                        "note": g.get("evidence_summary", ""),
                    }
                    for eid in valid_ids
                ],
            }
        )

    if validated:
        try:
            saved = await upsert_gaps(db, project_id, validated)
        except Exception as exc:
            logger.error("Failed to persist gaps: %s", exc)
            if runner:
                await runner.emit(
                    {
                        "type": "progress",
                        "step": "gaps",
                        "status": "failed",
                        "percent": 0,
                        "label": str(exc),
                    }
                )
            return {"gaps_created": 0, "status": "failed", "error": str(exc)[:200]}
    else:
        saved = 0

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "gaps",
                "status": "done",
                "percent": 100,
                "label": f"Gaps done: {saved}",
            }
        )

    return {
        "gaps_created": saved,
        "status": "completed",
    }
