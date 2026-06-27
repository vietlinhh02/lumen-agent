"""Pydantic models for the PRISMA-style project audit endpoint (T2).

The audit endpoint summarizes a project's search, screening, full-text
retrieval, exclusion, and synthesis counts so reviewers can defend the
flow they followed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# Human-readable labels for the project's controlled exclusion reasons.
# Kept here (not in `services.project`) because the audit module is the
# canonical producer of audit artifacts that include these labels.
EXCLUSION_REASON_LABELS: dict[str, str] = {
    "wrong_population": "Wrong population",
    "wrong_intervention_or_topic": "Wrong topic",
    "wrong_outcome": "Wrong outcome",
    "wrong_study_type": "Wrong study type",
    "not_peer_reviewed": "Not peer reviewed",
    "outside_date_range": "Outside date range",
    "duplicate": "Duplicate",
    "no_full_text": "No full text",
    "insufficient_relevance": "Insufficient relevance",
    "other": "Other",
}


class AuditCount(BaseModel):
    """Single labeled counter used throughout the audit flow."""

    label: str
    count: int
    note: str | None = None


class AuditSourceCount(BaseModel):
    """Per-source count of papers identified through database search."""

    source: str
    count: int


class AuditExclusionReason(BaseModel):
    """Breakdown of excluded papers by their controlled exclusion reason."""

    reason: str
    label: str
    count: int


class AuditHistogramPoint(BaseModel):
    """One bucket in a key→count distribution (e.g. year, venue)."""

    key: str
    count: int


class AuditTimelinePoint(BaseModel):
    """One point on a per-period time series (e.g. papers added per day)."""

    date: str  # ISO date (YYYY-MM-DD)
    count: int


class AuditSearchSessionSummary(BaseModel):
    """Compact summary of a single search session for the audit history."""

    id: str
    user_query: str
    total_results: int
    screened_count: int
    high_score_count: int
    created_at: datetime


class AuditQualityMetrics(BaseModel):
    """Quality signals for the AI features of this project."""

    matrix_avg_confidence: float | None = None
    matrix_confidence_breakdown: dict[str, int] = Field(default_factory=dict)
    full_text_success_rate: float | None = None
    full_text_breakdown: dict[str, int] = Field(default_factory=dict)
    citation_validity_rate: float | None = None
    reports_by_validation: dict[str, int] = Field(default_factory=dict)


class AuditFieldCoverage(BaseModel):
    """Per-schema-field population coverage for the literature matrix."""

    key: str
    label: str
    type: str
    is_reserved: bool
    required: bool
    populated: int
    rows_total: int
    coverage_rate: float


class AuditExtractionSchema(BaseModel):
    """Summary of the project's effective extraction schema (T4)."""

    is_default: bool
    version: int
    fields_total: int
    custom_fields_total: int
    fields: list[AuditFieldCoverage] = Field(default_factory=list)


class PrismaAuditResponse(BaseModel):
    """PRISMA-style audit summary for one project.

    Counts are derived from existing data (search runs, project papers,
    matrix rows, review citations) without altering any records.
    """

    project_id: UUID
    project_title: str
    project_topic: str
    research_question: str | None = None
    generated_at: datetime

    # Identification: papers found through database searching.
    identified_by_source: list[AuditSourceCount] = Field(default_factory=list)
    records_identified: int = 0

    # Deduplication across search sessions and prior saves.
    duplicates_removed: int = 0

    # Title/abstract screening (driven by SearchRun.screening_scores).
    records_screened: int = 0
    records_excluded_screening: int = 0
    screening_score_distribution: dict[str, int] = Field(default_factory=dict)

    # Full-text retrieval.
    full_text_assessed: int = 0
    full_text_not_retrieved: int = 0

    # Final include/exclude.
    records_included: int = 0
    records_uncertain: int = 0
    records_excluded_final: int = 0
    exclusion_reasons: list[AuditExclusionReason] = Field(default_factory=list)

    # Synthesis: downstream artifact counts.
    matrix_rows: int = 0
    reports_generated: int = 0
    cited_in_reports: int = 0

    # Free-form reviewer notes from the stored protocol (shown above the flow).
    protocol_notes: str | None = None

    # ── Enrichment layer ────────────────────────────────────────────────
    # The fields below add coverage / quality / reproducibility signals on
    # top of the basic PRISMA flow. They are all derived from existing
    # tables and are safe to render alongside the core flow.

    # Coverage: year + venue distribution of saved papers.
    year_distribution: list[AuditHistogramPoint] = Field(default_factory=list)
    top_venues: list[AuditHistogramPoint] = Field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None

    # Workflow history: recent search sessions and the inclusion timeline.
    recent_search_sessions: list[AuditSearchSessionSummary] = Field(default_factory=list)
    inclusion_timeline: list[AuditTimelinePoint] = Field(default_factory=list)

    # Quality signals across AI features.
    quality_metrics: AuditQualityMetrics = Field(default_factory=AuditQualityMetrics)

    # T4: per-field coverage of the project's effective extraction schema.
    extraction_schema: AuditExtractionSchema | None = None
PrismaAuditResponse.model_rebuild()
