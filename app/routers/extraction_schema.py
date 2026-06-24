"""REST endpoints for the T4 Custom Extraction Schema Builder.

- ``GET  /{project_id}/extraction-schema``        — effective schema
- ``PUT  /{project_id}/extraction-schema``        — replace schema
- ``POST /{project_id}/extraction-schema:reset``  — revert to defaults
- ``POST /{project_id}/extraction-schema:suggest`` — LLM field suggestions

The router does not write to the matrix — it only manages the schema
definition. The matrix extractor (``matrix_extraction_node``) calls into
``app.services.extraction_schema`` directly to read the effective schema
during extraction.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_provider
from app.core.security import get_current_user
from app.db.models import Project, ProjectPaper, User
from app.db.session import get_db
from app.schemas.extraction_schema import (
    ExtractionField,
    ExtractionSchemaResponse,
    ExtractionSchemaSuggestRequest,
    ExtractionSchemaSuggestResponse,
    ExtractionSchemaUpdateRequest,
)
from app.services.extraction_schema import (
    default_fields,
    get_effective_schema,
    replace_project_schema,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extraction-schema"])


async def _verify_project_owner(
    db: AsyncSession,
    user: User,
    project_id: UUID,
) -> Project:
    stmt = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    project = (await db.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


@router.get(
    "/{project_id}/extraction-schema",
    response_model=ExtractionSchemaResponse,
)
async def get_extraction_schema(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExtractionSchemaResponse:
    """Return the effective extraction schema for a project."""
    await _verify_project_owner(db, user, project_id)
    return await get_effective_schema(db, project_id)


@router.put(
    "/{project_id}/extraction-schema",
    response_model=ExtractionSchemaResponse,
)
async def update_extraction_schema(
    project_id: UUID,
    body: ExtractionSchemaUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExtractionSchemaResponse:
    """Replace the project's extraction schema.

    Body must include all seven reserved keys. The schema version is
    bumped, and any future matrix runs will extract against the new
    fields.
    """
    await _verify_project_owner(db, user, project_id)
    try:
        await replace_project_schema(db, project_id, body.fields)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return await get_effective_schema(db, project_id)


@router.post(
    "/{project_id}/extraction-schema:reset",
    response_model=ExtractionSchemaResponse,
)
async def reset_extraction_schema(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExtractionSchemaResponse:
    """Revert the project to the seven system-default fields."""
    await _verify_project_owner(db, user, project_id)
    try:
        await replace_project_schema(db, project_id, default_fields())
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return await get_effective_schema(db, project_id)


@router.post(
    "/{project_id}/extraction-schema:suggest",
    response_model=ExtractionSchemaSuggestResponse,
)
async def suggest_extraction_schema(
    project_id: UUID,
    body: ExtractionSchemaSuggestRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExtractionSchemaSuggestResponse:
    """Ask the LLM to suggest typed extraction fields for this project.

    Uses the project topic + review protocol + up to 5 sample abstracts
    (or the first 5 saved-paper abstracts if none are supplied) to ground
    the suggestion. The seven reserved fields are always returned first so
    the frontend can build a complete schema editor in one shot.
    """
    from app.ai.prompts import (
        EXTRACTION_SCHEMA_SUGGEST_SYSTEM,
        EXTRACTION_SCHEMA_SUGGEST_USER,
    )
    from app.schemas.extraction_schema import RESERVED_FIELD_KEYS

    project = await _verify_project_owner(db, user, project_id)

    abstracts = (body.sample_abstracts if body else None) or []
    if not abstracts:
        # Pull up to 5 abstracts from saved papers.
        stmt = (
            select(ProjectPaper)
            .where(
                ProjectPaper.project_id == project_id,
                ProjectPaper.status == "saved",
            )
            .limit(5)
        )
        rows = (await db.execute(stmt)).scalars().all()
        abstracts = []
        for pp in rows:
            paper = getattr(pp, "paper", None)
            if paper and paper.abstract:
                abstracts.append(paper.abstract[:600])
            if len(abstracts) >= 5:
                break

    max_fields = body.max_fields if body else 8
    reserved_list = ", ".join(RESERVED_FIELD_KEYS)
    abstracts_block = (
        "\n\n".join(f"- {a}" for a in abstracts[:5])
        if abstracts
        else "No sample abstracts available — suggest based on the project topic and protocol."
    )
    user_msg = EXTRACTION_SCHEMA_SUGGEST_USER.format(
        project_topic=project.topic,
        research_question=project.research_question or "Not specified",
        max_fields=max_fields,
        reserved_keys=reserved_list,
        abstracts_block=abstracts_block,
    )

    try:
        provider = get_provider()
        # We deliberately do NOT pass a JSON schema here — different
        # providers handle nested arrays of objects differently, and
        # ``complete_structured`` with a free-form dict works for the
        # response shapes we accept.
        response = await provider.complete(
            messages=[{"role": "user", "content": user_msg}],
            system=EXTRACTION_SCHEMA_SUGGEST_SYSTEM,
            max_tokens=2048,
        )
        parsed = _parse_suggestion_response(response)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Schema suggestion failed for project %s: %s", project_id, exc)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Schema suggestion failed: {exc}",
        ) from exc

    fields: list[ExtractionField] = []
    seen: set[str] = set()
    # Always emit the seven reserved keys first.
    for f in default_fields():
        if f.key not in seen:
            fields.append(f)
            seen.add(f.key)
    # Then the suggested extras, skipping any key that collides with reserved.
    for f in parsed:
        if f.key in seen or f.key in RESERVED_FIELD_KEYS:
            continue
        if f.type not in ("text", "number", "enum", "multi_select", "boolean", "quote", "citation"):
            continue
        # Enforce the same enum_values invariant.
        if f.type in ("enum", "multi_select") and not f.enum_values:
            continue
        fields.append(f)
        seen.add(f.key)
        if len(fields) - len(RESERVED_FIELD_KEYS) >= max_fields:
            break

    return ExtractionSchemaSuggestResponse(
        fields=fields,
        rationale=parsed[0].description if parsed else None,
    )


def _parse_suggestion_response(raw: str) -> list[ExtractionField]:
    """Tolerantly parse the LLM's JSON response into ExtractionField objects."""
    text = raw.strip()
    # Strip <think>…</think> blocks that some models leak through.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1].strip()
    # Try to extract the first JSON object/array.
    candidates: list[str] = []
    if text.startswith("{"):
        candidates.append(text)
    if text.startswith("["):
        candidates.append(text)
    # Find the first {...} or [...] block.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        idx = text.find(open_ch)
        if idx == -1:
            continue
        depth = 0
        for i in range(idx, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    candidates.append(text[idx : i + 1])
                    break

    parsed: object | None = None
    for cand in candidates:
        try:
            parsed = json.loads(cand)
            break
        except Exception:
            continue
    if parsed is None:
        return []

    # Accept either {"fields": [...]} or a bare list.
    if isinstance(parsed, dict):
        items = parsed.get("fields") or parsed.get("suggestions") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        return []
    if not isinstance(items, list):
        return []

    out: list[ExtractionField] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(ExtractionField.model_validate(item))
        except Exception:
            continue
    return out
