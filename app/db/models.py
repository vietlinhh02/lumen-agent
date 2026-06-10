import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ── Authentication ────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="researcher", server_default="researcher"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", lazy="selectin")
    reports: Mapped[list["ReviewReport"]] = relationship(
        back_populates="created_by_user", lazy="selectin"
    )

    __table_args__ = (CheckConstraint("role IN ('researcher', 'admin')", name="ck_users_role"),)


# ── Research Workspace ───────────────────────────────────────────────────────


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    research_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    owner: Mapped["User"] = relationship(back_populates="projects")
    project_papers: Mapped[list["ProjectPaper"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    matrix_rows: Mapped[list["LiteratureMatrixRow"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    gaps: Mapped[list["ResearchGap"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    reports: Mapped[list["ReviewReport"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    retrieval_audits: Mapped[list["RetrievalAudit"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    search_runs: Mapped[list["SearchRun"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )
    conflicting_findings: Mapped[list["ConflictingFinding"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
    )


# ── Canonical Papers ──────────────────────────────────────────────────────────


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(512), nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    openalex_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    citation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    authors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    source_names: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    project_papers: Mapped[list["ProjectPaper"]] = relationship(
        back_populates="paper", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_papers_doi_unique", doi, unique=True, postgresql_where=doi.isnot(None)),
        Index(
            "ix_papers_arxiv_unique", arxiv_id, unique=True, postgresql_where=arxiv_id.isnot(None)
        ),
        Index(
            "ix_papers_semantic_scholar_unique",
            semantic_scholar_id,
            unique=True,
            postgresql_where=semantic_scholar_id.isnot(None),
        ),
        Index(
            "ix_papers_openalex_unique",
            openalex_id,
            unique=True,
            postgresql_where=openalex_id.isnot(None),
        ),
        Index("ix_papers_title_year", "title", "year"),
        Index("ix_papers_language", "language"),
    )


# ── Search Protocol ──────────────────────────────────────────────────────────


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_languages: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    language_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="balanced", server_default="balanced"
    )
    english_dominance_score: Mapped[float | None] = mapped_column(nullable=True)
    total_results: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    results_json: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    screening_scores: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    query_variants: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    language_bias_audit: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_diagnostics: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="search_runs")
    queries: Mapped[list["SearchQuery"]] = relationship(
        back_populates="search_run", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "language_policy IN ('balanced', 'original_first', 'english_first')",
            name="ck_search_runs_language_policy",
        ),
    )


class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    search_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    search_run: Mapped["SearchRun"] = relationship(back_populates="queries")

    __table_args__ = (
        CheckConstraint(
            "source IN ('semantic_scholar', 'exa', 'firecrawl')",
            name="ck_search_queries_source",
        ),
    )


# ── Project Papers ───────────────────────────────────────────────────────────


class ProjectPaper(Base):
    __tablename__ = "project_papers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("papers.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="saved", server_default="saved"
    )
    relevance_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text_status: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    saved_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="project_papers")
    paper: Mapped["Paper"] = relationship(back_populates="project_papers")
    enrichments: Mapped[list["PaperEnrichment"]] = relationship(
        back_populates="project_paper", lazy="selectin", cascade="all, delete-orphan"
    )
    facets: Mapped[list["PaperFacet"]] = relationship(
        back_populates="project_paper", lazy="selectin", cascade="all, delete-orphan"
    )
    matrix_row: Mapped["LiteratureMatrixRow | None"] = relationship(
        back_populates="project_paper", uselist=False, cascade="all, delete-orphan"
    )
    gap_evidence_entries: Mapped[list["GapEvidence"]] = relationship(
        back_populates="project_paper", lazy="selectin", cascade="all, delete-orphan"
    )
    citations: Mapped[list["ReviewCitation"]] = relationship(
        back_populates="project_paper", lazy="selectin", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["PaperChunk"]] = relationship(
        back_populates="project_paper", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("project_id", "paper_id", name="uq_project_papers_project_paper"),
        CheckConstraint(
            "status IN ('saved', 'rejected', 'uncertain')", name="ck_project_papers_status"
        ),
        CheckConstraint(
            "relevance_label IS NULL OR relevance_label IN ('core', 'related', 'background')",
            name="ck_project_papers_relevance",
        ),
        Index("ix_project_papers_project_status", "project_id", "status"),
    )


# ── Research Enrichment ──────────────────────────────────────────────────────


class PaperEnrichment(Base):
    __tablename__ = "paper_enrichments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    merged_source_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    related_papers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    references_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    open_access_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawled_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_quality: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    enrichment_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(nullable=True)

    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="enrichments")

    __table_args__ = (
        CheckConstraint(
            "enrichment_status IN ('pending', 'completed', 'failed')",
            name="ck_paper_enrichments_status",
        ),
        CheckConstraint(
            "evidence_quality IN ('unknown', 'abstract-level', 'full-text', 'enriched')",
            name="ck_paper_enrichments_quality",
        ),
    )


class PaperFacet(Base):
    __tablename__ = "paper_facets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method_family: Mapped[str | None] = mapped_column(String(256), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dataset_names: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    metric_names: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    limitation_types: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    contribution_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    extraction_confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", server_default="medium"
    )
    extraction_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="facets")

    __table_args__ = (
        CheckConstraint(
            "extraction_confidence IN ('low', 'medium', 'high')",
            name="ck_paper_facets_confidence",
        ),
        Index("ix_paper_facets_method", "method_family"),
        Index("ix_paper_facets_domain", "domain"),
    )


# ── Literature Matrix ────────────────────────────────────────────────────────


class LiteratureMatrixRow(Base):
    __tablename__ = "literature_matrix_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    research_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_or_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    contribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", server_default="medium"
    )
    created_by: Mapped[str] = mapped_column(
        String(8), nullable=False, default="ai", server_default="ai"
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="matrix_rows")
    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="matrix_row")

    __table_args__ = (
        CheckConstraint("created_by IN ('ai', 'user')", name="ck_matrix_rows_created_by"),
        CheckConstraint(
            "extraction_confidence IN ('low', 'medium', 'high')",
            name="ck_matrix_rows_confidence",
        ),
        Index("ix_matrix_rows_project", "project_id"),
    )


# ── Research Gaps ────────────────────────────────────────────────────────────


class ResearchGap(Base):
    __tablename__ = "research_gaps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_direction: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", server_default="medium"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="gaps")
    evidence_entries: Mapped[list["GapEvidence"]] = relationship(
        back_populates="gap", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IN ('low', 'medium', 'high')", name="ck_research_gaps_confidence"
        ),
        Index("ix_research_gaps_project", "project_id"),
    )


class GapEvidence(Base):
    __tablename__ = "gap_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    gap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_gaps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    gap: Mapped["ResearchGap"] = relationship(back_populates="evidence_entries")
    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="gap_evidence_entries")

    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('limitation', 'missing_dataset', 'method_gap', 'result_pattern')",
            name="ck_gap_evidence_type",
        ),
    )


# ── Conflicting Findings ─────────────────────────────────────────────────────


class ConflictingFinding(Base):
    __tablename__ = "conflicting_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    paper_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paper_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shared_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    possible_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="medium", server_default="medium"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="conflicting_findings")

    __table_args__ = (
        CheckConstraint(
            "confidence IN ('low', 'medium', 'high')", name="ck_conflicting_findings_confidence"
        ),
        Index("ix_conflicting_findings_project", "project_id"),
    )


# ── Review Reports ───────────────────────────────────────────────────────────


class ReviewReport(Base):
    __tablename__ = "review_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="reports")
    created_by_user: Mapped["User"] = relationship(back_populates="reports")
    citations: Mapped[list["ReviewCitation"]] = relationship(
        back_populates="report", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "validation_status IN ('valid', 'invalid', 'pending')",
            name="ck_review_reports_validation",
        ),
        Index("ix_review_reports_project", "project_id"),
    )


class ReviewCitation(Base):
    __tablename__ = "review_citations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_papers.id"), nullable=False, index=True
    )
    citation_label: Mapped[str] = mapped_column(String(32), nullable=False)
    paragraph_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    report: Mapped["ReviewReport"] = relationship(back_populates="citations")
    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="citations")

    __table_args__ = (Index("ix_review_citations_report", "report_id"),)


# ── Agent Workflow ───────────────────────────────────────────────────────────


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    input_state: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    output_state: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    project: Mapped["Project"] = relationship(back_populates="agent_runs")
    steps: Mapped[list["AgentStep"]] = relationship(back_populates="agent_run", lazy="selectin")

    __table_args__ = (
        CheckConstraint(
            "run_type IN "
            "('search', 'enrichment', 'matrix', 'gap', 'report', 'full_review', 'conflict')",
            name="ck_agent_runs_run_type",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name="ck_agent_runs_status"
        ),
        Index("ix_agent_runs_project_type", "project_id", "run_type"),
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    input_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    output_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    tool_calls: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    agent_run: Mapped["AgentRun"] = relationship(back_populates="steps")

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')", name="ck_agent_steps_status"
        ),
        Index("ix_agent_steps_run_node", "agent_run_id", "node_name"),
    )


# ── Background Jobs ───────────────────────────────────────────────────────


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        CheckConstraint(
            "job_type IN ("
            "'auto_save', 'normalize', 'enrich',"
            " 'matrix_generate', 'gap_generate', 'conflict_generate'"
            ")",
            name="ck_background_jobs_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_background_jobs_status",
        ),
        Index("ix_background_jobs_user_status", "user_id", "status"),
    )


# ── Retrieval Audit ──────────────────────────────────────────────────────────


class RetrievalAudit(Base):
    __tablename__ = "retrieval_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    retrieved_chunks: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    reranker_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="retrieval_audits")

    __table_args__ = (
        CheckConstraint(
            "retrieval_mode IN ('full_text', 'vector', 'hybrid', 'reranked')",
            name="ck_retrieval_audits_mode",
        ),
        Index("ix_retrieval_audits_project_mode", "project_id", "retrieval_mode"),
    )


# ── pgvector Embeddings ──────────────────────────────────────────────────────


class PaperChunk(Base):
    __tablename__ = "paper_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_paper_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_papers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="full_text", server_default="full_text"
    )
    section_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # embedding: Mapped[list[float] | None] = mapped_column(nullable=True)
    # Uncomment and use pgvector.sqlalchemy.Vector when pgvector is available
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project_paper: Mapped["ProjectPaper"] = relationship(back_populates="chunks")

    __table_args__ = (
        CheckConstraint(
            "chunk_type IN ('abstract', 'summary', 'matrix', 'full_text', 'section')",
            name="ck_paper_chunks_type",
        ),
        CheckConstraint(
            "content_type IS NULL OR content_type IN ("
            "'abstract', 'narrative', 'method', 'results', 'limitation', "
            "'table', 'figure_caption', 'reference'"
            ")",
            name="ck_paper_chunks_content_type",
        ),
        Index("ix_paper_chunks_project_paper", "project_paper_id"),
        Index("ix_paper_chunks_project_content", "project_paper_id", "content_type"),
        Index("ix_paper_chunks_project_section", "project_paper_id", "section_label"),
    )
