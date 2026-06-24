"""Tests for the PRISMA-style project audit (T2)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas.audit import PrismaAuditResponse
from app.services.audit import (
    FULL_TEXT_FAILURE,
    FULL_TEXT_SUCCESS,
    RECENT_SESSIONS_LIMIT,
    TIMELINE_DAY_WINDOW,
    TOP_VENUES_LIMIT,
    build_project_audit,
    render_audit_csv,
    render_audit_markdown,
)


class _Counter:
    """Reusable helper that returns a sequence of MagicMock results from `db.execute`."""

    def __init__(self, results):
        self._results = list(results)
        self._index = 0

    async def __call__(self, _stmt):
        if self._index >= len(self._results):
            return MagicMock()
        result = self._results[self._index]
        self._index += 1
        return result


def _make_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), email="user@example.com")


def _scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _all_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _one_result(row):
    """Return a MagicMock whose .one() yields a single row with attribute access."""
    result = MagicMock()
    result.one.return_value = row
    return result


def _quality_row(total=0, high=0, medium=0, low=0, avg_score=None):
    return SimpleNamespace(
        total=total, high=high, medium=medium, low=low, avg_score=avg_score
    )


def _make_project(project_id, owner_id):
    return SimpleNamespace(
        id=project_id,
        owner_id=owner_id,
        title="Medical RAG",
        topic="RAG for medical QA",
        research_question="How well does RAG work for medical QA?",
        review_protocol={"notes": "Search 2020-2026 English"},
    )


@pytest.mark.asyncio
async def test_build_project_audit_returns_none_for_missing_project():
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_scalar_one_or_none(None)
    )
    user = _make_user()
    result = await build_project_audit(db, user, uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_build_project_audit_aggregates_counts():
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id

    project = _make_project(project_id, owner_id)
    # search_runs: one run with diagnostics across 2 sources and 5 screening scores
    search_runs_rows = [
        (
            [{"source": "semantic_scholar", "result_count": 80}, {"source": "openalex", "result_count": 70}],
            ["high", "high", "medium", "low", "high"],
        )
    ]
    # project_papers: 2 saved (1 completed, 1 failed), 1 rejected with reason, 1 uncertain
    pp_rows = [
        ("saved", None, "completed"),
        ("saved", None, "failed"),
        ("rejected", "wrong_population", None),
        ("uncertain", None, None),
    ]
    recent_sessions_rows = [
        (uuid4(), "rag medical", 150, ["high", "high", "medium"], datetime(2026, 6, 20)),
    ]
    saved_meta_rows = [
        (2022, "Nature", datetime(2026, 6, 18)),
        (2024, "Lancet", datetime(2026, 6, 20)),
    ]
    quality = _quality_row(total=2, high=1, medium=1, low=0, avg_score=2.5)
    report_validation_rows = [("valid", 1)]

    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),  # project ownership check (first)
            _scalar_result(150),  # sum of total_results
            _all_result(search_runs_rows),  # search runs
            _all_result(recent_sessions_rows),  # recent search sessions
            _all_result(pp_rows),  # project papers
            _all_result(saved_meta_rows),  # saved paper metadata
            _scalar_result(2),  # matrix row count
            _one_result(quality),  # matrix quality breakdown
            _scalar_result(2),  # gaps (unused in response)
            _scalar_result(1),  # reports count
            _all_result(report_validation_rows),  # reports by validation_status
            _scalar_result(5),  # distinct cited project_paper_ids
        ]
    )

    audit = await build_project_audit(db, user, project_id)

    assert audit is not None
    assert audit.project_id == project_id
    assert audit.records_identified == 150
    assert audit.records_screened == 5
    assert audit.records_excluded_screening == 2  # 1 medium + 1 low

    # Sources are sorted descending by count
    assert [s.source for s in audit.identified_by_source] == ["semantic_scholar", "openalex"]
    assert [s.count for s in audit.identified_by_source] == [80, 70]

    # Full-text bucket counts
    assert audit.full_text_assessed == 1
    assert audit.full_text_not_retrieved == 1

    # Save / reject / uncertain bucketing
    assert audit.records_included == 2
    assert audit.records_uncertain == 1
    assert audit.records_excluded_final == 1

    # Exclusion reasons — only one rejected paper, with the expected reason
    assert len(audit.exclusion_reasons) == 1
    assert audit.exclusion_reasons[0].reason == "wrong_population"
    assert audit.exclusion_reasons[0].label == "Wrong population"
    assert audit.exclusion_reasons[0].count == 1

    # Synthesis numbers
    assert audit.matrix_rows == 2
    assert audit.reports_generated == 1
    assert audit.cited_in_reports == 5

    # Duplicates are conservative: identified - max(tracked, screened)
    # tracked = 2+1+1+0 = 4, screened = 5 -> max(4, 5) = 5 -> duplicates = 150 - 5 = 145
    assert audit.duplicates_removed == 145

    # Protocol notes survive into the audit
    assert audit.protocol_notes == "Search 2020-2026 English"

    # ── Enrichment layer ────────────────────────────────────────────────
    # Screening score distribution
    assert audit.screening_score_distribution == {"high": 3, "medium": 1, "low": 1}
    # Year distribution (chronological)
    assert [(b.key, b.count) for b in audit.year_distribution] == [
        ("2022", 1),
        ("2024", 1),
    ]
    assert audit.year_min == 2022
    assert audit.year_max == 2024
    # Top venues — both appear
    assert {v.key for v in audit.top_venues} == {"Nature", "Lancet"}
    # Recent search sessions
    assert len(audit.recent_search_sessions) == 1
    assert audit.recent_search_sessions[0].user_query == "rag medical"
    assert audit.recent_search_sessions[0].total_results == 150
    assert audit.recent_search_sessions[0].screened_count == 3
    assert audit.recent_search_sessions[0].high_score_count == 2
    # Inclusion timeline
    assert [(t.date, t.count) for t in audit.inclusion_timeline] == [
        ("2026-06-18", 1),
        ("2026-06-20", 1),
    ]
    # Quality metrics
    q = audit.quality_metrics
    assert q.matrix_avg_confidence == 2.5
    assert q.matrix_confidence_breakdown == {"high": 1, "medium": 1, "low": 0}
    assert q.full_text_success_rate == 0.5  # 1 of 2 decided
    assert q.full_text_breakdown == {"completed": 1, "raw_extracted": 0, "failed": 1, "ocr_required": 0}
    assert q.citation_validity_rate == 1.0  # 1 valid / 1 decided
    assert q.reports_by_validation == {"valid": 1, "invalid": 0, "pending": 0}


@pytest.mark.asyncio
async def test_build_project_audit_caps_screened_by_identified():
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id
    project = _make_project(project_id, owner_id)

    # Screened (8) > identified (5) — the audit must not report more screened than identified
    search_runs_rows = [
        ([{"source": "arxiv", "result_count": 5}], ["high"] * 8),
    ]
    pp_rows: list[tuple[str, str | None, str | None]] = []

    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),  # project ownership check (first)
            _scalar_result(5),
            _all_result(search_runs_rows),
            _all_result([]),  # recent sessions
            _all_result(pp_rows),
            _all_result([]),  # saved metadata
            _scalar_result(0),  # matrix count
            _one_result(_quality_row()),  # matrix quality
            _scalar_result(0),  # gaps
            _scalar_result(0),  # reports
            _all_result([]),  # report validation
            _scalar_result(0),  # cited papers
        ]
    )

    audit = await build_project_audit(db, user, project_id)
    assert audit is not None
    assert audit.records_identified == 5
    assert audit.records_screened == 5  # capped
    assert audit.records_excluded_screening == 0  # also capped


@pytest.mark.asyncio
async def test_build_project_audit_empty_project_is_valid():
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id
    project = _make_project(project_id, owner_id)

    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),  # project ownership check (first)
            _scalar_result(0),
            _all_result([]),  # search runs
            _all_result([]),  # recent sessions
            _all_result([]),  # project papers
            _all_result([]),  # saved metadata
            _scalar_result(0),  # matrix count
            _one_result(_quality_row()),  # matrix quality
            _scalar_result(0),  # gaps
            _scalar_result(0),  # reports
            _all_result([]),  # report validation
            _scalar_result(0),  # cited papers
        ]
    )

    audit = await build_project_audit(db, user, project_id)
    assert audit is not None
    assert audit.records_identified == 0
    assert audit.duplicates_removed == 0
    assert audit.records_screened == 0
    assert audit.records_included == 0
    assert audit.exclusion_reasons == []
    assert audit.identified_by_source == []
    # Empty distributions are empty (no synthetic "unknown" bucket)
    assert audit.year_distribution == []
    assert audit.top_venues == []
    assert audit.recent_search_sessions == []
    assert audit.inclusion_timeline == []
    assert audit.screening_score_distribution == {}
    # Quality metrics: no decided signals -> None rates
    q = audit.quality_metrics
    assert q.matrix_avg_confidence is None
    assert q.full_text_success_rate is None
    assert q.citation_validity_rate is None
    assert q.full_text_breakdown == {"completed": 0, "raw_extracted": 0, "failed": 0, "ocr_required": 0}


def test_markdown_export_contains_all_stages():
    audit = PrismaAuditResponse(
        project_id=uuid4(),
        project_title="My Review",
        project_topic="RAG for medical QA",
        research_question="Does it work?",
        generated_at=__import__("datetime").datetime.now(),
        identified_by_source=[],
        records_identified=100,
        duplicates_removed=20,
        records_screened=80,
        records_excluded_screening=30,
        screening_score_distribution={"high": 50, "medium": 20, "low": 10},
        full_text_assessed=50,
        full_text_not_retrieved=10,
        records_included=40,
        records_uncertain=2,
        records_excluded_final=8,
        exclusion_reasons=[],
        matrix_rows=40,
        reports_generated=1,
        cited_in_reports=20,
        protocol_notes="Use PubMed only",
        year_distribution=[],
        top_venues=[],
        year_min=None,
        year_max=None,
        inclusion_timeline=[],
        recent_search_sessions=[],
    )

    md = render_audit_markdown(audit)
    assert "# PRISMA-Style Audit: My Review" in md
    assert "Records identified" in md
    assert "Duplicates removed" in md
    assert "Records screened" in md
    assert "Full-text reports assessed" in md
    assert "Studies included" in md
    assert "Literature matrix rows" in md
    assert "Unique papers cited in reports" in md
    assert "Use PubMed only" in md
    # New: screening score distribution
    assert "Screening score distribution" in md
    assert "| high | 50 |" in md


def test_markdown_export_contains_enrichment_sections():
    from app.schemas.audit import (
        AuditHistogramPoint,
        AuditQualityMetrics,
        AuditSearchSessionSummary,
        AuditTimelinePoint,
    )

    today = date(2026, 6, 22)
    audit = PrismaAuditResponse(
        project_id=uuid4(),
        project_title="Enriched",
        project_topic="Topic",
        research_question=None,
        generated_at=datetime.combine(today, datetime.min.time()),
        identified_by_source=[],
        records_identified=10,
        duplicates_removed=0,
        records_screened=10,
        records_excluded_screening=0,
        screening_score_distribution={"high": 6, "medium": 3, "low": 1},
        full_text_assessed=10,
        full_text_not_retrieved=0,
        records_included=10,
        records_uncertain=0,
        records_excluded_final=0,
        exclusion_reasons=[],
        matrix_rows=10,
        reports_generated=2,
        cited_in_reports=8,
        protocol_notes=None,
        year_distribution=[
            AuditHistogramPoint(key="2020", count=1),
            AuditHistogramPoint(key="2024", count=9),
        ],
        top_venues=[AuditHistogramPoint(key="Nature", count=10)],
        year_min=2020,
        year_max=2024,
        inclusion_timeline=[
            AuditTimelinePoint(date="2026-06-20", count=3),
            AuditTimelinePoint(date="2026-06-22", count=7),
        ],
        recent_search_sessions=[
            AuditSearchSessionSummary(
                id="s1",
                user_query="q",
                total_results=10,
                screened_count=10,
                high_score_count=6,
                created_at=datetime.combine(today, datetime.min.time()),
            )
        ],
        quality_metrics=AuditQualityMetrics(
            matrix_avg_confidence=2.5,
            matrix_confidence_breakdown={"high": 6, "medium": 3, "low": 1},
            full_text_success_rate=1.0,
            full_text_breakdown={"completed": 10, "failed": 0, "raw_extracted": 0, "ocr_required": 0},
            citation_validity_rate=0.5,
            reports_by_validation={"valid": 1, "invalid": 1, "pending": 0},
        ),
    )

    md = render_audit_markdown(audit)
    assert "## Coverage — saved corpus" in md
    assert "2020–2024" in md
    assert "Top venues" in md
    assert "| Nature | 10 |" in md
    assert "## Recent search sessions" in md
    assert f"## Inclusion timeline (last {TIMELINE_DAY_WINDOW} days)" in md
    assert "## Quality metrics" in md
    assert "Full-text success rate | 100%" in md
    assert "Citation validity rate | 50%" in md


def test_csv_export_contains_header_and_rows():
    audit = PrismaAuditResponse(
        project_id=uuid4(),
        project_title="X",
        project_topic="t",
        research_question=None,
        generated_at=__import__("datetime").datetime.now(),
        identified_by_source=[],
        records_identified=10,
        duplicates_removed=2,
        records_screened=8,
        records_excluded_screening=3,
        screening_score_distribution={"high": 5, "medium": 2, "low": 1},
        full_text_assessed=5,
        full_text_not_retrieved=1,
        records_included=4,
        records_uncertain=0,
        records_excluded_final=0,
        exclusion_reasons=[],
        matrix_rows=4,
        reports_generated=0,
        cited_in_reports=0,
        protocol_notes=None,
        year_distribution=[],
        top_venues=[],
        year_min=None,
        year_max=None,
        inclusion_timeline=[],
        recent_search_sessions=[],
    )

    csv = render_audit_csv(audit)
    lines = [line for line in csv.strip().splitlines() if line]
    assert lines[0] == "stage,label,count"
    # 12 stage rows + 0 source rows + 0 exclusion rows + 3 screening scores
    assert len(lines) == 16
    assert "identification,records_identified,10" in csv
    assert "synthesis,cited_in_reports,0" in csv
    assert "screening_score,high,5" in csv


def test_csv_export_contains_enrichment_rows():
    from app.schemas.audit import (
        AuditHistogramPoint,
        AuditQualityMetrics,
        AuditTimelinePoint,
    )

    audit = PrismaAuditResponse(
        project_id=uuid4(),
        project_title="X",
        project_topic="t",
        research_question=None,
        generated_at=datetime.now(),
        identified_by_source=[],
        records_identified=10,
        duplicates_removed=0,
        records_screened=10,
        records_excluded_screening=0,
        screening_score_distribution={},
        full_text_assessed=10,
        full_text_not_retrieved=0,
        records_included=10,
        records_uncertain=0,
        records_excluded_final=0,
        exclusion_reasons=[],
        matrix_rows=10,
        reports_generated=1,
        cited_in_reports=8,
        protocol_notes=None,
        year_distribution=[AuditHistogramPoint(key="2024", count=10)],
        top_venues=[AuditHistogramPoint(key="Nature", count=10)],
        year_min=2024,
        year_max=2024,
        inclusion_timeline=[AuditTimelinePoint(date="2026-06-22", count=10)],
        recent_search_sessions=[],
        quality_metrics=AuditQualityMetrics(
            matrix_avg_confidence=2.7,
            matrix_confidence_breakdown={"high": 8, "medium": 2, "low": 0},
            full_text_success_rate=0.9,
            full_text_breakdown={"completed": 9, "failed": 1},
            citation_validity_rate=1.0,
            reports_by_validation={"valid": 1, "invalid": 0, "pending": 0},
        ),
    )

    csv = render_audit_csv(audit)
    assert "year,2024,10" in csv
    assert "venue,Nature,10" in csv
    assert "inclusion_timeline,2026-06-22,10" in csv
    assert "matrix_confidence,high,8" in csv
    assert "full_text_status,completed,9" in csv
    assert "report_validation,valid,1" in csv


def test_full_text_buckets_match_model_statuses():
    # FULL_TEXT_SUCCESS and FULL_TEXT_FAILURE are the canonical buckets the
    # audit uses; guard against silent renaming of the model values.
    assert {"completed", "raw_extracted"} == FULL_TEXT_SUCCESS
    assert {"failed", "ocr_required"} == FULL_TEXT_FAILURE


@pytest.mark.asyncio
async def test_build_project_audit_venue_limit_is_respected():
    """Top venues should be capped at TOP_VENUES_LIMIT."""
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id
    project = _make_project(project_id, owner_id)

    # Build TOP_VENUES_LIMIT + 3 venues to verify trimming.
    extra = TOP_VENUES_LIMIT + 3
    saved_meta_rows = [
        (2024, f"Venue {i:02d}", datetime(2026, 6, 20)) for i in range(extra)
    ]

    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),
            _scalar_result(extra),
            _all_result([]),  # search runs
            _all_result([]),  # recent sessions
            _all_result([]),  # project papers
            _all_result(saved_meta_rows),
            _scalar_result(0),
            _one_result(_quality_row()),
            _scalar_result(0),
            _scalar_result(0),
            _all_result([]),
            _scalar_result(0),
        ]
    )

    audit = await build_project_audit(db, user, project_id)
    assert audit is not None
    assert len(audit.top_venues) == TOP_VENUES_LIMIT


@pytest.mark.asyncio
async def test_build_project_audit_recent_sessions_limit():
    """At most RECENT_SESSIONS_LIMIT sessions should be returned."""
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id
    project = _make_project(project_id, owner_id)

    # The DB query uses .limit(RECENT_SESSIONS_LIMIT); the audit reflects
    # whatever the DB returns, so we hand it exactly that many rows.
    sessions = [
        (uuid4(), f"q{i}", 10, ["high"], datetime(2026, 6, 20 - i))
        for i in range(RECENT_SESSIONS_LIMIT)
    ]

    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),
            _scalar_result(10),
            _all_result([]),
            _all_result(sessions),
            _all_result([]),
            _all_result([]),
            _scalar_result(0),
            _one_result(_quality_row()),
            _scalar_result(0),
            _scalar_result(0),
            _all_result([]),
            _scalar_result(0),
        ]
    )

    audit = await build_project_audit(db, user, project_id)
    assert audit is not None
    assert len(audit.recent_search_sessions) == RECENT_SESSIONS_LIMIT


@pytest.mark.asyncio
async def test_build_project_audit_timeline_window_caps_old_dates():
    """Inclusion timeline should be capped to the last TIMELINE_DAY_WINDOW days."""
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id
    project = _make_project(project_id, owner_id)

    # Two saved papers: one within window, one far outside.
    recent_day = datetime.now(UTC).date()
    ancient_day = recent_day - timedelta(days=TIMELINE_DAY_WINDOW * 5)
    saved_meta_rows = [
        (2020, "X", datetime(recent_day.year, recent_day.month, recent_day.day)),
        (2010, "Y", datetime(ancient_day.year, ancient_day.month, ancient_day.day)),
    ]

    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),
            _scalar_result(2),
            _all_result([]),
            _all_result([]),
            _all_result([]),
            _all_result(saved_meta_rows),
            _scalar_result(0),
            _one_result(_quality_row()),
            _scalar_result(0),
            _scalar_result(0),
            _all_result([]),
            _scalar_result(0),
        ]
    )

    audit = await build_project_audit(db, user, project_id)
    assert audit is not None
    # Only the recent paper should appear in the timeline
    assert len(audit.inclusion_timeline) == 1
    assert audit.inclusion_timeline[0].date == recent_day.isoformat()
    assert audit.inclusion_timeline[0].count == 1


@pytest.mark.asyncio
async def test_build_project_audit_quality_rates_none_when_no_decisions():
    """When nothing is decided, rates should be None (not 0.0)."""
    project_id = uuid4()
    owner_id = uuid4()
    user = _make_user()
    user.id = owner_id
    project = _make_project(project_id, owner_id)

    # No saved papers → no full-text decisions, no valid reports.
    db = MagicMock()
    db.execute = _Counter(
        [
            _scalar_one_or_none(project),
            _scalar_result(0),
            _all_result([]),
            _all_result([]),
            _all_result([]),
            _all_result([]),
            _scalar_result(0),
            _one_result(_quality_row(total=0)),
            _scalar_result(0),
            _scalar_result(0),
            _all_result([]),
            _scalar_result(0),
        ]
    )

    audit = await build_project_audit(db, user, project_id)
    assert audit is not None
    q = audit.quality_metrics
    assert q.matrix_avg_confidence is None
    assert q.full_text_success_rate is None
    assert q.citation_validity_rate is None
