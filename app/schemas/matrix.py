"""Pydantic models for literature matrix CRUD."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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
    extraction_confidence: str = "medium"
    created_by: str = "ai"
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MatrixListResponse(BaseModel):
    items: list[MatrixRowResponse]


class MatrixRowUpdate(BaseModel):
    research_problem: str | None = None
    method: str | None = None
    dataset_or_context: str | None = None
    key_result: str | None = None
    limitation: str | None = None
    contribution: str | None = None
    relevance: str | None = None
    extraction_confidence: str | None = Field(default=None, pattern="^(low|medium|high)$")


class MatrixGenerateRequest(BaseModel):
    overwrite_existing: bool = False


class MatrixGenerateResponse(BaseModel):
    status: str
    created_count: int
    skipped_count: int
