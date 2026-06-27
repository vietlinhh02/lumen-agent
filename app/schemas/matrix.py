"""Pydantic models for literature matrix CRUD."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MatrixRowResponse(BaseModel):
    id: UUID
    project_id: UUID
    project_paper_id: UUID
    paper_title: str | None = None
    research_problem: str | None = None
    method: str | None = None
    dataset_or_context: str | None = None
    key_result: str | None = None
    limitation: str | None = None
    contribution: str | None = None
    relevance: str | None = None
    # T4: project-defined typed field values keyed by schema ``key``.
    # Backwards-compatible: omitted rows return an empty dict.
    custom_fields: dict = Field(default_factory=dict)
    extraction_confidence: str = "medium"
    created_by: str = "ai"
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MatrixListResponse(BaseModel):
    items: list[MatrixRowResponse]
    # T4: the effective schema in the same response so the frontend can
    # render column-typed cells without a second round-trip.
    extraction_schema: ExtractionSchemaResponse | None = None


class MatrixRowUpdate(BaseModel):
    research_problem: str | None = None
    method: str | None = None
    dataset_or_context: str | None = None
    key_result: str | None = None
    limitation: str | None = None
    contribution: str | None = None
    relevance: str | None = None
    # T4: replace custom field values. Keys not in the project's schema
    # are silently ignored at the API layer.
    custom_fields: dict | None = None
    extraction_confidence: str | None = Field(default=None, pattern="^(low|medium|high)$")


class MatrixGenerateRequest(BaseModel):
    overwrite_existing: bool = False


class MatrixGenerateResponse(BaseModel):
    status: str
    created_count: int
    skipped_count: int


# ── T4: filter / aggregate ────────────────────────────────────────────────


# Operators supported by the matrix filter endpoint. Each operator has a
# well-defined JSON-serializable payload shape so the client can render
# type-aware inputs.
FilterOp = Literal["eq", "neq", "contains", "gt", "gte", "lt", "lte", "in"]


class MatrixFilterRequest(BaseModel):
    field: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "Schema field key to filter on. Reserved fields can also be "
            "addressed by their literal name (e.g. ``extraction_confidence``)."
        ),
    )
    op: FilterOp = Field(
        default="eq",
        description="Comparison operator.",
    )
    # Value is intentionally a free-form union: string / number / bool /
    # list (for ``in``). Pydantic will accept the JSON-native shape and
    # pass it through; the service validates per ``op``/``field_type``.
    value: str | int | float | bool | list[str | int | float] | None

    @model_validator(mode="after")
    def _check_op_value(self) -> MatrixFilterRequest:
        if self.op == "in" and not isinstance(self.value, list):
            raise ValueError("`op='in'` requires `value` to be an array.")
        if self.op in ("gt", "gte", "lt", "lte") and not isinstance(self.value, (int, float)):
            raise ValueError(f"`op='{self.op}'` requires a numeric `value`.")
        return self


class MatrixFilterResponse(BaseModel):
    row_ids: list[str]
    total: int


class MatrixAggregateBucket(BaseModel):
    key: str
    count: int


class MatrixAggregateResponse(BaseModel):
    field: str
    group_by: str | None = None
    buckets: list[MatrixAggregateBucket]
    total: int


# Forward reference to avoid an import cycle: ``ExtractionSchemaResponse``
# lives in ``app.schemas.extraction_schema``.
from app.schemas.extraction_schema import ExtractionSchemaResponse  # noqa: E402

MatrixListResponse.model_rebuild()
