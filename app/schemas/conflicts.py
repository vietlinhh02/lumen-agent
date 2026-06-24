"""Pydantic models for conflict API endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.evidence import EvidenceChunkResponse


class ConflictResponse(BaseModel):
    id: str
    title: str
    description: str
    paper_a_id: str
    paper_a_title: str = ""
    paper_b_id: str
    paper_b_title: str = ""
    shared_context: str | None = None
    claim_a: str | None = None
    claim_b: str | None = None
    possible_explanation: str | None = None
    confidence: str


class ConflictListResponse(BaseModel):
    items: list[ConflictResponse]
    total: int


class ConflictEvidenceResponse(BaseModel):
    """T3 — persisted chunks behind each side of a conflict."""

    paper_a_title: str = ""
    paper_b_title: str = ""
    claim_a: list[EvidenceChunkResponse]
    claim_b: list[EvidenceChunkResponse]
