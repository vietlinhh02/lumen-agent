"""Shared Pydantic models for the T3 evidence viewer.

Used by the matrix, gap, and conflict evidence endpoints so every surface
returns the same chunk shape and the frontend can reuse one drawer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class EvidenceChunkResponse(BaseModel):
    """A single supporting chunk (quote + section + optional page)."""

    chunk_id: UUID
    # The paper the chunk belongs to. Needed so the drawer can rate a chunk
    # even when one drawer mixes chunks from two papers (conflict surface).
    project_paper_id: UUID | None = None
    chunk_text: str
    section_label: str | None = None
    content_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    score: float


class EvidenceListResponse(BaseModel):
    """Evidence chunks scoped to one paper (matrix row / gap)."""

    project_paper_id: UUID
    paper_title: str | None = None
    items: list[EvidenceChunkResponse]


# ── T3 Phase 3: Evidence Ratings ──────────────────────────────────────────

SourceKind = Literal["matrix_row", "gap", "conflict", "report_paragraph"]
RatingValue = Literal["accepted", "weak", "wrong"]


class EvidenceRatingCreate(BaseModel):
    """Upsert payload for rating one chunk under one claim surface."""

    source_kind: SourceKind
    source_id: UUID
    project_paper_id: UUID
    chunk_id: UUID
    rating: RatingValue
    note: str | None = None


class EvidenceRatingResponse(BaseModel):
    id: UUID
    source_kind: SourceKind
    source_id: UUID
    project_paper_id: UUID
    chunk_id: UUID
    rating: RatingValue
    note: str | None = None
    updated_at: datetime | None = None


class EvidenceRatingListResponse(BaseModel):
    items: list[EvidenceRatingResponse]


class EvidenceRatingSummary(BaseModel):
    """Per-user rating tally for a project (drives the header chip)."""

    accepted: int = 0
    weak: int = 0
    wrong: int = 0
