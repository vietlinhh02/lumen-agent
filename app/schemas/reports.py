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
    # T3 Phase 4: served PDF URL when the file exists on disk, so report
    # citations can open the source PDF. None when no local PDF.
    pdf_path: str | None = None


class CitationAuditResponse(BaseModel):
    total_citations: int
    invalid_citations: int
    valid_citations: int
    uncited_saved_papers: int


class UngroundedClaimExample(BaseModel):
    claim: str
    section: str
    context: str
    cited_papers: list[str]


class ClaimAuditResponse(BaseModel):
    """Defensive audit that catches the "dâu ông nọ cắm căm bà kia"
    hallucination pattern: a paper is cited but the number attributed
    to it is not actually in the paper's retrieved chunks.
    """

    total_claims: int
    grounded_claims: int
    ungrounded_claims: int
    ungrounded_examples: list[UngroundedClaimExample] = Field(default_factory=list)
    grounding_rate: float


class ReportResponse(BaseModel):
    id: str
    title: str
    validation_status: str
    content_markdown: str
    references: list[ReferenceResponse] = Field(default_factory=list)
    citation_audit: CitationAuditResponse
    claim_audit: ClaimAuditResponse | None = None


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
    claim_audit: ClaimAuditResponse | None = None
    created_at: str
