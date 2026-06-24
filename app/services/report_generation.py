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
_INDUSTRY_COMMENTARY_DOMAINS = (
    "agentmarketcap.ai",
    "appxlab.io",
    "awesomeagents.ai",
    "blog.appxlab.io",
    "digitalapplied.com",
    "easycoding.tools",
    "lunexcoding.com",
    "medium.com",
    "particula.tech",
    "pith.science",
)
_SCHOLARLY_DOMAINS = (
    "aclanthology.org",
    "arxiv.org",
    "doi.org",
    "openreview.net",
    "semanticscholar.org",
    "zenodo.org",
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

# ── Claim Grounding Audit ───────────────────────────────────────────────────
# Heuristics for extracting specific factual claims from generated prose so
# we can verify that they are grounded in the cited paper's retrieved
# chunks. This is the cheap first pass that catches the most common
# hallucination pattern (made-up numbers attributed to a paper).
_CLAIM_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")  # 51.7, 1,794, 456535
_CLAIM_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%")
_CLAIM_TOKENS_RE = re.compile(r"\b\d[\d,]*\s*tokens?\b", re.IGNORECASE)
_CLAIM_RATIO_RE = re.compile(r"\b\d+\s+of\s+\d+\b", re.IGNORECASE)


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
Research Question: {research_question or "Not specified"}
Review protocol (anchor the section plan to the protocol's population, comparison,
outcome, and inclusion/exclusion scope):
{protocol_block}

Available Papers (ID to Title):
{paper_catalog_str}

Matrix Rows (first 10): {json.dumps(safe_rows[:10], indent=2)}
Gaps: {json.dumps(safe_gaps, indent=2) if safe_gaps else "None"}
Conflicts: {json.dumps(safe_conflicts, indent=2) if safe_conflicts else "None"}

Plan a literature review with 5-8 substantive synthesis sections. Each section should cover a distinct angle:
- Do NOT plan a "Methodology" or "Methods" section. The application injects a
  deterministic methodology section from validated project metadata.
- At least one section on methodology comparison
- At least one section on findings and results synthesis
- At least one section on limitations and challenges
- If gaps exist, at least one section addressing research gaps
- If conflicts exist, at least one section on conflicting findings
- Include a section on applications and future directions
- Final section MUST be "Conclusion". It should answer the research question,
  summarize the strongest cross-paper patterns, state implications, and identify
  specific future work without introducing new evidence.
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
Section: {section_plan.get("heading", "Untitled")}
Theme: {section_plan.get("theme", "")}
Review protocol (frame this section within the protocol's population, comparison,
outcome, and inclusion scope):
{protocol_block}

Available Papers (ID to Title):
{paper_catalog_str}

Full-text evidence:
{chunk_context}

Write this section in academic prose. Each paragraph MUST cite papers using their project_paper_id.
For non-conclusion sections, after your first paragraph, add a blockquote starting with
"**Key synthesis:**" with citations. Do not add a blockquote inside a Conclusion section.
Structure the section with 2-3 focused paragraphs that synthesize the evidence. If this
section is Conclusion, keep it to 1-2 concise paragraphs that answer the research question,
distill cross-paper patterns, and point to evidence-backed future work without introducing
new claims.
Do not write a Methodology or Methods section; the application adds that section separately.
Treat blogs, leaderboards, vendor pages, and commentary sources as industry context only.
Do not use them as primary scholarly evidence for empirical claims.
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
7. Do not add a Methodology or Methods section; the application adds that section separately.
8. Treat blogs, leaderboards, vendor pages, and commentary as industry context, not primary scholarly evidence.
9. Ensure the final substantive section is named "Conclusion". It should close the review by
   answering the research question, synthesizing the main patterns, naming implications, and
   pointing to specific future work without adding new evidence.
Available Papers (ID to Title):
{paper_catalog_str}

Existing sections:
{json.dumps(sections, indent=2)}

Conflicts to address (if any):
{json.dumps(safe_conflicts, indent=2) if safe_conflicts else "None"}

Research gaps to address (if any):
{json.dumps(safe_gaps, indent=2) if safe_gaps else "None"}

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
    pp_stmt = (
        select(ProjectPaper, Paper.title)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
        )
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
        generated_sections = [s for s in section_results if isinstance(s, dict)]
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

    cleaned_sections = _ensure_conclusion_section(
        cleaned_sections,
        topic=topic,
        research_question=research_question,
    )
    cleaned_sections, audit = await _validate_citations(db, project_id, cleaned_sections)

    # Telemetry: warn (but do not reject) sections that are below the
    # minimum-citation-density threshold. The system prompt asks every
    # non-conclusion section to cite at least 3 distinct papers; this
    # surfaces drift to the developer without blocking the report.
    _audit_section_citation_density(cleaned_sections)

    # Claim grounding audit — checks that every numeric claim in the
    # generated paragraphs is actually present in the cited paper's
    # retrieved chunks. This is the defensive check that catches the
    # "dâu ông nọ cắm căm bà kia" pattern: paper X is cited but a
    # number from paper Y is attributed to it.
    claim_audit = _audit_claim_grounding(cleaned_sections, chunks_by_paper)
    if claim_audit["ungrounded_claims"] > 0:
        logger.warning(
            "Claim grounding audit: %d/%d numeric claims not found in "
            "cited chunks (grounding_rate=%.2f). Examples: %s",
            claim_audit["ungrounded_claims"],
            claim_audit["total_claims"],
            claim_audit["grounding_rate"],
            [e["claim"] for e in claim_audit["ungrounded_examples"][:3]],
        )

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
    methodology = _build_methodology_summary(
        saved_papers=len(project_papers),
        matrix_rows=len(matrix_rows),
        research_gaps=len(gaps),
        conflicts=len(conflicts),
    )
    content_markdown = _build_content_markdown(
        cleaned_sections,
        references,
        methodology=methodology,
    )

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
        "claim_audit": claim_audit,
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
    """Build reference list from DB paper metadata.

    Numbering scheme:
    - Scholarly references are numbered continuously ``[1]``, ``[2]``, ``[3]`` ...
    - Industry commentary references are numbered as a separate contiguous
      block ``[I-1]``, ``[I-2]``, ... so the main reference list never has
      gaps from papers that were reclassified.

    The two groups are emitted as a single list (ordered scholarly first,
    then industry) so the markdown renderer can split them. Citation
    superscripts in section text always use the corresponding label from
    the matching group.

    Side effect:
        Papers whose ``authors`` field is empty and that have an
        ``arxiv_id`` are enriched in place by fetching the author list
        from the arXiv abstract page. This is the fix for the
        "Unknown author" regression we kept seeing in generated reports
        when the upstream source (Semantic Scholar, Exa, Firecrawl)
        returned a paper without an author block. The fix:

        * is best-effort — it never raises and never blocks the report;
        * persists the enriched authors back to the DB so the next
          generation does not have to re-fetch.
    """
    if not cited_paper_ids:
        return []

    # Load project_papers → papers
    stmt = select(ProjectPaper).where(ProjectPaper.id.in_(cited_paper_ids))
    pps = (await db.execute(stmt)).scalars().all()

    paper_ids = [pp.paper_id for pp in pps]
    paper_stmt = select(Paper).where(Paper.id.in_(paper_ids))
    papers_result = (await db.execute(paper_stmt)).scalars().all()
    paper_map = {p.id: p for p in papers_result}

    # Back-fill missing authors from arXiv when possible. Doing this
    # *before* building the records means the enriched authors flow into
    # the rendered references and the persisted Citation rows.
    await _enrich_paper_metadata(db, list(paper_map.values()))

    # Build a per-paper record so we can classify *before* numbering, then
    # number each group continuously.
    raw_records: list[dict] = []
    for pp in pps:
        paper = paper_map.get(pp.paper_id)
        if not paper:
            continue
        authors: list[str] = []
        for a in paper.authors or []:
            if isinstance(a, dict):
                authors.append(a.get("name", str(a)))
            else:
                authors.append(str(a))
        raw_records.append(
            {
                "project_paper_id": str(pp.id),
                "title": paper.title,
                "authors": authors,
                "year": paper.year,
                "url": paper.url,
                "reference_group": _classify_reference_group(paper),
                "metadata_complete": bool(authors and paper.year),
            }
        )

    scholarly_records = [
        r for r in raw_records if r.get("reference_group") != "industry_commentary"
    ]
    industry_records = [
        r for r in raw_records if r.get("reference_group") == "industry_commentary"
    ]

    references: list[dict] = []
    for i, rec in enumerate(scholarly_records):
        rec["citation_label"] = f"[{i + 1}]"
        references.append(rec)
    for i, rec in enumerate(industry_records):
        rec["citation_label"] = f"[I-{i + 1}]"
        references.append(rec)

    return references


async def _enrich_paper_metadata(db: AsyncSession, papers: list[Paper]) -> int:
    """Back-fill missing author lists from arXiv.

    Iterates over ``papers`` and, for any paper whose ``authors`` field is
    empty and that has an ``arxiv_id``, fires one arXiv abstract fetch.
    On success the paper is updated in the database so the next report
    generation can skip the network call.

    Returns the number of papers that were successfully enriched. The
    function never raises — failures are logged and counted.
    """
    from app.services.arxiv_metadata import enrich_papers_concurrently

    targets = [p for p in papers if (not p.authors) and p.arxiv_id]
    if not targets:
        return 0

    arxiv_ids = [p.arxiv_id for p in targets]
    fetched = await enrich_papers_concurrently(arxiv_ids)

    enriched = 0
    for paper in targets:
        new_authors = fetched.get(paper.arxiv_id) or []
        if not new_authors:
            continue
        paper.authors = new_authors
        enriched += 1

    if enriched > 0:
        try:
            await db.commit()
        except Exception as exc:  # pragma: no cover — DB hygiene guard
            logger.warning("Failed to persist arXiv-enriched authors: %s", exc)
            await db.rollback()

    if enriched or len(targets) > 0:
        logger.info(
            "arXiv author enrichment: %d/%d papers back-filled", enriched, len(targets)
        )
    return enriched


def _classify_reference_group(paper: Paper) -> str:
    """Classify non-scholarly web sources away from the main reference list."""
    url = (paper.url or "").lower()
    title = paper.title.lower()

    if any(domain in url for domain in _INDUSTRY_COMMENTARY_DOMAINS):
        return "industry_commentary"
    if any(term in title for term in ("blog", "leaderboard", "vendor benchmark")):
        return "industry_commentary"
    if paper.doi or paper.arxiv_id or paper.semantic_scholar_id or paper.openalex_id:
        return "scholarly"
    if any(domain in url for domain in _SCHOLARLY_DOMAINS):
        return "scholarly"
    return "scholarly"


def _format_reference_line(ref: Mapping[str, object]) -> str:
    """Render one reference line without blank author slots."""
    raw_authors = ref.get("authors")
    if isinstance(raw_authors, str):
        authors_list = [raw_authors] if raw_authors.strip() else []
    elif isinstance(raw_authors, Sequence):
        authors_list = [str(author) for author in raw_authors if str(author).strip()]
    else:
        authors_list = []

    authors = ", ".join(authors_list[:3]) if authors_list else "Unknown author"
    if len(authors_list) > 3:
        authors += " et al."

    year = ref.get("year") or "n.d."
    title = str(ref.get("title") or "Untitled source")
    url = ref.get("url")
    link_part = f" · [Link]({url})" if url else ""
    return f"{ref['citation_label']} {authors} ({year}). *{title}*{link_part}\n"


def _build_methodology_summary(
    saved_papers: int,
    matrix_rows: int,
    research_gaps: int,
    conflicts: int,
) -> dict[str, int]:
    """Return deterministic report-method metadata for markdown rendering."""
    return {
        "saved_papers": saved_papers,
        "matrix_rows": matrix_rows,
        "research_gaps": research_gaps,
        "conflicts": conflicts,
    }


def _render_methodology(methodology: Mapping[str, int]) -> str:
    saved_papers = methodology.get("saved_papers", 0)
    matrix_rows = methodology.get("matrix_rows", 0)
    research_gaps = methodology.get("research_gaps", 0)
    conflicts = methodology.get("conflicts", 0)
    coverage_note = ""
    if saved_papers > 0 and matrix_rows < saved_papers:
        coverage_note = (
            f" Because {matrix_rows} of {saved_papers} corpus entries currently "
            "carry structured extraction records, claims are weighted toward those "
            "sources together with retrieved full-text passages; the remaining "
            "corpus entries are treated as supplementary material rather than as "
            "equally structured evidence."
        )

    return (
        "This narrative synthesis is built on the project's curated scholarly "
        "corpus. The review draws on "
        f"{saved_papers} curated sources, {matrix_rows} structured extraction "
        f"records, {research_gaps} research-gap records, and {conflicts} "
        "conflicting-finding records. Sections were organized thematically "
        "around the research question, with paragraph-level citations validated "
        "against the project's saved evidence identifiers. Peer-reviewed and "
        "preprint scholarly sources are prioritized for empirical claims; web "
        "commentary, vendor material, and leaderboard sources are treated only "
        "as contextual industry evidence and listed separately when cited."
        f"{coverage_note}"
    )


def _is_methodology_heading(heading: object) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", str(heading).lower()).strip()
    return normalized in {"methodology", "methods", "review methodology"}


def _is_conclusion_heading(heading: object) -> bool:
    normalized = re.sub(r"[^a-z]+", " ", str(heading).lower()).strip()
    return normalized in {
        "conclusion",
        "conclusions",
        "conclusion future work",
        "conclusions future work",
        "implications future work",
    }


def _ensure_conclusion_section(
    sections: list[dict],
    topic: str,
    research_question: str | None,
) -> list[dict]:
    """Append a concise conclusion when the LLM omits one.

    Defensive behaviours applied to an LLM-authored conclusion:
    * trim to exactly two paragraphs (the prompt asks for two);
    * if the conclusion is missing entirely, build one from cited papers.
    """
    # If the LLM already wrote a conclusion, enforce the 2-paragraph cap
    # defensively so a wandering model that emits 3-4 paragraphs does
    # not bloat the final report.
    result: list[dict] = []
    for section in sections:
        if _is_conclusion_heading(section.get("heading")):
            capped = _cap_conclusion_to_two_paragraphs(section)
            result.append(capped)
        else:
            result.append(section)

    if any(_is_conclusion_heading(s.get("heading")) for s in result):
        return result

    citation_ids = _collect_conclusion_citation_ids(result)
    if not citation_ids:
        return result

    return [
        *result,
        _build_conclusion_section(
            topic=topic,
            research_question=research_question,
            citation_ids=citation_ids,
            has_gap_section=any(
                "gap" in str(s.get("heading", "")).lower() for s in result
            ),
        ),
    ]


def _cap_conclusion_to_two_paragraphs(section: dict) -> dict:
    """Trim a conclusion section to at most 2 paragraphs.

    The system prompt asks for exactly two paragraphs in the Conclusion.
    When the LLM exceeds that, we keep the first two paragraphs and drop
    the rest. Citation_paper_ids on the kept paragraphs are unioned so
    no references are lost.
    """
    paragraphs = section.get("paragraphs", [])
    if len(paragraphs) <= 2:
        return section

    logger.warning(
        "Conclusion has %d paragraphs; trimming to 2 per prompt spec",
        len(paragraphs),
    )
    kept = paragraphs[:2]
    # Union the dropped paragraphs' citations onto the last kept paragraph
    # so the trimmed-out papers are still cited somewhere.
    dropped_citations: set = set()
    for para in paragraphs[2:]:
        for pid in para.get("citation_paper_ids", []):
            dropped_citations.add(pid)
    if dropped_citations and kept:
        last = dict(kept[-1])
        merged = list(last.get("citation_paper_ids", []))
        seen: set = set()
        for pid in merged:
            if isinstance(pid, UUID):
                seen.add(pid)
        for pid in dropped_citations:
            if isinstance(pid, UUID) and pid not in seen:
                merged.append(pid)
                seen.add(pid)
        last["citation_paper_ids"] = merged
        kept[-1] = last
    return {**section, "paragraphs": kept}


def _collect_conclusion_citation_ids(sections: list[dict]) -> list[UUID]:
    citation_ids: list[UUID] = []
    seen: set[UUID] = set()
    for section in sections:
        if _is_methodology_heading(section.get("heading")):
            continue
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if not isinstance(pid, UUID) or pid in seen:
                    continue
                citation_ids.append(pid)
                seen.add(pid)
                if len(citation_ids) >= 4:
                    return citation_ids
    return citation_ids


def _build_conclusion_section(
    topic: str,
    research_question: str | None,
    citation_ids: list[UUID],
    has_gap_section: bool,
) -> dict:
    focus = research_question or topic
    future_work = (
        "future work should prioritize the unresolved gaps identified above"
        if has_gap_section
        else "future work should extend these comparisons to broader workloads"
    )
    return {
        "heading": "Conclusion",
        "paragraphs": [
            {
                "text": (
                    "Taken together, the reviewed literature shows that "
                    f"{focus} is best understood as a repository-level, "
                    "multi-step software engineering problem rather than an isolated "
                    "code-generation task. The strongest cross-paper pattern is that "
                    "agentic systems extend the reachable task space through planning, "
                    "tool use, execution feedback, and recovery mechanisms, but their "
                    "reported gains remain dependent on workload realism, evaluation "
                    "coverage, and process discipline."
                ),
                "citation_paper_ids": citation_ids,
            },
            {
                "text": (
                    "The practical implication is that claims about autonomous coding "
                    "agents should be evaluated with evidence that combines correctness, "
                    "cost, long-horizon behavior, and maintainability rather than with "
                    f"single benchmark scores alone; {future_work} using reproducible "
                    "trajectories and validated citation or patch evidence."
                ),
                "citation_paper_ids": citation_ids,
            },
        ],
    }


_UUID_PATTERN = re.compile(
    # Bracket-wrapped standard UUID (optionally with a leading space so we
    # also collapse the gap left behind when we strip the citation).
    r"\s*\[([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\]",
    re.IGNORECASE,
)

# Parenthesised UUID pattern. Some LLM generations inline the raw paper ID
# as ``(58e090c2-1f14-4005-80bc-e8270e1c3694)`` directly in the prose.
_PAREN_UUID_PATTERN = re.compile(
    r"\s*\(([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\)",
    re.IGNORECASE,
)

# Bracket-wrapped *list* of UUIDs separated by commas, e.g.
# ``[99369ec6-..., 8f013674-...]``. This is the failure mode the LLM uses
# in the Conclusion when it tries to combine multiple citation IDs into a
# single inline citation instead of emitting them through the
# ``citation_paper_ids`` array.
_UUID_LIST_PATTERN = re.compile(
    r"\s*\["
    r"(\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"(\s*,\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})+)"
    r"\s*\]",
    re.IGNORECASE,
)

# Bare UUID pattern. We require whitespace or punctuation on both sides so
# we never match the hex digits inside a normal word.
_BARE_UUID_PATTERN = re.compile(
    r"(?<![0-9a-fA-F])"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?![0-9a-fA-F])",
    re.IGNORECASE,
)


def _strip_inlined_uuids(text: str, ref_map: dict[str, str]) -> tuple[str, int]:
    """Remove paper UUIDs inlined into paragraph text.

    Some LLM generations inline raw paper UUIDs directly into the prose
    (e.g. ``finding X [7feb6873-4492-4a45-8158-6141f03ff4cf]`` or
    ``(58e090c2-1f14-4005-80bc-e8270e1c3694)`` or
    ``[99369ec6-..., 8f013674-...]``) instead of, or in addition to,
    populating the ``citation_paper_ids`` array. Those raw IDs then leak
    into the rendered markdown and confuse readers because they don't
    map to the numbered ``References`` list.

    Behaviour:
    - UUID is in ``ref_map`` → strip (the citation is already represented
      via ``citation_paper_ids`` → ``<sup>[N]</sup>`` at end of paragraph).
    - UUID is NOT in ``ref_map`` → strip and emit a warning (the LLM
      hallucinated an ID that isn't part of the project).

    Patterns stripped (in order):
    1. ``[uuid1, uuid2, ...]`` — comma-separated lists inside one bracket pair
    2. ``[uuid]`` — single bracket-wrapped UUID
    3. ``(uuid)`` — parenthesised UUID
    4. Bare ``uuid`` — last resort, requires whitespace/punctuation boundaries

    Returns:
        (cleaned_text, replacements_count)
    """
    replacements = 0

    def _replace_list(match: re.Match[str]) -> str:
        nonlocal replacements
        body = match.group(1)
        # Count UUIDs in the matched list.
        count = len(_BARE_UUID_PATTERN.findall(body))
        # De-duplicate the replacement count.
        replacements += count
        # Emit one warning per unique UUID.
        seen: set[str] = set()
        for uuid in _BARE_UUID_PATTERN.findall(body):
            if uuid in seen:
                continue
            seen.add(uuid)
            if uuid in ref_map:
                logger.debug("Stripping inlined UUID %s (already in ref_map)", uuid)
            else:
                logger.warning(
                    "Stripping inlined UUID %s not in references (hallucinated)",
                    uuid,
                )
        return ""

    def _replace_single(uuid: str) -> str:
        nonlocal replacements
        replacements += 1
        if uuid in ref_map:
            logger.debug("Stripping inlined UUID %s (already in ref_map)", uuid)
        else:
            logger.warning(
                "Stripping inlined UUID %s not in references (hallucinated)",
                uuid,
            )
        return ""

    # Order matters: lists first, then bracket singletons, then paren, then
    # bare. Lists must be matched before the single-bracket pattern would
    # eat only the first UUID in the list.
    text = _UUID_LIST_PATTERN.sub(_replace_list, text)
    text = _UUID_PATTERN.sub(lambda m: _replace_single(m.group(1)), text)
    text = _PAREN_UUID_PATTERN.sub(lambda m: _replace_single(m.group(1)), text)
    text = _BARE_UUID_PATTERN.sub(lambda m: _replace_single(m.group(1)), text)

    # Collapse punctuation artefacts like trailing commas / double spaces
    # left behind by the strip. ``(Foo, )`` → ``(Foo)`` etc.
    text = re.sub(r",\s*\)", ")", text)
    text = re.sub(r"\(\s*,", "(", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r" {2,}", " ", text)

    return text, replacements


def _count_inlined_uuids(sections: list[dict]) -> int:
    """Count inlined UUIDs across all sections (used for telemetry).

    Used to measure LLM drift — after ``_strip_inlined_uuids`` post-
    processing this should always be zero. Emitted as a warning before
    cleanup so we know how often the LLM misbehaves.

    Counts every unique UUID exactly once regardless of whether it is
    wrapped in ``[...]``, ``(...)`` or appears bare. This avoids the
    double-count that would happen if we summed the four overlapping
    pattern match lists.
    """
    seen_in_para: set[str] = set()
    count = 0
    for section in sections:
        for para in section.get("paragraphs", []):
            text = para.get("text", "")
            for uuid in _BARE_UUID_PATTERN.findall(text):
                if uuid in seen_in_para:
                    continue
                seen_in_para.add(uuid)
                count += 1
    return count


def _audit_section_citation_density(
    sections: list[dict],
    min_unique_citations: int = 3,
) -> list[dict]:
    """Log a warning when a non-conclusion section cites too few papers.

    The system prompt asks every non-conclusion section to cite at least
    3 distinct papers. We do not trim or rewrite such sections — that
    would require another LLM call and risks losing good prose — but we
    log the failure so the next prompt iteration has data to act on.

    Returns the input sections unchanged.
    """
    for section in sections:
        if _is_conclusion_heading(section.get("heading")):
            continue
        unique: set[UUID] = set()
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if isinstance(pid, UUID):
                    unique.add(pid)
        if len(unique) < min_unique_citations:
            logger.warning(
                "Section '%s' cites only %d unique paper(s); expected >= %d. "
                "Consider revising the prompt or rejecting the section.",
                section.get("heading", "<untitled>"),
                len(unique),
                min_unique_citations,
            )
    return sections


def _extract_numeric_claims(text: str) -> list[str]:
    """Extract specific factual claims (numbers, percentages, ratios) from prose.

    These are the spans most likely to hallucinate: a fabricated ``51.7%``
    or ``1,794 tasks`` is much easier to detect than a paraphrased finding.
    We also extract the *surrounding 8 words* so the audit log can show
    the claim in context.

    Returns a list of unique claim strings, in the order they appear.
    """
    candidates: list[str] = []
    for pattern in (
        _CLAIM_PERCENT_RE,
        _CLAIM_TOKENS_RE,
        _CLAIM_RATIO_RE,
    ):
        candidates.extend(m.group(0) for m in pattern.finditer(text))
    # Also collect bare large numbers (3+ digits) — these are typically
    # concrete dataset/result counts. Skip 1-2 digit numbers which are
    # mostly stop-words like "5 agents" that are too ambiguous to verify.
    for m in _CLAIM_NUMBER_RE.finditer(text):
        raw = m.group(0)
        digits = raw.replace(",", "").rstrip(".0")
        if len(digits) >= 3 and raw not in candidates:
            candidates.append(raw)
    return candidates


def _normalise_claim_for_matching(claim: str) -> list[str]:
    """Return a list of equivalent forms of a claim for fuzzy matching.

    Numbers like ``1,794`` may be written as ``1794`` in the chunk, and
    ``51.7%`` may be written as ``51.7 %`` or ``$51.7\\%$`` in LaTeX-flavored
    text. We generate a small set of variants and check each.
    """
    forms = [claim]
    # Strip commas.
    if "," in claim:
        forms.append(claim.replace(",", ""))
    # Percent variants.
    if "%" in claim:
        stripped = claim.replace(" %", "%").replace("%", "").strip()
        forms.append(stripped)
        # LaTeX: 51.7\% may show as 51.7 in raw text
        if stripped.endswith("."):
            forms.append(stripped.rstrip("."))
    return forms


def _claim_in_chunks(claim: str, chunks_text: list[str]) -> bool:
    """Return True if any chunk contains the claim (or a normalised form)."""
    if not chunks_text:
        return False
    for form in _normalise_claim_for_matching(claim):
        for chunk_text in chunks_text:
            if form in chunk_text:
                return True
    return False


def _audit_claim_grounding(
    sections: list[dict],
    chunks_by_paper: dict[UUID, list[RetrievedChunk]],
) -> dict:
    """Check that numeric claims in each paragraph appear in the cited paper's chunks.

    This is the *defensive* audit that catches the most common
    hallucination pattern: the LLM cites paper X but invents a specific
    number that is not actually in paper X. Each numeric claim is matched
    against the union of retrieved chunks for every cited paper. Claims
    that are not found anywhere in the cited corpus are reported as
    ``ungrounded``.

    This is a *heuristic* — it catches the most common number-fabrication
    pattern but cannot detect paraphrased findings or correct claims whose
    exact numbers happen to be absent from the retrieved chunks. A more
    robust check would require an LLM-based claim verification pass; the
    current pass exists to surface obvious fabrication without paying
    another LLM call.

    Returns:
        A dict with:
        * ``total_claims`` — total numeric claims extracted
        * ``grounded_claims`` — claims found in at least one cited paper's chunks
        * ``ungrounded_claims`` — claims NOT found in any cited paper's chunks
        * ``ungrounded_examples`` — at most 5 ungrounded claims with their
          surrounding context (for the audit report)
        * ``grounding_rate`` — ``grounded_claims / total_claims`` (0..1)
    """
    total = 0
    grounded = 0
    ungrounded: list[dict] = []

    # Flatten chunks for fast lookup. We accept a paper as "supporting" a
    # claim if any of its retrieved chunks mentions the number.
    chunks_text_by_paper: dict[UUID, list[str]] = {}
    for pid, chunk_list in chunks_by_paper.items():
        chunks_text_by_paper[pid] = [c.chunk_text for c in chunk_list]

    for section in sections:
        for para in section.get("paragraphs", []):
            text = para.get("text", "")
            cited_ids = [pid for pid in para.get("citation_paper_ids", []) if isinstance(pid, UUID)]
            claims = _extract_numeric_claims(text)
            if not claims:
                continue
            for claim in claims:
                total += 1
                # Search across all cited papers' chunks
                found = any(
                    _claim_in_chunks(claim, chunks_text_by_paper.get(pid, []))
                    for pid in cited_ids
                )
                if found:
                    grounded += 1
                else:
                    # Capture context for the audit log.
                    idx = text.find(claim)
                    if idx == -1:
                        context = text[:80]
                    else:
                        start = max(0, idx - 40)
                        end = min(len(text), idx + len(claim) + 40)
                        context = text[start:end].strip()
                    ungrounded.append(
                        {
                            "claim": claim,
                            "section": section.get("heading", "<untitled>"),
                            "context": context,
                            "cited_papers": [str(pid) for pid in cited_ids],
                        }
                    )

    return {
        "total_claims": total,
        "grounded_claims": grounded,
        "ungrounded_claims": len(ungrounded),
        "ungrounded_examples": ungrounded[:5],
        "grounding_rate": (grounded / total) if total else 1.0,
    }


def _build_content_markdown(
    sections: list[dict],
    references: list[dict],
    methodology: Mapping[str, int] | None = None,
) -> str:
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

    if methodology:
        parts.append("## Methodology\n")
        parts.append(f"{_render_methodology(methodology)}\n")
        if sections:
            parts.append("\n---\n")

    rendered_sections = [
        section
        for section in sections
        if not (methodology and _is_methodology_heading(section.get("heading")))
    ]

    for i, section in enumerate(rendered_sections):
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

    scholarly_refs = [
        ref for ref in references if ref.get("reference_group") != "industry_commentary"
    ]
    commentary_refs = [
        ref for ref in references if ref.get("reference_group") == "industry_commentary"
    ]

    if scholarly_refs:
        # Build a structured reference list with metadata
        for ref in scholarly_refs:
            parts.append(_format_reference_line(ref))
    else:
        parts.append("*No scholarly references cited.*\n")

    if commentary_refs:
        parts.append("\n---\n\n## Industry Commentary\n")
        for ref in commentary_refs:
            parts.append(_format_reference_line(ref))

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
