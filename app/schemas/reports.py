"""Pydantic models for report API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateReportRequest(BaseModel):
    title: str | None = None
    include_gap_section: bool = True
    selected_gap_ids: list[str] | None = None


class ReferenceResponse(BaseModel):
    citation_label: str
    project_paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str | None = None


class CitationAuditResponse(BaseModel):
    total_citations: int
    invalid_citations: int
    valid_citations: int
    uncited_saved_papers: int


class ReportResponse(BaseModel):
    id: str
    title: str
    validation_status: str
    content_markdown: str
    references: list[ReferenceResponse] = Field(default_factory=list)
    citation_audit: CitationAuditResponse


class ReportListResponse(BaseModel):
    items: list[ReportResponse]
    total: int


class ReportDetailResponse(BaseModel):
    id: str
    title: str
    validation_status: str
    content_markdown: str
    references: list[ReferenceResponse] = Field(default_factory=list)
    citation_audit: CitationAuditResponse
    created_at: str
