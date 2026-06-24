"""Pydantic models for claim synthesis API endpoints (T7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClaimEvidenceResponse(BaseModel):
    id: str
    project_paper_id: str
    paper_title: str = ""
    polarity: str  # support | contradict | neutral
    snippet: str | None = None


class ClaimResponse(BaseModel):
    id: str
    canonical_text: str
    claim_type: str  # support | contradict | mixed | weak
    support_count: int
    contradict_count: int
    neutral_count: int
    confidence: str
    field_origin: str | None = None
    source_type: str
    evidence: list[ClaimEvidenceResponse] = Field(default_factory=list)


class ClaimListResponse(BaseModel):
    items: list[ClaimResponse]
    total: int


class ClaimAggregateResponse(BaseModel):
    support: int
    contradict: int
    mixed: int
    weak: int
