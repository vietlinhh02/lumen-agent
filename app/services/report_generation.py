"""Report generation with RAG and citation guardrail."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    REVIEW_WRITER_CHUNK_SYSTEM,
    REVIEW_WRITER_CHUNK_USER,
    format_protocol_for_prompt,
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

# Multi-section report generation constants
_REPORT_ANGLE_QUERIES = [
    "{topic} methodology comparison framework evaluation metrics",
    "{topic} dataset benchmark performance results ablation",
    "{topic} limitations weakness failure case generalization",
    "{topic} application domain real-world deployment practical",
    "{topic} temporal progression evolution future direction",
    "{topic} theoretical foundation assumption prior work",
    "{topic} conflicting findings disagreement debate",
    "{topic} gap underexplored missing comparison",
]
_MAX_CHUNKS_PER_ANGLE = 15
_MAX_SECTION_CHUNK_BUDGET = 30000  # chars per section
_MAX_SECTION_TOKENS = 3000
_REPORT_SECTION_CONCURRENCY = 4  # Parallel section generation
_MIN_SECTIONS_FOR_PLANNING = 5


def _build_review_retrieval_query(
    topic: str,
    research_question: str | None,
    matrix_rows: Sequence[object],
    gaps: Sequence[object],
    conflicts: Sequence[object],
    review_protocol: Mapping[str, object] | None = None,
) -> str:
    """Build a high-signal retrieval query from matrix, gap, and conflict data."""
    terms: list[str] = []

    _append_unique_term(terms, topic)
    _append_unique_term(terms, research_question)
    for keyword in _REVIEW_BASE_KEYWORDS:
        _append_unique_term(terms, keyword)

    # Fold protocol anchors (population / outcome / topic / criteria) into the
    # retrieval query so chunk fetcher biases toward protocol-relevant evidence.
    if review_protocol:
        for field in (
            "population",
            "intervention_or_topic",
            "comparison",
            "outcome",
            "notes",
        ):
            _append_unique_term(terms, _get_field(review_protocol, field))
        for list_field in (
            "research_questions",
            "inclusion_criteria",
            "exclusion_criteria",
            "source_list",
        ):
            value = _get_field(review_protocol, list_field)
            if isinstance(value, list):
                for item in value:
                    _append_unique_term(terms, item)

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


# ── Multi-Section Report Generation Helpers ──────────────────────────────────


async def _retrieve_multi_angle(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
    research_question: str | None,
    matrix_rows: Sequence[object],
    gaps: Sequence[object],
    conflicts: Sequence[object],
    review_protocol: Mapping[str, object] | None = None,
) -> list[RetrievedChunk]:
    """Run multiple thematic queries and merge + dedupe results.

    Each query targets a different angle (methodology, results, gaps, etc.)
    for broader evidence coverage than a single query.
    """
    all_chunks: list[RetrievedChunk] = []
    seen_chunk_ids: set[UUID] = set()
    seen_queries: set[str] = set()
    query_topic = topic if not research_question else f"{topic} {research_question}"
    queries = [
        _build_review_retrieval_query(
            topic, research_question, matrix_rows, gaps, conflicts, review_protocol
        ),
        *[template.format(topic=query_topic) for template in _REPORT_ANGLE_QUERIES],
    ]

    for query in queries:
        normalized_query = " ".join(query.split())
        if not normalized_query or normalized_query in seen_queries:
            continue
        seen_queries.add(normalized_query)
        try:
            chunks = await retrieve_project_evidence(
                db, project_id, normalized_query, limit=_MAX_CHUNKS_PER_ANGLE
            )
            for c in chunks:
                if c.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(c.chunk_id)
                    all_chunks.append(c)
        except Exception as exc:
            logger.warning(
                "Multi-angle retrieval query failed for '%s': %s",
                normalized_query[:40],
                exc,
            )

    # Sort by score and limit total
    all_chunks.sort(key=lambda c: c.score, reverse=True)
    all_chunks = all_chunks[:_MAX_RAG_CHUNKS]

    return all_chunks


def _group_chunks_by_paper(
    chunks: list[RetrievedChunk],
) -> dict[UUID, list[RetrievedChunk]]:
    """Group retrieved chunks by project_paper_id."""
    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)
    for paper_chunks in chunks_by_paper.values():
        paper_chunks.sort(key=lambda chunk: chunk.score, reverse=True)
    return chunks_by_paper


async def _plan_sections(
    topic: str,
    research_question: str | None,
    safe_rows: list[dict],
    safe_gaps: list[dict],
    safe_conflicts: list[dict],
    paper_catalog_str: str,
    provider,
    protocol_text: str | None = None,
) -> list[dict]:
    """Plan literature review sections using LLM.

    Returns a list of section plans, each with heading, theme, focus_paper_ids, key_angles.
    """
    protocol_block = protocol_text or "Not provided"
    plan_prompt = f"""Given the following literature:

Topic: {topic}
Research Question: {research_question or 'Not specified'}
Review protocol (anchor the section plan to the protocol's population, comparison,
outcome, and inclusion/exclusion scope):
{protocol_block}

Available Papers (ID to Title):
{paper_catalog_str}

Matrix Rows (first 10): {json.dumps(safe_rows[:10], indent=2)}
Gaps: {json.dumps(safe_gaps, indent=2) if safe_gaps else 'None'}
Conflicts: {json.dumps(safe_conflicts, indent=2) if safe_conflicts else 'None'}

Plan a literature review with 5-8 sections. Each section should cover a distinct angle:
- At least one section on methodology comparison
- At least one section on findings and results synthesis
- At least one section on limitations and challenges
- If gaps exist, at least one section addressing research gaps
- If conflicts exist, at least one section on conflicting findings
- Include a section on applications and future directions
- IMPORTANT: Ensure your planned sections collectively try to cover as many of the provided matrix rows as possible.

Return a JSON object with a "sections" array, each section having:
- "heading": section name
- "theme": 1-2 sentence description of what this section synthesizes
- "focus_paper_ids": list of paper IDs most relevant to this section
- "key_angles": list of themes this section covers (e.g., ["methodology", "results"])

Example format:
{{"sections": [
  {{"heading": "...", "theme": "...", "focus_paper_ids": ["..."], "key_angles": ["..."]}}
]}}"""

    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": plan_prompt}],
            system=(
                "You are a literature review planner. Return ONLY a JSON object "
                "with sections array."
            ),
            schema={"type": "object", "properties": {"sections": {"type": "array"}}},
            tool_name="review_plan",
            max_tokens=3000,
        )
        raw_sections = result.get("sections", [])
        if not isinstance(raw_sections, Sequence) or isinstance(raw_sections, str):
            return []

        sections = [
            section
            for section in raw_sections
            if isinstance(section, Mapping)
            and section.get("heading")
            and section.get("theme")
            and isinstance(section.get("focus_paper_ids", []), list)
        ]
        if len(sections) < _MIN_SECTIONS_FOR_PLANNING:
            logger.warning(
                "Section planning returned only %d usable sections; falling back",
                len(sections),
            )
            return []
        return [dict(section) for section in sections[:8]]
    except Exception as exc:
        logger.warning("Section planning failed: %s", exc)
        return []


async def _generate_section(
    section_plan: dict,
    chunks_by_paper: dict[UUID, list[RetrievedChunk]],
    paper_catalog_str: str,
    topic: str,
    provider,
    protocol_text: str | None = None,
) -> dict | None:
    """Generate a single section of the literature review.

    Uses focus_paper_ids to select relevant chunks, limiting context per section.
    Returns the generated section dict or None on failure.
    """
    # Get chunks from focus papers
    focus_chunks: list[RetrievedChunk] = []
    for pid_str in section_plan.get("focus_paper_ids", []):
        try:
            pid = UUID(pid_str)
            focus_chunks.extend(chunks_by_paper.get(pid, []))
        except (ValueError, TypeError):
            pass

    # Fallback: if LLM gave wrong/hallucinated UUIDs and no chunks matched,
    # use all available chunks ranked by score so the section always has evidence.
    if not focus_chunks:
        focus_chunks = [c for chunks in chunks_by_paper.values() for c in chunks]

    # Sort by score and limit chunk budget
    focus_chunks.sort(key=lambda c: c.score, reverse=True)

    chunk_parts: list[str] = []
    total = 0
    included_pids = set()
    for c in focus_chunks[:30]:
        label = c.section_label or c.content_type or "section"
        block = f"---{label} (Paper ID: {c.project_paper_id})---\n{c.chunk_text}"
        if total + len(block) > _MAX_SECTION_CHUNK_BUDGET:
            break
        chunk_parts.append(block)
        included_pids.add(str(c.project_paper_id))
        total += len(block)

    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text available."
    json.dumps(list(included_pids))

    protocol_block = protocol_text or "Not provided"
    section_prompt = f"""Write the following literature review section:

Topic: {topic}
Section: {section_plan.get('heading', 'Untitled')}
Theme: {section_plan.get('theme', '')}
Review protocol (frame this section within the protocol's population, comparison,
outcome, and inclusion scope):
{protocol_block}

Available Papers (ID to Title):
{paper_catalog_str}

Full-text evidence:
{chunk_context}

Write this section in academic prose. Each paragraph MUST cite papers using their project_paper_id.
After your first paragraph, add a blockquote starting with "**Key synthesis:**" with citations.
Structure the section with 2-3 focused paragraphs that synthesize the evidence.
"""

    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": section_prompt}],
            system=REVIEW_WRITER_CHUNK_SYSTEM,
            schema=ReviewOutput.model_json_schema(),
            tool_name="review_section",
            max_tokens=_MAX_SECTION_TOKENS,
        )
        sections = result.get("sections", [])
        if sections:
            # The LLM returns a sections array, we want the first one
            return sections[0]
        return None
    except Exception as exc:
        logger.warning(
            "Section generation failed for '%s': %s",
            section_plan.get("heading", ""),
            exc,
        )
        return None


async def _aggregate_sections(
    sections: list[dict],
    safe_conflicts: list[dict],
    safe_gaps: list[dict],
    paper_catalog_str: str,
    provider,
) -> list[dict]:
    """Final pass: weave in conflicts + gaps, ensure smooth transitions.

    Reviews generated sections and ensures conflicts/gaps are addressed.

    Reliability notes:
    - The aggregate prompt serialises ALL sections + conflicts + gaps, so the
      output JSON is large (~10 sections × full content). We default to
      16k output tokens and retry with 24k if the first attempt produces
      truncated JSON (the previous default of 6k routinely produced the
      "Expecting ',' delimiter" error on long reports).
    """
    if not sections:
        return []

    aggregate_prompt = f"""You have generated {len(sections)} sections for a literature review.
Please review and improve them:

1. Ensure each section has meaningful citations (no empty citation_paper_ids)
2. Add smooth transitions between sections
3. If conflicts exist but not addressed, add a paragraph on conflicting findings
4. If gaps exist but not addressed, add a paragraph on research gaps
5. Ensure consistent citation style throughout
6. IMPORTANT: You MUST ONLY use the valid paper IDs provided below for citations. Do not invent IDs.
Available Papers (ID to Title):
{paper_catalog_str}

Existing sections:
{json.dumps(sections, indent=2)}

Conflicts to address (if any):
{json.dumps(safe_conflicts, indent=2) if safe_conflicts else 'None'}

Research gaps to address (if any):
{json.dumps(safe_gaps, indent=2) if safe_gaps else 'None'}

Return the improved sections as a JSON object with "sections" array."""

    last_error: Exception | None = None
    max_tokens = 16000
    for attempt in range(2):
        try:
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": aggregate_prompt}],
                system=REVIEW_WRITER_CHUNK_SYSTEM,
                schema=ReviewOutput.model_json_schema(),
                tool_name="review_aggregate",
                max_tokens=max_tokens,
            )
            return result.get("sections", sections)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Section aggregation attempt %d failed (max_tokens=%d): %s",
                attempt + 1,
                max_tokens,
                exc,
            )
            max_tokens = 24000  # Bump on retry

    logger.warning(
        "Section aggregation failed after retries, falling back to original sections: %s",
        last_error,
    )
    return sections


async def generate_report(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    topic: str,
    research_question: str | None,
    title: str | None,
    include_gap_section: bool,
    selected_gap_ids: list[UUID] | None,
    review_protocol: Mapping[str, object] | None = None,
) -> dict:
    """Generate a citation-safe literature review.

    Returns dict with: id, title, validation_status, content_markdown,
    references, citation_audit.
    """
    # Render protocol once for every downstream prompt + retrieval query.
    protocol_text = format_protocol_for_prompt(review_protocol)

    # 1. Load matrix rows
    stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == project_id)
    matrix_rows = list((await db.execute(stmt)).scalars().all())
    if not matrix_rows:
        return {"error": "No matrix rows. Generate a literature matrix first.", "status": "failed"}

    # 2. Load saved project_paper IDs with Titles
    pp_stmt = select(ProjectPaper, Paper.title).join(Paper, ProjectPaper.paper_id == Paper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    pp_results = list((await db.execute(pp_stmt)).all())
    if not pp_results:
        return {"error": "No saved papers in project.", "status": "failed"}

    project_papers = [row[0] for row in pp_results]
    valid_pp_ids = {pp.id for pp in project_papers}

    paper_catalog_dict = {str(row[0].id): row[1] for row in pp_results}
    paper_catalog_str = json.dumps(paper_catalog_dict, indent=2)

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

    # 5. Build prompt data (chunk_context for fallback will be built later)
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

    report_title = title or f"Literature Review: {topic}"

    # 8. Multi-section generation flow
    provider = get_provider()

    # 8a. Multi-angle RAG retrieval for broader evidence coverage
    all_chunks = await _retrieve_multi_angle(
        db,
        project_id,
        topic,
        research_question,
        matrix_rows,
        gaps,
        conflicts,
        review_protocol=review_protocol,
    )
    chunks_by_paper = _group_chunks_by_paper(all_chunks)
    logger.info(
        "Multi-angle retrieval: %d chunks from %d papers",
        len(all_chunks),
        len(chunks_by_paper),
    )

    # 8b. Section planning
    sections_plan = await _plan_sections(
        topic,
        research_question,
        safe_rows,
        safe_gaps,
        safe_conflicts,
        paper_catalog_str,
        provider,
        protocol_text=protocol_text,
    )
    logger.info("Section planning: %d sections planned", len(sections_plan))
    chunk_context: str | None = None

    # 8c. Per-section generation (parallel)
    if sections_plan:
        sem = asyncio.Semaphore(_REPORT_SECTION_CONCURRENCY)

        async def _generate_with_semaphore(plan: dict) -> dict | None:
            async with sem:
                return await _generate_section(
                    plan,
                    chunks_by_paper,
                    paper_catalog_str,
                    topic,
                    provider,
                    protocol_text=protocol_text,
                )

        section_tasks = [_generate_with_semaphore(plan) for plan in sections_plan]
        section_results = await asyncio.gather(*section_tasks, return_exceptions=True)
        generated_sections = [
            s for s in section_results if isinstance(s, dict)
        ]
        logger.info(
            "Section generation: %d/%d sections generated",
            len(generated_sections),
            len(sections_plan),
        )
    else:
        # Fallback: use single-pass generation if planning failed
        generated_sections = []

    # 8d. Aggregate + weave conflicts/gaps
    if generated_sections:
        sections = await _aggregate_sections(
            generated_sections, safe_conflicts, safe_gaps, paper_catalog_str, provider
        )
    else:
        # Ultimate fallback: use single-pass generation with original retrieval
        # Build chunk context from all_chunks
        chunk_parts: list[str] = []
        total_chars = 0
        included_pids = set()
        for pp_id, chunks in chunks_by_paper.items():
            for c in chunks[:_MAX_CHUNKS_PER_PAPER]:
                label = c.section_label or c.content_type or "section"
                block = f"---{label} (Paper ID: {str(pp_id)})---\n{c.chunk_text}"
                if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                    break
                chunk_parts.append(block)
                included_pids.add(str(pp_id))
                total_chars += len(block)
        chunk_context = (
            "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."
        )
        json.dumps(list(included_pids))

        sections, _, _ = await _generate_and_validate(
            db,
            project_id,
            topic,
            research_question,
            paper_catalog_str,
            safe_rows,
            safe_gaps,
            safe_conflicts,
            chunk_context,
            valid_pp_ids,
            protocol_text=protocol_text,
        )

    # 9. Validate citations
    cleaned_sections, audit = await _validate_citations(db, project_id, sections)

    # 10. Retry if >30% invalid (only for single-pass fallback)
    if audit["total_citations"] > 0 and not generated_sections and chunk_context is not None:
        invalid_ratio = audit["invalid_citations"] / audit["total_citations"]
        if invalid_ratio > 0.3:
            logger.info(
                "Retrying review generation — %.0f%% invalid citations", invalid_ratio * 100
            )
            sections2, audit2, _ = await _generate_and_validate(
                db,
                project_id,
                topic,
                research_question,
                paper_catalog_str,
                safe_rows,
                safe_gaps,
                safe_conflicts,
                chunk_context,
                valid_pp_ids,
                retry_warning=(
                    f"Previous attempt had {audit['invalid_citations']} invalid citations."
                ),
                protocol_text=protocol_text,
            )
            if audit2["invalid_citations"] < audit["invalid_citations"]:
                cleaned_sections, audit = await _validate_citations(db, project_id, sections2)

    # 11. Determine validation status
    validation_status = "valid" if audit["invalid_citations"] == 0 else "invalid"

    # 12. Build references from DB
    cited_ids = set()
    for section in cleaned_sections:
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if isinstance(pid, UUID):
                    cited_ids.add(pid)
    references = await _build_references(db, cited_ids)

    # 13. Build markdown from cleaned sections
    content_markdown = _build_content_markdown(cleaned_sections, references)

    # 14. Persist
    report = await _persist_report(
        db,
        project_id,
        user_id,
        report_title,
        content_markdown,
        validation_status,
        cleaned_sections,
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
    paper_catalog_str: str,
    safe_rows: list[dict],
    safe_gaps: list[dict],
    safe_conflicts: list[dict],
    chunk_context: str,
    valid_pp_ids: set[UUID],
    retry_warning: str | None = None,
    protocol_text: str | None = None,
) -> tuple[list[dict], dict, str]:
    """Run LLM, validate citations, return (sections, audit, markdown)."""
    user_msg = REVIEW_WRITER_CHUNK_USER.format(
        project_topic=topic,
        research_question=research_question or topic,
        protocol_context=protocol_text or "Not provided",
        paper_ids_json=paper_catalog_str,
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


_UUID_PATTERN = re.compile(
    # Bracket-wrapped standard UUID (optionally with a leading space so we
    # also collapse the gap left behind when we strip the citation).
    r"\s*\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]",
    re.IGNORECASE,
)


def _strip_inlined_uuids(
    text: str, ref_map: dict[str, str]
) -> tuple[str, int]:
    """Remove bracket-wrapped paper UUIDs inlined into paragraph text.

    Some LLM generations inline raw paper UUIDs directly into the prose
    (e.g. "finding X [7feb6873-4492-4a45-8158-6141f03ff4cf]") instead of,
    or in addition to, populating the ``citation_paper_ids`` array. Those
    raw IDs then leak into the rendered markdown and confuse readers
    because they don't map to the numbered ``References`` list.

    Behaviour:
    - UUID is in ``ref_map`` → strip (the citation is already represented
      via ``citation_paper_ids`` → ``<sup>[N]</sup>`` at end of paragraph).
    - UUID is NOT in ``ref_map`` → strip and emit a warning (the LLM
      hallucinated an ID that isn't part of the project).

    Returns:
        (cleaned_text, replacements_count)
    """
    replacements = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal replacements
        uuid = match.group(1)
        if uuid in ref_map:
            logger.debug(
                "Stripping inlined UUID %s (already in ref_map)", uuid
            )
        else:
            logger.warning(
                "Stripping inlined UUID %s not in references (hallucinated)",
                uuid,
            )
        replacements += 1
        return ""

    cleaned = _UUID_PATTERN.sub(_replace, text)
    return cleaned, replacements


def _count_inlined_uuids(sections: list[dict]) -> int:
    """Count inlined UUIDs across all sections (used for telemetry).

    Used to measure LLM drift — after ``_strip_inlined_uuids`` post-
    processing this should always be zero. Emitted as a warning before
    cleanup so we know how often the LLM misbehaves.
    """
    count = 0
    for section in sections:
        for para in section.get("paragraphs", []):
            count += len(_UUID_PATTERN.findall(para.get("text", "")))
    return count


def _build_content_markdown(sections: list[dict], references: list[dict]) -> str:
    """Convert validated sections + references into rich Markdown.

    Produces:
    - Superscript citation markers: <sup>[1]</sup>
    - Blockquote key findings preserved from LLM output
    - Horizontal rules between sections
    - Structured reference table
    - Inlined paper UUIDs in paragraph text are stripped (they duplicate the
      ``citation_paper_ids`` array and confuse readers).
    """
    ref_map: dict[str, str] = {}
    for ref in references:
        ref_map[ref["project_paper_id"]] = ref["citation_label"]

    # Telemetry: warn if the LLM inlined any UUIDs into the prose so we can
    # measure drift. The post-processing below strips them.
    inlined_count = _count_inlined_uuids(sections)
    if inlined_count > 0:
        logger.warning(
            "Stripping %d inlined paper UUID(s) from section text "
            "(LLM should use citation_paper_ids array, not inline UUIDs)",
            inlined_count,
        )

    parts: list[str] = []

    for i, section in enumerate(sections):
        # Section divider (not before first section)
        if i > 0:
            parts.append("\n---\n")

        parts.append(f"## {section['heading']}\n")

        for para in section.get("paragraphs", []):
            cited_ids = para.get("citation_paper_ids", [])
            labels = [ref_map.get(str(pid), "[?]") for pid in cited_ids]

            # Strip inlined UUIDs (those belong in citation_paper_ids, not
            # in the prose). Skip the call for empty text to keep the log
            # noise-free.
            raw_text = para.get("text", "")
            text, _stripped = _strip_inlined_uuids(raw_text, ref_map)

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
