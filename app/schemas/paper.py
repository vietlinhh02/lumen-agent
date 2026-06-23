"""Pydantic models for the paper search + download feature."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Request ──────────────────────────────────────────────────────────────


class PaperSearchRequest(BaseModel):
    """Search parameters sent by the user or agent."""

    query: str = Field(
        ..., description="Natural-language search query", min_length=2, max_length=500
    )
    limit: int = Field(default=50, description="Max papers to return", ge=1, le=500)
    year_from: int | None = Field(
        default=None, description="Earliest publication year", ge=1900, le=2100
    )
    year_to: int | None = Field(
        default=None, description="Latest publication year", ge=1900, le=2100
    )
    download_pdfs: bool = Field(
        default=True,
        description="Automatically download full-text PDFs for returned papers",
    )
    target_languages: list[str] = Field(
        default_factory=list,
        description="Preferred languages for query variants, e.g. ['en', 'vi']",
    )
    language_policy: str = Field(
        default="balanced",
        description="Language bias policy: 'balanced', 'original_first', or 'english_first'",
    )


# ── Language Bias ─────────────────────────────────────────────────────────


class QueryVariant(BaseModel):
    source: str
    query: str
    language: str


class LanguageBiasAudit(BaseModel):
    policy: str = "balanced"
    candidate_counts_by_language: dict[str, int] = Field(default_factory=dict)
    english_dominance_score: float = 0.0
    adjustments_applied: list[str] = Field(default_factory=list)


# ── Response ─────────────────────────────────────────────────────────────


class PaperAuthor(BaseModel):
    """Author information for a paper."""

    name: str
    author_id: str | None = None


class PaperResult(BaseModel):
    """A single paper in the search results."""

    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    semantic_scholar_id: str | None = None
    url: str | None = None
    citation_count: int | None = None
    authors: list[PaperAuthor] = Field(default_factory=list)
    fields_of_study: list[str] = Field(default_factory=list)
    is_open_access: bool | None = None
    source_names: list[str] = Field(default_factory=list)
    source_specific: dict = Field(default_factory=dict)

    # Download status
    pdf_downloaded: bool = False
    pdf_path: str | None = None
    pdf_source: str | None = None


class PaperSearchResponse(BaseModel):
    """Top-level response for a paper search."""

    query: str
    total_found: int
    total_returned: int
    search_time_ms: float
    download_time_ms: float | None = None
    pdfs_downloaded: int = 0
    pdfs_failed: int = 0
    papers: list[PaperResult]
    detected_language: str | None = None
    query_variants: list[QueryVariant] = Field(default_factory=list)
    language_bias_audit: LanguageBiasAudit | None = None
    source_diagnostics: list[dict] = Field(default_factory=list)


class PaperPDFStatus(BaseModel):
    """Status of a PDF download for one paper."""

    paper_title: str
    paper_arxiv_id: str | None = None
    paper_doi: str | None = None
    downloaded: bool
    pdf_path: str | None = None
    pdf_source: str | None = None
    file_size_bytes: int | None = None
    error: str | None = None


# ── Query Suggestions ─────────────────────────────────────────────────────


class SuggestQueriesRequest(BaseModel):
    """Request body for query suggestion endpoint."""

    title: str = Field(default="", description="Project title")
    topic: str = Field(..., description="Research topic", min_length=2, max_length=500)
    research_question: str = Field(default="", description="Specific research question")
    # Optional — when the caller knows the project, the server loads the
    # stored review_protocol and uses it to bias query formulation.
    project_id: str | None = Field(
        default=None,
        description="Optional project UUID; if provided, the server will look "
        "up the project's review_protocol from the database.",
    )
    # Optional — caller-supplied protocol when project_id is not provided.
    review_protocol: dict | None = Field(
        default=None,
        description="Optional pre-loaded review protocol (see ReviewProtocol). "
        "Ignored when project_id resolves to a real project.",
    )


class SuggestQueriesResponse(BaseModel):
    """Response with AI-generated search query suggestions."""

    queries: list[str] = Field(description="Suggested academic search queries (4–6)")


# ── Paper Screening ───────────────────────────────────────────────────────


class ScreenPaperItem(BaseModel):
    """One paper to screen, identified by its title + abstract."""

    title: str
    abstract: str | None = None


class ScreenPapersRequest(BaseModel):
    """Request body for AI paper screening."""

    topic: str = Field(..., min_length=1, max_length=512)
    research_question: str | None = None
    review_protocol: dict | None = Field(
        default=None,
        description="Optional review protocol so scoring can use "
        "inclusion/exclusion criteria and population/comparison/outcome.",
    )
    papers: list[ScreenPaperItem] = Field(..., min_length=1, max_length=100)


class ScreenPapersResponse(BaseModel):
    """Response with relevance scores for each paper (same order as input)."""

    scores: list[str] = Field(description="Relevance score per paper: 'high', 'medium', or 'low'")


# ── Auto Search & Save ───────────────────────────────────────────────────


class AutoSearchRequest(BaseModel):
    """Request body for the auto-search-and-save endpoint.

    ``target_count`` is constrained to a small set of options so the UI can
    present a simple dropdown (25 / 50 / 100).
    """

    query: str = Field(..., min_length=2, max_length=500)
    target_count: Literal[25, 50, 100] = Field(..., description="Number of papers to save (25, 50, or 100)")


class AutoSearchResponse(BaseModel):
    """Response for POST /api/projects/{id}/search/auto."""

    job_id: str
    session_id: str
    target_count: int
    status: str
