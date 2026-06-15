"""Report generation with RAG and citation guardrail."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    REVIEW_WRITER_CHUNK_SYSTEM,
    REVIEW_WRITER_CHUNK_USER,
)
from app.ai.provider import get_provider
from app.ai.structured_outputs import ReviewOutput
from app.db.models import (
    ConflictingFinding,
    LiteratureMatrixRow,
    Paper,
    ProjectPaper,
    ResearchGap,
    ReviewCitation,
    ReviewReport,
)
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence

logger = logging.getLogger(__name__)

_MAX_RAG_CHUNKS = 50
_MAX_CHUNKS_PER_PAPER = 5
_MAX_CHUNK_CONTEXT_CHARS = 12000
_MAX_REVIEW_QUERY_TERMS = 80
_MAX_REVIEW_QUERY_CHARS = 3000
_REVIEW_BASE_KEYWORDS = (
    "literature review synthesis",
    "method comparison",
    "dataset context",
    "key results",
    "limitations",
    "research gaps",
    "conflicting findings",
)


def _build_review_retrieval_query(
    topic: str,
    research_question: str | None,
    matrix_rows: Sequence[object],
    gaps: Sequence[object],
    conflicts: Sequence[object],
) -> str:
    """Build a high-signal retrieval query from matrix, gap, and conflict data."""
    terms: list[str] = []

    _append_unique_term(terms, topic)
    _append_unique_term(terms, research_question)
    for keyword in _REVIEW_BASE_KEYWORDS:
        _append_unique_term(terms, keyword)

    for row in matrix_rows:
        for field in (
            "research_problem",
            "method",
            "dataset_or_context",
            "key_result",
            "limitation",
            "contribution",
            "relevance",
        ):
            _append_unique_term(terms, getattr(row, field, None))

    for gap in gaps:
        for field in ("title", "description", "suggested_direction", "evidence_summary"):
            _append_unique_term(terms, _get_field(gap, field))

    for conflict in conflicts:
        for field in (
            "title",
            "description",
            "shared_context",
            "claim_a",
            "claim_b",
            "possible_explanation",
        ):
            _append_unique_term(terms, _get_field(conflict, field))

    return " ".join(terms[:_MAX_REVIEW_QUERY_TERMS])[:_MAX_REVIEW_QUERY_CHARS]


def _append_unique_term(terms: list[str], value: object) -> None:
    text = _normalize_query_term(value)
    if not text:
        return
    if text.lower() in {term.lower() for term in terms}:
        return
    terms.append(text)


def _get_field(source: object, field: str) -> object:
    if isinstance(source, Mapping):
        source_map = cast(Mapping[str, object], source)
        return source_map.get(field)
    return getattr(source, field, None)


def _normalize_query_term(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.lower() in {"not specified", "none", "null", "n/a"}:
        return ""
    return " ".join(text.split())


async def generate_report(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    topic: str,
    research_question: str | None,
    title: str | None,
    include_gap_section: bool,
    selected_gap_ids: list[UUID] | None,
) -> dict:
    """Generate a citation-safe literature review.

    Returns dict with: id, title, validation_status, content_markdown,
    references, citation_audit.
    """
    # 1. Load matrix rows
    stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == project_id)
    matrix_rows = list((await db.execute(stmt)).scalars().all())
    if not matrix_rows:
        return {"error": "No matrix rows. Generate a literature matrix first.", "status": "failed"}

    # 2. Load saved project_paper IDs
    pp_stmt = select(ProjectPaper).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    project_papers = list((await db.execute(pp_stmt)).scalars().all())
    if not project_papers:
        return {"error": "No saved papers in project.", "status": "failed"}
    valid_pp_ids = {pp.id for pp in project_papers}

    # 3. Load gaps (optional)
    gaps: list[ResearchGap] = []
    if include_gap_section:
        gap_stmt = select(ResearchGap).where(ResearchGap.project_id == project_id)
        if selected_gap_ids:
            gap_stmt = gap_stmt.where(ResearchGap.id.in_(selected_gap_ids))
        gaps = list((await db.execute(gap_stmt)).scalars().all())

    # 4. Load conflicts so report generation can address matrix gap/conflict findings
    conflict_stmt = select(ConflictingFinding).where(ConflictingFinding.project_id == project_id)
    conflicts = list((await db.execute(conflict_stmt)).scalars().all())

    # 5. RAG retrieval
    query = _build_review_retrieval_query(topic, research_question, matrix_rows, gaps, conflicts)
    all_chunks = await retrieve_project_evidence(db, project_id, query, limit=_MAX_RAG_CHUNKS)
    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 6. Build chunk context
    chunk_parts: list[str] = []
    total_chars = 0
    for pp_id, chunks in chunks_by_paper.items():
        for c in chunks[:_MAX_CHUNKS_PER_PAPER]:
            label = c.section_label or c.content_type or "section"
            block = f"---{label} (paper {str(pp_id)[:8]})---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                break
            chunk_parts.append(block)
            total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    # 7. Build prompt
    safe_rows = _rows_to_json_safe(
        [
            {
                "project_paper_id": r.project_paper_id,
                "research_problem": r.research_problem,
                "method": r.method,
                "dataset_or_context": r.dataset_or_context,
                "key_result": r.key_result,
                "limitation": r.limitation,
                "contribution": r.contribution,
                "relevance": r.relevance,
            }
            for r in matrix_rows
        ]
    )
    safe_gaps = _rows_to_json_safe(
        [
            {
                "title": g.title,
                "description": g.description,
                "suggested_direction": g.suggested_direction,
                "evidence_summary": g.evidence_summary,
            }
            for g in gaps
        ]
    )
    safe_conflicts = _rows_to_json_safe(
        [
            {
                "title": c.title,
                "description": c.description,
                "paper_a_id": c.paper_a_id,
                "paper_b_id": c.paper_b_id,
                "shared_context": c.shared_context,
                "claim_a": c.claim_a,
                "claim_b": c.claim_b,
                "possible_explanation": c.possible_explanation,
                "confidence": c.confidence,
            }
            for c in conflicts
        ]
    )
    paper_ids_json = json.dumps([str(pp.id) for pp in project_papers])

    report_title = title or f"Literature Review: {topic}"

    # 8. First LLM attempt
    sections, audit, content_markdown = await _generate_and_validate(
        db,
        project_id,
        topic,
        research_question,
        paper_ids_json,
        safe_rows,
        safe_gaps,
        safe_conflicts,
        chunk_context,
        valid_pp_ids,
    )

    # 9. Retry if >30% invalid
    if audit["total_citations"] > 0:
        invalid_ratio = audit["invalid_citations"] / audit["total_citations"]
        if invalid_ratio > 0.3:
            logger.info(
                "Retrying review generation — %.0f%% invalid citations", invalid_ratio * 100
            )
            sections2, audit2, content_markdown2 = await _generate_and_validate(
                db,
                project_id,
                topic,
                research_question,
                paper_ids_json,
                safe_rows,
                safe_gaps,
                safe_conflicts,
                chunk_context,
                valid_pp_ids,
                retry_warning=(
                    f"Previous attempt had {audit['invalid_citations']} invalid citations."
                ),
            )
            if audit2["invalid_citations"] < audit["invalid_citations"]:
                sections, audit, content_markdown = sections2, audit2, content_markdown2

    # 10. Determine validation status
    validation_status = "valid" if audit["invalid_citations"] == 0 else "invalid"

    # 11. Build references from DB
    cited_ids = set()
    for section in sections:
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if isinstance(pid, UUID):
                    cited_ids.add(pid)
    references = await _build_references(db, cited_ids)

    # 12. Persist
    report = await _persist_report(
        db,
        project_id,
        user_id,
        report_title,
        content_markdown,
        validation_status,
        sections,
    )

    return {
        "id": str(report.id),
        "title": report_title,
        "validation_status": validation_status,
        "content_markdown": content_markdown,
        "references": references,
        "citation_audit": audit,
    }


async def _generate_and_validate(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
    research_question: str | None,
    paper_ids_json: str,
    safe_rows: list[dict],
    safe_gaps: list[dict],
    safe_conflicts: list[dict],
    chunk_context: str,
    valid_pp_ids: set[UUID],
    retry_warning: str | None = None,
) -> tuple[list[dict], dict, str]:
    """Run LLM, validate citations, return (sections, audit, markdown)."""
    user_msg = REVIEW_WRITER_CHUNK_USER.format(
        project_topic=topic,
        research_question=research_question or topic,
        paper_ids_json=paper_ids_json,
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        gaps_json=json.dumps(safe_gaps, indent=2),
        conflicts_json=json.dumps(safe_conflicts, indent=2),
        chunk_context=chunk_context,
    )
    if retry_warning:
        user_msg += f"\n\nWARNING: {retry_warning} Use ONLY the paper IDs listed above."

    provider = get_provider()
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": user_msg}],
        system=REVIEW_WRITER_CHUNK_SYSTEM,
        schema=ReviewOutput.model_json_schema(),
        tool_name="review_report",
        max_tokens=8000,
    )
    sections = result.get("sections", [])

    # Validate citations
    cleaned_sections, audit = await _validate_citations(db, project_id, sections)
    references = await _build_references(
        db,
        {
            pid
            for s in cleaned_sections
            for p in s.get("paragraphs", [])
            for pid in p.get("citation_paper_ids", [])
            if isinstance(pid, UUID)
        },
    )
    content_markdown = _build_content_markdown(cleaned_sections, references)

    return cleaned_sections, audit, content_markdown


async def _validate_citations(
    db: AsyncSession,
    project_id: UUID,
    sections: list[dict],
) -> tuple[list[dict], dict]:
    """Validate citation IDs against project_papers.

    Returns (cleaned_sections, audit).
    - Removes paragraphs with zero valid citations.
    - Trims invalid IDs from paragraphs that have some valid IDs.
    """
    stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(stmt)).scalars().all())

    total = 0
    invalid = 0
    valid_cited_ids: set[UUID] = set()
    cleaned_sections: list[dict] = []

    for section in sections:
        cleaned_paras: list[dict] = []
        for para in section.get("paragraphs", []):
            raw_ids = para.get("citation_paper_ids", [])
            total += len(raw_ids)
            valid_ids: list[UUID] = []
            for pid in raw_ids:
                try:
                    uid = UUID(pid) if isinstance(pid, str) else pid
                    if uid in valid_pp_ids:
                        valid_ids.append(uid)
                        valid_cited_ids.add(uid)
                    else:
                        invalid += 1
                except (ValueError, TypeError):
                    invalid += 1
            if valid_ids:
                cleaned_paras.append({**para, "citation_paper_ids": valid_ids})
        if cleaned_paras:
            cleaned_sections.append({**section, "paragraphs": cleaned_paras})

    uncited = len(valid_pp_ids - valid_cited_ids)
    return cleaned_sections, {
        "total_citations": total,
        "invalid_citations": invalid,
        "valid_citations": total - invalid,
        "uncited_saved_papers": uncited,
    }


async def _build_references(db: AsyncSession, cited_paper_ids: set[UUID]) -> list[dict]:
    """Build reference list from DB paper metadata."""
    if not cited_paper_ids:
        return []

    # Load project_papers → papers
    stmt = select(ProjectPaper).where(ProjectPaper.id.in_(cited_paper_ids))
    pps = (await db.execute(stmt)).scalars().all()

    paper_ids = [pp.paper_id for pp in pps]
    paper_stmt = select(Paper).where(Paper.id.in_(paper_ids))
    papers_result = (await db.execute(paper_stmt)).scalars().all()
    paper_map = {p.id: p for p in papers_result}

    references: list[dict] = []
    for i, pp in enumerate(pps):
        paper = paper_map.get(pp.paper_id)
        if not paper:
            continue
        authors = []
        for a in paper.authors or []:
            if isinstance(a, dict):
                authors.append(a.get("name", str(a)))
            else:
                authors.append(str(a))
        references.append(
            {
                "citation_label": f"[{i + 1}]",
                "project_paper_id": str(pp.id),
                "title": paper.title,
                "authors": authors,
                "year": paper.year,
                "url": paper.url,
            }
        )
    return references


def _build_content_markdown(sections: list[dict], references: list[dict]) -> str:
    """Convert validated sections + references into rich Markdown.

    Produces:
    - Superscript citation markers: <sup>[1]</sup>
    - Blockquote key findings preserved from LLM output
    - Horizontal rules between sections
    - Structured reference table
    """
    ref_map: dict[str, str] = {}
    for ref in references:
        ref_map[ref["project_paper_id"]] = ref["citation_label"]

    parts: list[str] = []

    for i, section in enumerate(sections):
        # Section divider (not before first section)
        if i > 0:
            parts.append("\n---\n")

        parts.append(f"## {section['heading']}\n")

        for para in section.get("paragraphs", []):
            cited_ids = para.get("citation_paper_ids", [])
            labels = [ref_map.get(str(pid), "[?]") for pid in cited_ids]

            text = para.get("text", "")

            # Detect if this is a blockquote (starts with **Key finding:** etc.)
            is_blockquote = (
                text.lstrip().startswith("**Key ")
                or text.lstrip().startswith("**Research gap:")
                or text.lstrip().startswith("**Limitation:")
            )

            # Build citation superscripts
            sup_parts = [f"<sup>{label}</sup>" for label in labels]
            citation_html = " ".join(sup_parts)

            if is_blockquote:
                # Render as blockquote with citation badges
                parts.append(f"> {text} {citation_html}\n")
            else:
                # Regular paragraph with inline superscript citations
                parts.append(f"{text} {citation_html}\n")

    # References section
    parts.append("\n---\n\n## References\n")

    if references:
        # Build a structured reference list with metadata
        for ref in references:
            authors = ", ".join(ref["authors"][:3])
            if len(ref["authors"]) > 3:
                authors += " et al."
            year = ref.get("year") or "n.d."
            title = ref["title"]
            url = ref.get("url")

            # Format: [1] Author(s) (Year). *Title*. [Link](url)
            link_part = f" · [Link]({url})" if url else ""
            parts.append(f"{ref['citation_label']} {authors} ({year}). *{title}*{link_part}\n")
    else:
        parts.append("*No references cited.*\n")

    return "\n".join(parts)


async def _persist_report(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    content_markdown: str,
    validation_status: str,
    sections: list[dict],
) -> ReviewReport:
    """Save report + citations to DB."""
    report = ReviewReport(
        project_id=project_id,
        created_by=user_id,
        title=title,
        content_markdown=content_markdown,
        validation_status=validation_status,
    )
    db.add(report)
    await db.flush()

    # Persist citations
    citation_idx = 0
    for para_idx, section in enumerate(sections):
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if not isinstance(pid, UUID):
                    continue
                citation_idx += 1
                citation = ReviewCitation(
                    report_id=report.id,
                    project_paper_id=pid,
                    citation_label=f"[{citation_idx}]",
                    paragraph_index=para_idx,
                )
                db.add(citation)

    await db.commit()
    await db.refresh(report)
    return report


def _rows_to_json_safe(rows: list[dict]) -> list[dict]:
    """Convert UUID fields to strings so rows are JSON-serializable."""
    return [{k: str(v) if isinstance(v, UUID) else v for k, v in row.items()} for row in rows]


async def get_reports_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[ReviewReport]:
    """List reports for a project."""
    stmt = (
        select(ReviewReport)
        .where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_report_by_id(
    db: AsyncSession,
    project_id: UUID,
    report_id: UUID,
) -> ReviewReport | None:
    """Get a single report by ID."""
    stmt = select(ReviewReport).where(
        ReviewReport.id == report_id,
        ReviewReport.project_id == project_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()
