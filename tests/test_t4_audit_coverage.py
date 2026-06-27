"""Tests for T4 audit integration — schema coverage + Markdown rendering."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


from app.schemas.audit import (
    AuditExtractionSchema,
    AuditFieldCoverage,
    AuditQualityMetrics,
    PrismaAuditResponse,
)
from app.services.audit import (
    render_audit_csv,
    render_audit_markdown,
)


# ── audit response shape ────────────────────────────────────────────────


def _make_audit(
    *,
    with_extraction_schema: bool = True,
) -> PrismaAuditResponse:
    schema = None
    if with_extraction_schema:
        schema = AuditExtractionSchema(
            is_default=False,
            version=3,
            fields_total=8,
            custom_fields_total=1,
            fields=[
                AuditFieldCoverage(
                    key="research_problem",
                    label="Research Problem",
                    type="text",
                    is_reserved=True,
                    required=False,
                    populated=4,
                    rows_total=5,
                    coverage_rate=0.8,
                ),
                AuditFieldCoverage(
                    key="sample_size",
                    label="Sample size",
                    type="number",
                    is_reserved=False,
                    required=True,
                    populated=2,
                    rows_total=5,
                    coverage_rate=0.4,
                ),
            ],
        )
    return PrismaAuditResponse(
        project_id=uuid4(),
        project_title="RAG for Medical QA",
        project_topic="Retrieval-Augmented Generation for medical question answering",
        research_question="How does RAG help?",
        generated_at=datetime.now(UTC).replace(tzinfo=None),
        identified_by_source=[],
        records_identified=0,
        duplicates_removed=0,
        records_screened=0,
        records_excluded_screening=0,
        screening_score_distribution={},
        full_text_assessed=0,
        full_text_not_retrieved=0,
        records_included=0,
        records_uncertain=0,
        records_excluded_final=0,
        exclusion_reasons=[],
        matrix_rows=5,
        reports_generated=0,
        cited_in_reports=0,
        protocol_notes=None,
        year_distribution=[],
        top_venues=[],
        year_min=None,
        year_max=None,
        inclusion_timeline=[],
        recent_search_sessions=[],
        quality_metrics=AuditQualityMetrics(),
        extraction_schema=schema,
    )


# ── Markdown renderer includes the new section ─────────────────────────


def test_render_audit_markdown_includes_schema_coverage():
    audit = _make_audit(with_extraction_schema=True)
    md = render_audit_markdown(audit)
    assert "Extraction schema coverage (T4)" in md
    assert "research_problem" in md
    assert "sample_size" in md
    assert "80%" in md
    assert "40%" in md
    assert "version 3" in md or "v3" in md


def test_render_audit_markdown_handles_no_schema():
    audit = _make_audit(with_extraction_schema=False)
    md = render_audit_markdown(audit)
    assert "Extraction schema coverage" not in md


def test_render_audit_markdown_handles_default_schema():
    audit = _make_audit(with_extraction_schema=True)
    assert audit.extraction_schema is not None
    audit.extraction_schema.is_default = True
    md = render_audit_markdown(audit)
    assert "system default" in md


# ── CSV renderer includes the new section ──────────────────────────────


def test_render_audit_csv_includes_schema_coverage():
    audit = _make_audit(with_extraction_schema=True)
    csv = render_audit_csv(audit)
    assert "extraction_schema,fields_total,8" in csv
    assert "extraction_schema,custom_fields_total,1" in csv
    assert "extraction_schema,version,3" in csv
    assert "extraction_field,research_problem,4" in csv
    assert "extraction_field,sample_size,2" in csv


def test_render_audit_csv_handles_no_schema():
    audit = _make_audit(with_extraction_schema=False)
    csv = render_audit_csv(audit)
    assert "extraction_schema" not in csv
