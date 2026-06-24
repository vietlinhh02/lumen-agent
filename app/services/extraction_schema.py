"""T4 Custom Extraction Schema service.

Manages the project-level extraction schema definition and resolves the
"effective schema" used at extraction time (project override merged over
the seven system defaults). Persists to ``ProjectExtractionSchema`` and
returns the schema for callers (router, matrix extractor, schema editor
UI).

The seven reserved keys are treated as system defaults: they are always
present in the effective schema, their ``type`` is locked to ``text``,
and their ``key`` is immutable. New fields can be added, removed,
reordered, and have their ``label``/``description``/``required``
modified freely.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProjectExtractionSchema
from app.schemas.extraction_schema import (
    RESERVED_FIELD_KEYS,
    ExtractionField,
    ExtractionSchemaResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default schema
# ---------------------------------------------------------------------------


def _default_field(key: str) -> dict:
    """Return the canonical default entry for a reserved field key."""
    labels = {
        "research_problem": "Research Problem",
        "method": "Method",
        "dataset_or_context": "Dataset / Context",
        "key_result": "Key Result",
        "limitation": "Limitation",
        "contribution": "Contribution",
        "relevance": "Relevance",
    }
    descriptions = {
        "research_problem": "What problem the paper addresses.",
        "method": "Main method or approach used.",
        "dataset_or_context": "Dataset, domain, or study setting.",
        "key_result": "Main finding or contribution.",
        "limitation": "Stated or inferred limitation.",
        "contribution": "What the paper uniquely adds to the field.",
        "relevance": "Why this paper matters to the project topic.",
    }
    return {
        "key": key,
        "label": labels[key],
        "type": "text",
        "description": descriptions[key],
        "required": False,
        "enum_values": None,
    }


def default_fields() -> list[ExtractionField]:
    """Return the seven system-default fields in canonical order."""
    return [ExtractionField.model_validate(_default_field(k)) for k in RESERVED_FIELD_KEYS]


def default_field_dicts() -> list[dict]:
    """Same as :func:`default_fields` but as raw dicts (for JSONB storage)."""
    return [_default_field(k) for k in RESERVED_FIELD_KEYS]


# ---------------------------------------------------------------------------
# Effective-schema resolution
# ---------------------------------------------------------------------------


async def get_project_schema_row(
    db: AsyncSession, project_id: UUID
) -> ProjectExtractionSchema | None:
    """Return the persisted schema row for a project (or None if not customized)."""
    stmt = select(ProjectExtractionSchema).where(
        ProjectExtractionSchema.project_id == project_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_effective_schema(
    db: AsyncSession, project_id: UUID
) -> ExtractionSchemaResponse:
    """Return the effective schema for a project.

    If the project has not customized its schema, returns the seven
    defaults with ``is_default=True`` and ``version=1``. Otherwise returns
    the project override merged over the defaults so the seven reserved
    keys are always present.
    """
    row = await get_project_schema_row(db, project_id)
    if row is None:
        return ExtractionSchemaResponse(
            project_id=project_id,
            version=1,
            fields=default_fields(),
            is_default=True,
            created_at=None,
            updated_at=None,
        )
    # Merge: start with defaults, then overlay project entries by key.
    merged: dict[str, dict] = {f.key: f.model_dump() for f in default_fields()}
    for entry in row.fields or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if not key:
            continue
        if key in merged:
            # Reserved key: lock key/type; allow label/description/required override.
            merged[key] = {
                **merged[key],
                **{k: v for k, v in entry.items() if k in ("label", "description", "required")},
                "key": key,
                "type": "text",
                "enum_values": None,
            }
        else:
            # Project-defined field.
            merged[key] = {
                "key": key,
                "label": entry.get("label", key),
                "type": entry.get("type", "text"),
                "description": entry.get("description"),
                "required": bool(entry.get("required", False)),
                "enum_values": entry.get("enum_values"),
            }
    # Preserve the project-specified ordering for project-defined fields
    # by walking the persisted row.fields list, then appending any
    # reserved keys that the project owner did not enumerate (rare).
    ordered_keys: list[str] = []
    seen: set[str] = set()
    for entry in row.fields or []:
        if not isinstance(entry, dict):
            continue
        k = entry.get("key")
        if k and k in merged and k not in seen:
            ordered_keys.append(k)
            seen.add(k)
    for k in RESERVED_FIELD_KEYS:
        if k not in seen:
            ordered_keys.append(k)
            seen.add(k)
    fields = [ExtractionField.model_validate(merged[k]) for k in ordered_keys]
    return ExtractionSchemaResponse(
        project_id=project_id,
        version=row.version,
        fields=fields,
        is_default=False,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Schema mutation
# ---------------------------------------------------------------------------


def _normalize_for_storage(fields: list[ExtractionField]) -> list[dict]:
    """Validate and serialize a list of fields for JSONB storage.

    - All seven reserved keys must be present (with type='text').
    - No duplicate keys.
    - Reserved keys' type is forced to 'text' regardless of input.
    """
    seen: set[str] = set()
    out: list[dict] = []
    reserved_set = set(RESERVED_FIELD_KEYS)

    for f in fields:
        if f.key in seen:
            raise ValueError(f"Duplicate field key: {f.key!r}")
        seen.add(f.key)
        entry = f.model_dump()
        if f.key in reserved_set:
            entry["type"] = "text"
            entry["enum_values"] = None
        out.append(entry)
    missing = reserved_set - seen
    if missing:
        raise ValueError(
            f"Missing reserved field(s): {sorted(missing)}. "
            "The seven default fields are immutable and must always be present."
        )
    return out


async def replace_project_schema(
    db: AsyncSession,
    project_id: UUID,
    fields: list[ExtractionField],
) -> ProjectExtractionSchema:
    """Replace the project's schema with the given list of fields.

    Bumps the version. If the project has no schema row, creates one with
    the supplied fields (validated to include all reserved keys). If the
    supplied fields are exactly the seven defaults, the row is deleted
    instead so the project reverts to ``is_default=True``.
    """
    normalized = _normalize_for_storage(fields)

    # If the result is exactly the seven defaults, delete any existing row.
    is_pure_default = (
        len(normalized) == len(RESERVED_FIELD_KEYS)
        and all(
            normalized[i]["key"] == RESERVED_FIELD_KEYS[i]
            and normalized[i]["type"] == "text"
            and normalized[i]["enum_values"] is None
            for i in range(len(RESERVED_FIELD_KEYS))
        )
    )

    if is_pure_default:
        existing = await get_project_schema_row(db, project_id)
        if existing is not None:
            await db.delete(existing)
            await db.commit()
            logger.info(
                "Reverted project %s extraction schema to defaults", project_id
            )
        return None  # type: ignore[return-value]

    existing = await get_project_schema_row(db, project_id)
    if existing is None:
        existing = ProjectExtractionSchema(
            project_id=project_id,
            fields=normalized,
            version=1,
        )
        db.add(existing)
    else:
        existing.fields = normalized
        existing.version = (existing.version or 1) + 1
    await db.commit()
    await db.refresh(existing)
    logger.info(
        "Updated project %s extraction schema (version=%d, fields=%d)",
        project_id,
        existing.version,
        len(normalized),
    )
    return existing


# ---------------------------------------------------------------------------
# Validation helpers used by the matrix extractor
# ---------------------------------------------------------------------------


def coerce_custom_value(
    field: ExtractionField, value: object
) -> object | None:
    """Coerce a raw LLM-produced value to the schema-typed Python value.

    Returns ``None`` when the value is missing or cannot be coerced. The
    matrix extractor skips ``None`` values, so missing fields are simply
    omitted from the persisted ``custom_fields`` dict.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if field.type == "number":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if field.type == "boolean":
        lowered = raw.lower()
        if lowered in ("true", "yes", "1", "y"):
            return True
        if lowered in ("false", "no", "0", "n"):
            return False
        return None
    if field.type == "enum":
        # Snap to the closest declared value, case-insensitively.
        lowered = raw.lower()
        for ev in field.enum_values or []:
            if ev.lower() == lowered:
                return ev
        return None
    if field.type == "multi_select":
        # Allow comma- or semicolon-separated lists.
        tokens = [t.strip() for t in raw.replace(";", ",").split(",")]
        valid: list[str] = []
        for tok in tokens:
            if not tok:
                continue
            for ev in field.enum_values or []:
                if ev.lower() == tok.lower() and ev not in valid:
                    valid.append(ev)
                    break
        return valid
    # text / quote / citation / fallback — keep as-is, trimmed.
    if len(raw) > 4000:
        raw = raw[:4000]
    return raw


def build_extraction_json_schema(fields: list[ExtractionField]) -> dict:
    """Build a JSON Schema dict for the LLM call that extracts a matrix row.

    The schema always includes the seven reserved keys (typed as strings,
    matching the legacy ``MatrixRowOutput`` shape) plus the project's
    custom fields with their declared type. Custom values are nested under
    ``custom_fields`` so the response can be cleanly split between the
    fixed columns and the dynamic ones.
    """
    properties: dict[str, dict] = {}
    reserved_set = set(RESERVED_FIELD_KEYS)
    custom_required: list[str] = []

    for f in fields:
        if f.key in reserved_set:
            properties[f.key] = {
                "type": "string",
                "description": f.description or f.label,
            }
        else:
            properties[f.key] = _json_type_for(f)
            if f.required:
                custom_required.append(f.key)

    required: list[str] = list(RESERVED_FIELD_KEYS) + custom_required

    properties["confidence"] = {
        "type": "string",
        "enum": ["high", "medium", "low"],
        "description": (
            "Extraction QUALITY (not topic relevance). 'high' = every field "
            "clearly supported. 'medium' = most fields supported, a couple "
            "are 'not specified'. 'low' = the text is unusable."
        ),
    }

    schema: dict = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    return schema


def _json_type_for(field: ExtractionField) -> dict:
    """Map an ``ExtractionField`` to a JSON Schema fragment."""
    desc = field.description or field.label
    if field.type == "number":
        return {"type": "number", "description": desc}
    if field.type == "boolean":
        return {"type": "boolean", "description": desc}
    if field.type == "enum":
        return {
            "type": "string",
            "enum": field.enum_values or [],
            "description": desc,
        }
    if field.type == "multi_select":
        return {
            "type": "array",
            "items": {"type": "string", "enum": field.enum_values or []},
            "description": desc,
        }
    # text / quote / citation
    return {"type": "string", "description": desc}
