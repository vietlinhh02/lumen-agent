"""Pydantic models for the T4 Custom Extraction Schema Builder.

A project-level extraction schema defines the list of typed fields that the
AI extractor fills in for each literature matrix row. The seven default
fields (``research_problem``, ``method``, ``dataset_or_context``,
``key_result``, ``limitation``, ``contribution``, ``relevance``) are
immutable system entries; new fields are project-defined.

The actual values are stored in ``LiteratureMatrixRow.custom_fields``
(JSONB). See ``docs/t4-custom-extraction-schema.md`` for the design.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

# Field types accepted by the schema builder. The vocabulary is closed so
# the frontend can render a fixed cell-editor widget per type.
FieldType = Literal[
    "text",
    "number",
    "enum",
    "multi_select",
    "boolean",
    "quote",
    "citation",
]

# Reserved keys for the seven system-default fields. They are always present
# in the effective schema (even when the project owner hides them in the UI)
# and their ``key`` cannot be changed by reviewers.
RESERVED_FIELD_KEYS: tuple[str, ...] = (
    "research_problem",
    "method",
    "dataset_or_context",
    "key_result",
    "limitation",
    "contribution",
    "relevance",
)


class ExtractionField(BaseModel):
    """One field in the project extraction schema.

    ``key`` is the stable identifier used as the JSON key in
    ``LiteratureMatrixRow.custom_fields``. After creation, ``key`` is
    effectively immutable (we never rename on update) so that previously
    extracted values do not get orphaned.

    ``type`` controls the cell editor and the value validation. Enum and
    multi_select require ``enum_values`` to be a non-empty list.
    """

    key: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description=(
            "Stable identifier used as the JSON key in custom_fields. "
            "Lowercase snake_case; cannot start with a digit."
        ),
    )
    label: str = Field(min_length=1, max_length=120)
    type: FieldType = Field(description="Field type; controls the cell editor.")
    description: str | None = Field(default=None, max_length=500)
    required: bool = Field(default=False)
    enum_values: list[str] | None = Field(default=None)

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: str) -> str:
        # Reserved keys are the seven default fields. Allow them through so
        # the schema can override their label/description (but not key/type).
        return v

    @model_validator(mode="after")
    def _check_enum_values(self) -> ExtractionField:
        if self.type in ("enum", "multi_select"):
            if not self.enum_values or len(self.enum_values) == 0:
                raise ValueError(
                    f"Field '{self.key}' of type '{self.type}' requires "
                    "a non-empty enum_values list."
                )
            # Deduplicate while preserving order.
            seen: set[str] = set()
            deduped: list[str] = []
            for v in self.enum_values:
                if v not in seen:
                    seen.add(v)
                    deduped.append(v)
            self.enum_values = deduped
        else:
            # enum_values is meaningless for non-enum fields; ignore it.
            self.enum_values = None
        return self


class ExtractionSchemaResponse(BaseModel):
    """Effective extraction schema for a project (defaults + project override)."""

    project_id: UUID
    version: int = 1
    fields: list[ExtractionField]
    is_default: bool = Field(
        description=(
            "True when the project has not customized its schema and is "
            "using the seven system defaults verbatim."
        )
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExtractionSchemaUpdateRequest(BaseModel):
    """Replace the project's extraction schema."""

    fields: list[ExtractionField] = Field(
        min_length=1,
        description=(
            "Full ordered list of fields. Must include all seven reserved "
            "keys (research_problem, method, dataset_or_context, "
            "key_result, limitation, contribution, relevance) with type='text'."
        ),
    )


class ExtractionSchemaSuggestRequest(BaseModel):
    """Ask the LLM to suggest schema fields for a project."""

    max_fields: int = Field(default=8, ge=1, le=20)
    sample_abstracts: list[str] | None = Field(
        default=None,
        max_length=10,
        description=(
            "Optional abstracts to ground the suggestions. The server can "
            "auto-fill these from the first few saved papers if omitted."
        ),
    )


class ExtractionSchemaSuggestResponse(BaseModel):
    """Suggested fields from the LLM."""

    fields: list[ExtractionField]
    rationale: str | None = None
