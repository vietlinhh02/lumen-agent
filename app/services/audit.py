"""Compute PRISMA-style audit counts for a project.

Reuses existing tables — SearchRun, ProjectPaper, LiteratureMatrixRow,
ReviewCitation — so the audit can be derived without writing any new
state. Numbers are read-only aggregates intended for the project
dashboard and CSV/Markdown export.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    LiteratureMatrixRow,
    Paper,
    ProjectPaper,
    ResearchGap,
    ReviewCitation,
    ReviewReport,
    SearchRun,
    User,
)
from app.schemas.audit import (
    EXCLUSION_REASON_LABELS,
    AuditExclusionReason,
    AuditExtractionSchema,
    AuditFieldCoverage,
    AuditHistogramPoint,
    AuditQualityMetrics,
    AuditSearchSessionSummary,
    AuditSourceCount,
    AuditTimelinePoint,
    PrismaAuditResponse,
)
from app.services.literature_matrix import field_coverage
from app.services.project import VALID_EXCLUSION_REASONS

logger = logging.getLogger(__name__)

# Full-text terminal states. Anything outside this set is "pending".
FULL_TEXT_SUCCESS = frozenset({"completed", "raw_extracted"})
FULL_TEXT_FAILURE = frozenset({"failed", "ocr_required"})

# Limits for enrichment data (kept narrow to avoid noisy rows in the UI).
TOP_VENUES_LIMIT = 5
RECENT_SESSIONS_LIMIT = 5
TIMELINE_DAY_WINDOW = 30

# Confidence → numeric score for averaging matrix extraction quality (1–3).
_CONFIDENCE_SCORE = case(
    (LiteratureMatrixRow.extraction_confidence == "high", 3),
    (LiteratureMatrixRow.extraction_confidence == "medium", 2),
    (LiteratureMatrixRow.extraction_confidence == "low", 1),
    else_=0,
)


async def build_project_audit(
    db: AsyncSession, user: User, project_id: UUID
) -> PrismaAuditResponse | None:
    """Compute the PRISMA-style audit numbers for one project.

    Returns ``None`` if the project does not exist or is not owned by
    *user* (callers translate this into 404).
    """
    # Lazy import to avoid a top-level cycle via services.project.
    from app.db.models import Project

    project = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.owner_id == user.id)
        )
    ).scalar_one_or_none()
    if project is None:
        return None

    # Fan out independent read-only queries concurrently.
    import asyncio

    search_total_stmt = select(func.coalesce(func.sum(SearchRun.total_results), 0)).where(
        SearchRun.project_id == project_id
    )
    # Search-run aggregates for source counts + screening score histogram.
    search_runs_stmt = select(SearchRun.source_diagnostics, SearchRun.screening_scores).where(
        SearchRun.project_id == project_id
    )
    # Recent sessions are surfaced in the Search History panel (most recent first).
    recent_sessions_stmt = (
        select(
            SearchRun.id,
            SearchRun.user_query,
            SearchRun.total_results,
            SearchRun.screening_scores,
            SearchRun.created_at,
        )
        .where(SearchRun.project_id == project_id)
        .order_by(SearchRun.created_at.desc())
        .limit(RECENT_SESSIONS_LIMIT)
    )

    status_stmt = select(
        ProjectPaper.status,
        ProjectPaper.exclusion_reason,
        ProjectPaper.full_text_status,
    ).where(ProjectPaper.project_id == project_id)

    # Saved-paper metadata for year + venue distributions and the timeline.
    # Joined with Paper to get the bibliographic fields; saved_at is used
    # for the inclusion-timeline histogram.
    saved_meta_stmt = (
        select(Paper.year, Paper.venue, ProjectPaper.saved_at)
        .join(ProjectPaper, ProjectPaper.paper_id == Paper.id)
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
        )
    )

    matrix_count_stmt = (
        select(func.count(LiteratureMatrixRow.id))
        .join(ProjectPaper, LiteratureMatrixRow.project_paper_id == ProjectPaper.id)
        .where(ProjectPaper.project_id == project_id)
    )
    matrix_quality_stmt = (
        select(
            func.count().label("total"),
            func.sum(case((_CONFIDENCE_SCORE == 3, 1), else_=0)).label("high"),
            func.sum(case((_CONFIDENCE_SCORE == 2, 1), else_=0)).label("medium"),
            func.sum(case((_CONFIDENCE_SCORE == 1, 1), else_=0)).label("low"),
            func.avg(_CONFIDENCE_SCORE).label("avg_score"),
        )
        .join(ProjectPaper, LiteratureMatrixRow.project_paper_id == ProjectPaper.id)
        .where(ProjectPaper.project_id == project_id)
    )
    # T4: load every matrix row once so we can compute per-field coverage.
    matrix_rows_for_coverage_stmt = (
        select(LiteratureMatrixRow)
        .join(ProjectPaper, LiteratureMatrixRow.project_paper_id == ProjectPaper.id)
        .where(ProjectPaper.project_id == project_id)
    )

    gap_count_stmt = select(func.count(ResearchGap.id)).where(ResearchGap.project_id == project_id)
    report_count_stmt = select(func.count(ReviewReport.id)).where(
        ReviewReport.project_id == project_id
    )
    report_validation_stmt = (
        select(ReviewReport.validation_status, func.count(ReviewReport.id))
        .where(ReviewReport.project_id == project_id)
        .group_by(ReviewReport.validation_status)
    )
    cited_papers_stmt = (
        select(func.count(func.distinct(ReviewCitation.project_paper_id)))
        .join(ReviewReport, ReviewCitation.report_id == ReviewReport.id)
        .where(ReviewReport.project_id == project_id)
    )

    (
        search_total,
        search_runs,
        recent_sessions,
        project_paper_rows,
        saved_meta,
        matrix_count,
        matrix_quality,
        matrix_rows_for_coverage,
        gap_count,
        report_count,
        report_validation,
        cited_papers,
    ) = await asyncio.gather(
        db.execute(search_total_stmt),
        db.execute(search_runs_stmt),
        db.execute(recent_sessions_stmt),
        db.execute(status_stmt),
        db.execute(saved_meta_stmt),
        db.execute(matrix_count_stmt),
        db.execute(matrix_quality_stmt),
        db.execute(matrix_rows_for_coverage_stmt),
        db.execute(gap_count_stmt),
        db.execute(report_count_stmt),
        db.execute(report_validation_stmt),
        db.execute(cited_papers_stmt),
    )

    records_identified = int(search_total.scalar() or 0)

    # Aggregate source diagnostics and screening score distribution across
    # every search session.
    source_counts: dict[str, int] = {}
    screening_score_counts: Counter[str] = Counter()
    records_screened = 0
    screening_excluded = 0
    for diagnostics, scores in search_runs.all():
        for diag in diagnostics or []:
            source = str(diag.get("source") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + int(
                diag.get("result_count") or 0
            )
        if scores:
            records_screened += len(scores)
            for score in scores:
                screening_score_counts[score] += 1
                if score != "high":
                    screening_excluded += 1

    # Cap screened by identified (search sessions can have screening scores
    # without the underlying results count being preserved in source_diagnostics
    # for old rows; this keeps the audit conservative).
    if records_identified and records_screened > records_identified:
        records_screened = records_identified
    if screening_excluded > records_screened:
        screening_excluded = records_screened

    # Bucket project papers by PRISMA-relevant status.
    status_counts: dict[str, int] = {
        "saved": 0,
        "rejected": 0,
        "uncertain": 0,
        "draft": 0,
    }
    full_text_counts: dict[str, int] = {s: 0 for s in FULL_TEXT_SUCCESS | FULL_TEXT_FAILURE}
    exclusion_counts: dict[str, int] = {r: 0 for r in VALID_EXCLUSION_REASONS}

    full_text_assessed = 0
    full_text_not_retrieved = 0
    for status, exclusion_reason, full_text_status in project_paper_rows.all():
        if status in status_counts:
            status_counts[status] += 1
        if status == "saved" and full_text_status in full_text_counts:
            full_text_counts[full_text_status] += 1
            if full_text_status in FULL_TEXT_SUCCESS:
                full_text_assessed += 1
            elif full_text_status in FULL_TEXT_FAILURE:
                full_text_not_retrieved += 1
        if status == "rejected" and exclusion_reason in exclusion_counts:
            exclusion_counts[exclusion_reason] += 1
    # Duplicates estimate: papers that search results touched more than once.
    # Without scanning every results_json payload (expensive), we approximate
    # `tracked_unique` as the largest of (papers with any project decision,
    # papers screened). The remainder is reported as duplicates — strictly
    # conservative, never claims a higher duplicate count than the data
    # supports.
    tracked_in_project = (
        status_counts["saved"]
        + status_counts["rejected"]
        + status_counts["uncertain"]
        + status_counts["draft"]
    )
    tracked_unique = min(records_identified, max(tracked_in_project, records_screened))
    duplicates_removed = max(0, records_identified - tracked_unique)

    exclusion_reasons: list[AuditExclusionReason] = [
        AuditExclusionReason(
            reason=reason,
            label=EXCLUSION_REASON_LABELS.get(reason, reason),
            count=count,
        )
        for reason, count in sorted(exclusion_counts.items(), key=lambda kv: kv[1], reverse=True)
        if count > 0
    ]

    identified_by_source = [
        AuditSourceCount(source=source, count=count)
        for source, count in sorted(source_counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # ── Enrichment layer ────────────────────────────────────────────────
    year_distribution, year_min, year_max, top_venues = _build_coverage(saved_meta)
    inclusion_timeline = _build_inclusion_timeline(saved_meta)
    recent_session_summaries = _build_recent_sessions(recent_sessions)
    quality_metrics = _build_quality_metrics(
        matrix_quality=matrix_quality,
        full_text_counts=full_text_counts,
        report_validation=report_validation,
    )

    # T4: per-field coverage from the effective extraction schema.
    from typing import cast

    from app.services.extraction_schema import get_effective_schema

    extraction_schema: AuditExtractionSchema | None = None
    try:
        eff_schema = await get_effective_schema(db, project_id)
        raw_rows = cast(
            list[LiteratureMatrixRow],
            list(matrix_rows_for_coverage.scalars().all()),
        )
        coverage = field_coverage(raw_rows, eff_schema.fields)
        field_breakdown: list[AuditFieldCoverage] = [
            AuditFieldCoverage(
                key=f["key"],
                label=f["label"],
                type=f["type"],
                is_reserved=f["is_reserved"],
                required=f["required"],
                populated=f["populated"],
                rows_total=f["rows_total"],
                coverage_rate=f["coverage_rate"],
            )
            for f in coverage.get("fields", [])
        ]
        extraction_schema = AuditExtractionSchema(
            is_default=eff_schema.is_default,
            version=eff_schema.version,
            fields_total=len(eff_schema.fields),
            custom_fields_total=sum(
                1
                for f in eff_schema.fields
                if f.key
                not in {
                    "research_problem",
                    "method",
                    "dataset_or_context",
                    "key_result",
                    "limitation",
                    "contribution",
                    "relevance",
                }
            ),
            fields=field_breakdown,
        )
    except Exception as exc:
        # Non-fatal: a transient schema-read failure should not blank the
        # rest of the audit.
        logger.warning("Could not compute T4 extraction-schema coverage: %s", exc)

    return PrismaAuditResponse(
        project_id=project.id,
        project_title=project.title,
        project_topic=project.topic,
        research_question=project.research_question,
        generated_at=datetime.now(UTC).replace(tzinfo=None),
        identified_by_source=identified_by_source,
        records_identified=records_identified,
        duplicates_removed=duplicates_removed,
        records_screened=records_screened,
        records_excluded_screening=screening_excluded,
        screening_score_distribution=dict(screening_score_counts),
        full_text_assessed=full_text_assessed,
        full_text_not_retrieved=full_text_not_retrieved,
        records_included=status_counts["saved"],
        records_uncertain=status_counts["uncertain"],
        records_excluded_final=status_counts["rejected"],
        exclusion_reasons=exclusion_reasons,
        matrix_rows=int(matrix_count.scalar() or 0),
        reports_generated=int(report_count.scalar() or 0),
        cited_in_reports=int(cited_papers.scalar() or 0),
        protocol_notes=(project.review_protocol or {}).get("notes"),
        year_distribution=year_distribution,
        year_min=year_min,
        year_max=year_max,
        top_venues=top_venues,
        inclusion_timeline=inclusion_timeline,
        recent_search_sessions=recent_session_summaries,
        quality_metrics=quality_metrics,
        extraction_schema=extraction_schema,
    )


# ── Enrichment helpers ──────────────────────────────────────────────────


def _build_coverage(
    saved_meta_result,
) -> tuple[list[AuditHistogramPoint], int | None, int | None, list[AuditHistogramPoint]]:
    """Year + venue distributions for the saved corpus.

    Papers missing year/venue are skipped silently (no synthetic "unknown"
    bucket that would inflate the visible distribution).
    """
    year_counter: Counter[int] = Counter()
    venue_counter: Counter[str] = Counter()
    for year, venue, _saved_at in saved_meta_result.all():
        if isinstance(year, int):
            year_counter[year] += 1
        if isinstance(venue, str) and venue.strip():
            venue_counter[venue.strip()] += 1

    year_distribution = [
        AuditHistogramPoint(key=str(year), count=count)
        for year, count in sorted(year_counter.items())
    ]
    year_min = min(year_counter) if year_counter else None
    year_max = max(year_counter) if year_counter else None
    top_venues = [
        AuditHistogramPoint(key=venue, count=count)
        for venue, count in venue_counter.most_common(TOP_VENUES_LIMIT)
    ]
    return year_distribution, year_min, year_max, top_venues


def _build_inclusion_timeline(saved_meta_result) -> list[AuditTimelinePoint]:
    """Group saved papers by calendar date (UTC) and emit the last 30 days.

    Empty days are intentionally omitted — bars represent activity, not
    silence, and clients can re-render at any density.
    """
    date_counter: Counter[str] = Counter()
    for _year, _venue, saved_at in saved_meta_result.all():
        if saved_at is None:
            continue
        date_counter[saved_at.date().isoformat()] += 1

    if not date_counter:
        return []

    sorted_dates = sorted(date_counter)
    end_date = date.fromisoformat(sorted_dates[-1])
    cutoff = (end_date - timedelta(days=TIMELINE_DAY_WINDOW - 1)).isoformat()
    return [AuditTimelinePoint(date=d, count=date_counter[d]) for d in sorted_dates if d >= cutoff]


def _build_recent_sessions(recent_sessions_result) -> list[AuditSearchSessionSummary]:
    """Convert the most recent search sessions into audit-friendly summaries."""
    summaries: list[AuditSearchSessionSummary] = []
    for sid, user_query, total_results, scores, created_at in recent_sessions_result.all():
        screened = len(scores) if scores else 0
        high_count = sum(1 for s in (scores or []) if s == "high")
        summaries.append(
            AuditSearchSessionSummary(
                id=str(sid),
                user_query=user_query or "",
                total_results=int(total_results or 0),
                screened_count=screened,
                high_score_count=high_count,
                created_at=created_at,
            )
        )
    return summaries


def _build_quality_metrics(
    matrix_quality,
    full_text_counts: dict[str, int],
    report_validation,
) -> AuditQualityMetrics:
    """AI-quality signals for the project.

    Returns ``None`` for ratios whose denominator is zero — that keeps the
    UI honest about cases where the signal is "not measured" rather than
    "exactly 0".
    """
    row = matrix_quality.one()
    matrix_breakdown = {
        "high": int(row.high or 0),
        "medium": int(row.medium or 0),
        "low": int(row.low or 0),
    }
    matrix_avg_confidence = round(float(row.avg_score), 2) if row.avg_score is not None else None

    full_text_success = sum(full_text_counts.get(s, 0) for s in FULL_TEXT_SUCCESS)
    full_text_failure = sum(full_text_counts.get(s, 0) for s in FULL_TEXT_FAILURE)
    full_text_decided = full_text_success + full_text_failure
    full_text_success_rate = (
        round(full_text_success / full_text_decided, 3) if full_text_decided else None
    )

    by_validation: dict[str, int] = {
        str(status): int(count) for status, count in report_validation.all()
    }
    valid_reports = by_validation.get("valid", 0)
    invalid_reports = by_validation.get("invalid", 0)
    pending_reports = by_validation.get("pending", 0)
    decided = valid_reports + invalid_reports
    citation_validity_rate = round(valid_reports / decided, 3) if decided else None

    return AuditQualityMetrics(
        matrix_avg_confidence=matrix_avg_confidence,
        matrix_confidence_breakdown=matrix_breakdown,
        full_text_success_rate=full_text_success_rate,
        full_text_breakdown=dict(full_text_counts),
        citation_validity_rate=citation_validity_rate,
        reports_by_validation={
            "valid": valid_reports,
            "invalid": invalid_reports,
            "pending": pending_reports,
        },
    )


# ── Renderers ───────────────────────────────────────────────────────────


def render_audit_markdown(audit: PrismaAuditResponse) -> str:
    """Serialize an audit to a Markdown report suitable for PRISMA appendices."""
    lines: list[str] = []
    lines.append(f"# PRISMA-Style Audit: {audit.project_title}")
    lines.append("")
    lines.append(f"_Project topic_: {audit.project_topic}")
    if audit.research_question:
        lines.append(f"_Research question_: {audit.research_question}")
    lines.append(f"_Generated at_: {audit.generated_at.isoformat()}")
    lines.append("")
    lines.append("## Identification — papers found through database searching")
    lines.append("")
    lines.append("| Source | Records identified |")
    lines.append("| --- | ---: |")
    if audit.identified_by_source:
        for src in audit.identified_by_source:
            lines.append(f"| {src.source} | {src.count} |")
    else:
        lines.append("| (no search sessions) | 0 |")
    lines.append(f"| **Total identified** | **{audit.records_identified}** |")
    lines.append("")
    lines.append("## Screening — title/abstract")
    lines.append("")
    lines.append("| Stage | Records |")
    lines.append("| --- | ---: |")
    lines.append(
        f"| Records after deduplication | {max(audit.records_identified - audit.duplicates_removed, 0)} |"
    )
    lines.append(f"| Duplicates removed | {audit.duplicates_removed} |")
    lines.append(f"| Records screened | {audit.records_screened} |")
    lines.append(f"| Records excluded at screening | {audit.records_excluded_screening} |")
    if audit.screening_score_distribution:
        lines.append("")
        lines.append("### Screening score distribution")
        lines.append("")
        lines.append("| Score | Papers |")
        lines.append("| --- | ---: |")
        for score in ("high", "medium", "low"):
            if score in audit.screening_score_distribution:
                lines.append(f"| {score} | {audit.screening_score_distribution[score]} |")
    lines.append("")
    lines.append("## Eligibility — full-text retrieval")
    lines.append("")
    lines.append("| Stage | Records |")
    lines.append("| --- | ---: |")
    lines.append(f"| Full-text reports assessed | {audit.full_text_assessed} |")
    lines.append(f"| Full-text not retrieved | {audit.full_text_not_retrieved} |")
    lines.append("")
    lines.append("## Included — final corpus")
    lines.append("")
    lines.append("| Stage | Records |")
    lines.append("| --- | ---: |")
    lines.append(f"| Studies included | {audit.records_included} |")
    lines.append(f"| Studies uncertain (pending review) | {audit.records_uncertain} |")
    lines.append(f"| Studies excluded after full-text | {audit.records_excluded_final} |")
    lines.append("")
    if audit.exclusion_reasons:
        lines.append("### Exclusion reasons")
        lines.append("")
        lines.append("| Reason | Studies |")
        lines.append("| --- | ---: |")
        for r in audit.exclusion_reasons:
            lines.append(f"| {r.label} (`{r.reason}`) | {r.count} |")
        lines.append("")
    lines.append("## Synthesis — downstream artifacts")
    lines.append("")
    lines.append("| Artifact | Count |")
    lines.append("| --- | ---: |")
    lines.append(f"| Literature matrix rows | {audit.matrix_rows} |")
    lines.append(f"| Reports generated | {audit.reports_generated} |")
    lines.append(f"| Unique papers cited in reports | {audit.cited_in_reports} |")
    lines.append("")
    if audit.year_distribution or audit.top_venues:
        lines.append("## Coverage — saved corpus")
        lines.append("")
        if audit.year_distribution:
            year_range = (
                f"{audit.year_min}–{audit.year_max}"
                if audit.year_min is not None and audit.year_max is not None
                else "n/a"
            )
            lines.append(f"_Publication year range_: **{year_range}**")
            lines.append("")
            lines.append("| Year | Papers |")
            lines.append("| --- | ---: |")
            for bucket in audit.year_distribution:
                lines.append(f"| {bucket.key} | {bucket.count} |")
            lines.append("")
        if audit.top_venues:
            lines.append("### Top venues")
            lines.append("")
            lines.append("| Venue | Papers |")
            lines.append("| --- | ---: |")
            for venue in audit.top_venues:
                lines.append(f"| {venue.key} | {venue.count} |")
            lines.append("")
    if audit.recent_search_sessions:
        lines.append("## Recent search sessions")
        lines.append("")
        lines.append("| Date | Query | Results | Screened | High |")
        lines.append("| --- | --- | ---: | ---: | ---: |")
        for s in audit.recent_search_sessions:
            lines.append(
                f"| {s.created_at.date().isoformat()} | {s.user_query or '(empty)'} | "
                f"{s.total_results} | {s.screened_count} | {s.high_score_count} |"
            )
        lines.append("")
    if audit.inclusion_timeline:
        lines.append(f"## Inclusion timeline (last {TIMELINE_DAY_WINDOW} days)")
        lines.append("")
        lines.append("| Date | Papers saved |")
        lines.append("| --- | ---: |")
        for point in audit.inclusion_timeline:
            lines.append(f"| {point.date} | {point.count} |")
        lines.append("")
    q = audit.quality_metrics
    has_quality = (
        q.matrix_avg_confidence is not None
        or q.full_text_success_rate is not None
        or q.citation_validity_rate is not None
        or any(q.matrix_confidence_breakdown.values())
        or any(q.reports_by_validation.values())
    )
    if has_quality:
        lines.append("## Quality metrics")
        lines.append("")
        lines.append("| Signal | Value |")
        lines.append("| --- | ---: |")
        if q.matrix_avg_confidence is not None:
            lines.append(f"| Matrix extraction confidence (avg, 1–3) | {q.matrix_avg_confidence} |")
        if any(q.matrix_confidence_breakdown.values()):
            breakdown = ", ".join(f"{k}={v}" for k, v in q.matrix_confidence_breakdown.items() if v)
            lines.append(f"| Matrix confidence breakdown | {breakdown} |")
        if q.full_text_success_rate is not None:
            lines.append(f"| Full-text success rate | {q.full_text_success_rate:.0%} |")
        if q.citation_validity_rate is not None:
            lines.append(f"| Citation validity rate | {q.citation_validity_rate:.0%} |")
        if any(q.reports_by_validation.values()):
            lines.append(
                f"| Reports by validation | "
                f"valid={q.reports_by_validation.get('valid', 0)}, "
                f"invalid={q.reports_by_validation.get('invalid', 0)}, "
                f"pending={q.reports_by_validation.get('pending', 0)} |"
            )
        lines.append("")
    if audit.protocol_notes:
        lines.append("## Protocol notes")
        lines.append("")
        lines.append(audit.protocol_notes)
        lines.append("")
    if audit.extraction_schema and audit.extraction_schema.fields:
        lines.append("## Extraction schema coverage (T4)")
        lines.append("")
        lines.append(
            f"_{audit.extraction_schema.fields_total} field(s) defined"
            f" ({audit.extraction_schema.custom_fields_total} custom)."
            f" Schema {'is the system default' if audit.extraction_schema.is_default else f'version {audit.extraction_schema.version}'}._"
        )
        lines.append("")
        lines.append("| Field | Type | Reserved | Required | Populated | Coverage |")
        lines.append("| --- | --- | --- | --- | ---: | ---: |")
        for f in audit.extraction_schema.fields:
            lines.append(
                f"| {f.label} (`{f.key}`) | {f.type} | "
                f"{'yes' if f.is_reserved else 'no'} | "
                f"{'yes' if f.required else 'no'} | "
                f"{f.populated} / {f.rows_total} | "
                f"{f.coverage_rate:.0%} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_audit_csv(audit: PrismaAuditResponse) -> str:
    """Serialize an audit to CSV (one row per stage)."""
    header = "stage,label,count\n"
    rows: list[tuple[str, str, int]] = [
        ("identification", "records_identified", audit.records_identified),
        ("identification", "duplicates_removed", audit.duplicates_removed),
        ("screening", "records_screened", audit.records_screened),
        ("screening", "records_excluded_screening", audit.records_excluded_screening),
        ("eligibility", "full_text_assessed", audit.full_text_assessed),
        ("eligibility", "full_text_not_retrieved", audit.full_text_not_retrieved),
        ("included", "records_included", audit.records_included),
        ("included", "records_uncertain", audit.records_uncertain),
        ("included", "records_excluded_final", audit.records_excluded_final),
        ("synthesis", "matrix_rows", audit.matrix_rows),
        ("synthesis", "reports_generated", audit.reports_generated),
        ("synthesis", "cited_in_reports", audit.cited_in_reports),
    ]
    for src in audit.identified_by_source:
        rows.append(("identification_source", src.source, src.count))
    for r in audit.exclusion_reasons:
        rows.append(("exclusion_reason", r.reason, r.count))
    for score, count in audit.screening_score_distribution.items():
        rows.append(("screening_score", score, count))
    for bucket in audit.year_distribution:
        rows.append(("year", bucket.key, bucket.count))
    for venue in audit.top_venues:
        rows.append(("venue", venue.key, venue.count))
    for point in audit.inclusion_timeline:
        rows.append(("inclusion_timeline", point.date, point.count))
    q = audit.quality_metrics
    for k, v in q.matrix_confidence_breakdown.items():
        rows.append(("matrix_confidence", k, v))
    for k, v in q.full_text_breakdown.items():
        rows.append(("full_text_status", k, v))
    for k, v in q.reports_by_validation.items():
        rows.append(("report_validation", k, v))
    if audit.extraction_schema and audit.extraction_schema.fields:
        rows.append(
            (
                "extraction_schema",
                "fields_total",
                audit.extraction_schema.fields_total,
            )
        )
        rows.append(
            (
                "extraction_schema",
                "custom_fields_total",
                audit.extraction_schema.custom_fields_total,
            )
        )
        rows.append(
            (
                "extraction_schema",
                "version",
                audit.extraction_schema.version,
            )
        )
        for f in audit.extraction_schema.fields:
            rows.append(
                (
                    "extraction_field",
                    f.key,
                    f.populated,
                )
            )
    body = "\n".join(f"{stage},{label},{count}" for stage, label, count in rows)
    return header + body + "\n"


__all__ = [
    "build_project_audit",
    "render_audit_markdown",
    "render_audit_csv",
    "FULL_TEXT_SUCCESS",
    "FULL_TEXT_FAILURE",
    "TOP_VENUES_LIMIT",
    "RECENT_SESSIONS_LIMIT",
    "TIMELINE_DAY_WINDOW",
]
