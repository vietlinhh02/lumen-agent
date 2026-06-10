"""Pydantic models for gap API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateGapsRequest(BaseModel):
    max_gaps: int = Field(default=5, ge=1, le=10)
    include_low_confidence: bool = False


class GapEvidenceResponse(BaseModel):
    project_paper_id: str
    title: str = ""
    evidence_type: str
    note: str


class GapResponse(BaseModel):
    id: str
    title: str
    description: str
    suggested_direction: str
    evidence_summary: str
    confidence: str
    evidence: list[GapEvidenceResponse] = Field(default_factory=list)


class GapListResponse(BaseModel):
    items: list[GapResponse]
    total: int
