"""Pydantic models for conflict API endpoints."""

from __future__ import annotations

from pydantic import BaseModel


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
