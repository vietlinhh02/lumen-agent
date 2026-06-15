"""Pydantic models for project CRUD and paper management."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Project CRUD ──────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    topic: str = Field(..., min_length=1)
    research_question: str | None = None


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    topic: str | None = None
    research_question: str | None = None
    status: str | None = None  # "active" | "archived"


class ProjectResponse(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    topic: str
    research_question: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    paper_count: int = 0

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


# ── Save / Manage Papers ───────────────────────────────────────────────────


class SavePaperRequest(BaseModel):
    paper_title: str = Field(..., min_length=1)
    paper_abstract: str | None = None
    paper_year: int | None = None
    paper_venue: str | None = None
    paper_doi: str | None = None
    paper_arxiv_id: str | None = None
    paper_semantic_scholar_id: str | None = None
    paper_url: str | None = None
    paper_citation_count: int | None = None
    paper_authors: list[dict[str, str]] = Field(default_factory=list)
    paper_source_names: list[str] = Field(default_factory=list)
    relevance_label: str | None = None  # "core" | "related" | "background"
    user_note: str | None = None
    download_pdf: bool = False
    source_specific: dict = Field(default_factory=dict)
    # If the caller already downloaded the PDF (e.g. search_papers did it),
    # pass the local path here so we skip the network round-trip entirely.
    prefetched_pdf_path: str | None = None
    prefetched_pdf_source: str | None = None


class SavePaperResponse(BaseModel):
    project_paper_id: UUID
    paper_id: UUID
    title: str
    status: str
    pdf_path: str | None = None
    full_text_status: str | None = None


class ProjectPaperResponse(BaseModel):
    id: UUID
    project_id: UUID
    paper_id: UUID
    status: str
    relevance_label: str | None = None
    user_note: str | None = None
    full_text_status: str | None = None
    saved_at: datetime
    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[dict] = Field(default_factory=list)
    citation_count: int | None = None
    pdf_path: str | None = None
    has_matrix: bool = False
    has_enrichment: bool = False

    model_config = {"from_attributes": True}


class UpdatePaperRequest(BaseModel):
    relevance_label: str | None = None
    user_note: str | None = None
    status: str | None = None  # "saved" | "rejected" | "uncertain"
    full_text_status: str | None = None


class FullTextChunk(BaseModel):
    section_label: str | None = None
    section_path: str | None = None
    chunk_index: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    content_type: str | None = None
    pipeline_version: str | None = None
    content_hash: str | None = None
    chunk_text: str
    char_count: int


class FullTextResponse(BaseModel):
    project_paper_id: UUID
    title: str
    full_text_status: str | None
    total_chars: int
    total_chunks: int
    chunks: list[FullTextChunk]
    crawled_markdown: str | None = None


class NormalizeResponse(BaseModel):
    processed: int
    skipped: int
    failed: int


class RetrieveEvidenceRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=50)
    content_types: list[str] | None = None


class EvidenceChunkResponse(BaseModel):
    project_paper_id: UUID
    paper_id: UUID
    chunk_id: UUID
    title: str
    section_label: str | None = None
    section_path: str | None = None
    chunk_index: int | None = None
    content_type: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    content_hash: str | None = None
    score: float
    keyword_score: float
    vector_score: float
    chunk_text: str


class RetrieveEvidenceResponse(BaseModel):
    query: str
    total: int
    chunks: list[EvidenceChunkResponse]
