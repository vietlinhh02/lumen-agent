"""LangGraph agent nodes — each node is a typed function.

Every node:
  1. Receives ResearchState
  2. Does one well-defined task
  3. Returns a partial ResearchState (only changed fields)
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from app.agents.state import ResearchState
from app.ai.prompts import (
    GAP_ANALYSIS_CHUNK_SYSTEM,
    GAP_ANALYSIS_CHUNK_USER,
    MATRIX_EXTRACTION_CHUNK_SYSTEM,
    MATRIX_EXTRACTION_CHUNK_USER,
    QUERY_PLANNER_SYSTEM,
    QUERY_PLANNER_USER,
    REVIEW_WRITER_CHUNK_SYSTEM,
    REVIEW_WRITER_CHUNK_USER,
)
from app.ai.provider import get_provider
from app.ai.structured_outputs import (
    GapListOutput,
    MatrixRowOutput,
    QueryPlanOutput,
    ReviewOutput,
)
from app.services.gap_detection import upsert_gaps
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence

logger = logging.getLogger(__name__)

_VALID_CONFIDENCE = {"high", "medium", "low"}
_MAX_CHUNK_CONTEXT_CHARS = 8000


# ── Node 0: Query Planner ──────────────────────────────────────────────────


async def query_planner_node(state: ResearchState) -> dict:
    """Analyze the user's topic and produce optimized search query variants."""
    provider = get_provider()
    user_msg = QUERY_PLANNER_USER.format(topic=state.user_topic)

    try:
        raw = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=QUERY_PLANNER_SYSTEM,
            schema=QueryPlanOutput.model_json_schema(),
            tool_name="query_plan",
            max_tokens=2000,
        )
        plan = QueryPlanOutput(**raw)
    except Exception as exc:
        logger.exception("Query planner failed")
        return {
            "current_node": "query_planner",
            "errors": [f"Query planning failed: {exc}"],
        }

    query_variants = [
        {
            "language": "en",
            "query": plan.english_query,
            "sources": plan.suggested_sources,
        },
    ]
    if plan.original_language_query and plan.original_language_query != plan.english_query:
        query_variants.append(
            {
                "language": "original",
                "query": plan.original_language_query,
                "sources": plan.suggested_sources,
            }
        )

    logger.info(
        "Query planned — language=%s, concepts=%d, queries=%d",
        plan.detected_language,
        len(plan.core_concepts),
        len(query_variants),
    )

    return {
        "detected_language": plan.detected_language,
        "core_concepts": plan.core_concepts,
        "query_variants": query_variants,
        "current_node": "query_planner",
    }


# ── Node 1: Search Agent ───────────────────────────────────────────────────


async def search_agent_node(state: ResearchState) -> dict:
    """Search Semantic Scholar for papers matching the query variants."""
    from app.services.paper_search import _classify_pdf_source
    from app.sources.semantic_scholar import SemanticScholarSource

    all_raw: list[dict] = []
    source_diagnostics: dict = {}

    for variant in state.query_variants:
        query = variant["query"]
        sources = variant.get("sources", ["semantic_scholar"])

        for src_name in sources:
            if src_name != "semantic_scholar":
                source_diagnostics[src_name] = {
                    "status": "skipped",
                    "count": 0,
                    "error": "Not implemented yet",
                }
                continue

            try:
                source = SemanticScholarSource(timeout=45)
                papers = await source.search(query=query, limit=50)
                source_diagnostics["semantic_scholar"] = {
                    "status": "ok",
                    "count": len(papers),
                    "query": query,
                }

                for p in papers:
                    all_raw.append(
                        {
                            "title": p.title,
                            "abstract": p.abstract,
                            "year": p.year,
                            "venue": p.venue,
                            "doi": p.doi,
                            "arxiv_id": p.arxiv_id,
                            "semantic_scholar_id": p.semantic_scholar_id,
                            "url": p.url,
                            "citation_count": p.citation_count,
                            "authors": p.authors,
                            "source_name": p.source_name,
                            "pdf_source": _classify_pdf_source(p),
                            "fields_of_study": p.source_specific.get("fields_of_study", []),
                            "is_open_access": p.source_specific.get("is_open_access"),
                            "pdf_url": p.source_specific.get("pdf_url"),
                        }
                    )
            except Exception as exc:
                source_diagnostics["semantic_scholar"] = {
                    "status": "failed",
                    "count": 0,
                    "error": str(exc),
                }

    # Deduplicate by strongest ID
    seen: set[str] = set()
    deduped: list[dict] = []
    for p in all_raw:
        key = p.get("semantic_scholar_id") or p.get("arxiv_id") or p.get("doi") or p["title"][:80]
        if key not in seen:
            seen.add(key)
            deduped.append(p)

    return {
        "raw_papers": deduped,
        "source_diagnostics": source_diagnostics,
        "current_node": "search_agent",
    }


# ── Node 2: Save Screened Papers ───────────────────────────────────────────


async def save_screened_node(state: ResearchState) -> dict:
    """Save papers that passed user screening into the project.

    This node expects the caller to have set ``screened_paper_ids``
    (via the user-screening step in the frontend). It persists the selected
    ``raw_papers`` to the database.

    In a full implementation this would call ``save_paper_to_project`` in a loop.
    For now it's a placeholder that validates the state is correct.
    """
    if not state.screened_paper_ids and state.raw_papers:
        # Auto-screen all papers when the user hasn't selected yet
        # (in production this would be set by the frontend)
        logger.info("No screened papers — auto-screening all %d papers", len(state.raw_papers))
    return {
        "current_node": "save_screened",
    }


# ── Node 3: Matrix Extraction ──────────────────────────────────────────────

_MAX_CHUNKS_PER_PAPER = 5
_MAX_PAPERS = 20


def _build_chunk_context(
    chunks: list[RetrievedChunk], max_chars: int = _MAX_CHUNK_CONTEXT_CHARS
) -> str:
    """Format chunks into prompt-ready section blocks with a total char limit."""
    if not chunks:
        return "No full-text sections available."
    parts: list[str] = []
    total = 0
    for c in chunks:
        label = c.section_label or c.content_type or "section"
        block = f"---{label}---\n{c.chunk_text}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "No full-text sections available."


def _rows_to_json_safe(rows: list[dict]) -> list[dict]:
    """Convert UUID fields to strings so rows are JSON-serializable."""
    return [{k: str(v) if isinstance(v, UUID) else v for k, v in row.items()} for row in rows]


async def matrix_extraction_node(state: ResearchState, db) -> dict:
    """Generate literature matrix rows using metadata + retrieved chunks.

    DB session is used only for data access, not held during LLM calls.
    """
    from sqlalchemy import exists, select
    from sqlalchemy.orm import selectinload

    from app.db.models import LiteratureMatrixRow, ProjectPaper
    from app.services.literature_matrix import upsert_rows

    if not state.project_id:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "failed",
            "errors": ["No project_id in state"],
        }

    # 1. Load saved project_papers, excluding those that already have matrix rows
    stmt = (
        select(ProjectPaper)
        .options(selectinload(ProjectPaper.paper))
        .where(
            ProjectPaper.project_id == state.project_id,
            ProjectPaper.status == "saved",
            ~exists().where(LiteratureMatrixRow.project_paper_id == ProjectPaper.id),
        )
        .limit(_MAX_PAPERS)
    )
    papers_to_process = (await db.execute(stmt)).scalars().all()

    if not papers_to_process:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "completed",
            "matrix_rows": [],
        }

    # 2. Retrieve chunks for the whole project (single query, outside LLM loop)
    query = state.user_topic or ""
    all_chunks = await retrieve_project_evidence(db, state.project_id, query, limit=40)

    # 3. Group chunks by project_paper_id
    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # ── DB session is no longer needed below; LLM calls happen next ──

    # 4. Extract matrix rows via LLM
    provider = get_provider()
    rows: list[dict] = []

    for pp in papers_to_process:
        paper = pp.paper
        paper_chunks = chunks_by_paper.get(pp.id, [])[:_MAX_CHUNKS_PER_PAPER]
        chunk_context = _build_chunk_context(paper_chunks)

        try:
            user_msg = MATRIX_EXTRACTION_CHUNK_USER.format(
                project_topic=state.user_topic,
                title=paper.title,
                authors=", ".join(
                    a.get("name", str(a)) if isinstance(a, dict) else str(a)
                    for a in (paper.authors or [])
                ),
                year=paper.year or "unknown",
                abstract=paper.abstract or "No abstract available",
                venue=paper.venue or "not specified",
                chunk_context=chunk_context,
            )
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                system=MATRIX_EXTRACTION_CHUNK_SYSTEM,
                schema=MatrixRowOutput.model_json_schema(),
                tool_name="matrix_row",
                max_tokens=2000,
            )
            confidence = result.get("confidence", "medium")
            if confidence not in _VALID_CONFIDENCE:
                confidence = "medium"
            rows.append(
                {
                    "project_paper_id": pp.id,
                    "research_problem": result.get("research_problem", "not specified"),
                    "method": result.get("method", "not specified"),
                    "dataset_or_context": result.get("dataset_or_context", "not specified"),
                    "key_result": result.get("key_result", "not specified"),
                    "limitation": result.get("limitation", "not specified"),
                    "contribution": result.get("contribution", "not specified"),
                    "relevance": result.get("relevance", "not specified"),
                    "extraction_confidence": confidence,
                }
            )
        except Exception as exc:
            logger.warning(
                "Matrix extraction failed for paper '%s': %s",
                paper.title[:60],
                exc,
            )

    # 5. Persist to DB
    matrix_status = "completed"
    if rows:
        try:
            saved_count = await upsert_rows(db, state.project_id, rows)
            logger.info("Persisted %d matrix rows for project %s", saved_count, state.project_id)
        except Exception as exc:
            logger.error("Failed to persist matrix rows: %s", exc)
            matrix_status = "failed"
    elif not papers_to_process:
        matrix_status = "completed"
    else:
        matrix_status = "failed"

    return {
        "matrix_rows": _rows_to_json_safe(rows),
        "matrix_status": matrix_status,
        "current_node": "matrix_extraction",
    }


# ── Node 4: Gap Analysis ───────────────────────────────────────────────────

_MAX_GAP_CHUNKS = 30
_MAX_CHUNKS_PER_GAP_PAPER = 5
_MIN_MATRIX_ROWS_FOR_GAPS = 5


async def gap_analysis_node(state: ResearchState, db) -> dict:
    """Detect research gaps from matrix rows + RAG chunks, persist to DB."""
    from sqlalchemy import select

    from app.db.models import LiteratureMatrixRow, ProjectPaper

    if not state.project_id:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": ["No project_id in state"],
        }

    # 1. Load matrix rows from DB
    stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == state.project_id)
    matrix_rows = (await db.execute(stmt)).scalars().all()

    if not matrix_rows:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": ["No matrix rows for gap analysis"],
        }

    if len(matrix_rows) < _MIN_MATRIX_ROWS_FOR_GAPS:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": [
                f"INSUFFICIENT_MATRIX: need >= {_MIN_MATRIX_ROWS_FOR_GAPS}"
                f" matrix rows, got {len(matrix_rows)}"
            ],
        }

    # 2. RAG retrieval for gap-relevant chunks
    query = f"research gaps limitations missing {state.user_topic or ''}"
    all_chunks = await retrieve_project_evidence(db, state.project_id, query, limit=_MAX_GAP_CHUNKS)

    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 3. Load valid project_paper_ids for evidence validation
    pp_stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == state.project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(pp_stmt)).scalars().all())

    # 4. Build prompt
    safe_rows = _rows_to_json_safe(
        [
            {
                "project_paper_id": r.project_paper_id,
                "research_problem": r.research_problem,
                "method": r.method,
                "dataset_or_context": r.dataset_or_context,
                "key_result": r.key_result,
                "limitation": r.limitation,
            }
            for r in matrix_rows
        ]
    )
    paper_ids_json = json.dumps([str(r.project_paper_id) for r in matrix_rows])

    # Build chunk context from all retrieved chunks
    chunk_parts: list[str] = []
    total_chars = 0
    limit_reached = False
    for pp_id, chunks in chunks_by_paper.items():
        if limit_reached:
            break
        for c in chunks[:_MAX_CHUNKS_PER_GAP_PAPER]:
            label = c.section_label or c.content_type or "section"
            block = f"---{label} (paper {str(pp_id)[:8]})---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                limit_reached = True
                break
            chunk_parts.append(block)
            total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    try:
        user_msg = GAP_ANALYSIS_CHUNK_USER.format(
            project_topic=state.user_topic,
            paper_ids_json=paper_ids_json,
            matrix_rows_json=json.dumps(safe_rows, indent=2),
            chunk_context=chunk_context,
        )
        provider = get_provider()
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=GAP_ANALYSIS_CHUNK_SYSTEM,
            schema=GapListOutput.model_json_schema(),
            tool_name="gap_analysis",
            max_tokens=4000,
        )
        raw_gaps = result.get("gaps", [])
    except Exception as exc:
        logger.exception("Gap analysis failed")
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": [f"Gap analysis failed: {exc}"],
        }

    # 5. Validate evidence_paper_ids and filter gaps
    validated_gaps: list[dict] = []
    for gap in raw_gaps:
        raw_ids = gap.get("evidence_paper_ids", [])
        try:
            ev_ids = [UUID(i) if isinstance(i, str) else i for i in raw_ids]
        except (ValueError, TypeError):
            logger.warning("Gap '%s' has invalid evidence IDs, skipping", gap.get("title", ""))
            continue

        valid_ids = [eid for eid in ev_ids if eid in valid_pp_ids]
        if not valid_ids:
            logger.warning(
                "Gap '%s' has no valid evidence after filtering, skipping", gap.get("title", "")
            )
            continue

        validated_gaps.append(
            {
                "title": gap.get("title", "Untitled gap"),
                "description": gap.get("description", ""),
                "suggested_direction": gap.get("suggested_direction", ""),
                "evidence_summary": gap.get("evidence_summary", ""),
                "confidence": gap.get("confidence", "medium"),
                "evidence": [
                    {
                        "project_paper_id": eid,
                        "evidence_type": "limitation",
                        "note": gap.get("evidence_summary", ""),
                    }
                    for eid in valid_ids
                ],
            }
        )

    # 6. Persist to DB
    gap_status = "completed"
    if validated_gaps:
        try:
            saved_count = await upsert_gaps(db, state.project_id, validated_gaps)
            logger.info("Persisted %d gaps for project %s", saved_count, state.project_id)
        except Exception as exc:
            logger.error("Failed to persist gaps: %s", exc)
            gap_status = "failed"

    return {
        "gaps": _rows_to_json_safe(validated_gaps),
        "gap_status": gap_status,
        "current_node": "gap_analysis",
    }


# ── Node 4b: Conflict Detection ────────────────────────────────────────────


async def conflict_detection_node(state: ResearchState, db) -> dict:
    """Detect potential conflicting findings from matrix rows."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    if not state.project_id:
        return {
            "current_node": "conflict_detection",
            "conflict_status": "failed",
            "errors": ["No project_id in state"],
        }

    try:
        conflicts = await detect_and_persist_conflicts(db, state.project_id, state.user_topic or "")
    except Exception as exc:
        logger.exception("Conflict detection failed")
        return {
            "current_node": "conflict_detection",
            "conflict_status": "failed",
            "errors": [f"Conflict detection failed: {exc}"],
        }

    return {
        "conflicts": conflicts,
        "conflict_status": "completed",
        "current_node": "conflict_detection",
    }


# ── Node 5: Review Writer ──────────────────────────────────────────────────

_MAX_REVIEW_CHUNKS = 50
_MAX_CHUNKS_PER_REVIEW_PAPER = 5


async def review_writer_node(state: ResearchState, db) -> dict:
    """Generate a citation-safe literature review with RAG + DB persistence."""
    from app.services.report_generation import (
        _build_content_markdown,
        _build_references,
        _persist_report,
        _validate_citations,
    )

    if not state.project_id:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No project_id in state"],
        }

    # 1. Load matrix rows from DB
    from sqlalchemy import select

    from app.db.models import LiteratureMatrixRow, ProjectPaper

    stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == state.project_id)
    matrix_rows = (await db.execute(stmt)).scalars().all()

    if not matrix_rows:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No matrix rows for review generation"],
        }

    # 2. Load saved project_paper IDs
    pp_stmt = select(ProjectPaper).where(
        ProjectPaper.project_id == state.project_id,
        ProjectPaper.status == "saved",
    )
    project_papers = (await db.execute(pp_stmt)).scalars().all()
    if not project_papers:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No saved papers in project"],
        }
    # 3. Load gaps from state (already validated by gap_analysis_node)
    gaps = state.gaps or []

    # 4. RAG retrieval
    query = state.user_topic or ""
    all_chunks = await retrieve_project_evidence(
        db, state.project_id, query, limit=_MAX_REVIEW_CHUNKS
    )

    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 5. Build chunk context
    chunk_parts: list[str] = []
    total_chars = 0
    for pp_id, chunks in chunks_by_paper.items():
        for c in chunks[:_MAX_CHUNKS_PER_REVIEW_PAPER]:
            label = c.section_label or c.content_type or "section"
            block = f"---{label} (paper {str(pp_id)[:8]})---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                break
            chunk_parts.append(block)
            total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    # 6. Build prompt
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
    safe_gaps = _rows_to_json_safe(gaps)
    paper_ids_json = json.dumps([str(pp.id) for pp in project_papers])

    user_msg = REVIEW_WRITER_CHUNK_USER.format(
        project_topic=state.user_topic,
        research_question=state.research_question or state.user_topic,
        paper_ids_json=paper_ids_json,
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        gaps_json=json.dumps(safe_gaps, indent=2),
        chunk_context=chunk_context,
    )

    try:
        provider = get_provider()
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=REVIEW_WRITER_CHUNK_SYSTEM,
            schema=ReviewOutput.model_json_schema(),
            tool_name="review_report",
            max_tokens=8000,
        )
        sections = result.get("sections", [])
    except Exception as exc:
        logger.exception("Review generation failed")
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": [f"Review generation failed: {exc}"],
        }

    # 7. Validate citations
    cleaned_sections, audit = await _validate_citations(db, state.project_id, sections)

    # 8. Retry if >30% invalid
    if audit["total_citations"] > 0:
        invalid_ratio = audit["invalid_citations"] / audit["total_citations"]
        if invalid_ratio > 0.3:
            logger.info("Retrying review — %.0f%% invalid", invalid_ratio * 100)
            retry_msg = user_msg + (
                f"\n\nWARNING: Previous attempt had "
                f"{audit['invalid_citations']} invalid citations. "
                f"Use ONLY these paper IDs: {paper_ids_json}"
            )
            try:
                result2 = await provider.complete_structured(
                    messages=[{"role": "user", "content": retry_msg}],
                    system=REVIEW_WRITER_CHUNK_SYSTEM,
                    schema=ReviewOutput.model_json_schema(),
                    tool_name="review_report",
                    max_tokens=8000,
                )
                sections2 = result2.get("sections", [])
                cleaned2, audit2 = await _validate_citations(db, state.project_id, sections2)
                if audit2["invalid_citations"] < audit["invalid_citations"]:
                    cleaned_sections, audit = cleaned2, audit2
            except Exception as exc:
                logger.warning("Review retry failed: %s", exc)

    # 9. Build references and markdown
    cited_ids: set[UUID] = set()
    for section in cleaned_sections:
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if isinstance(pid, UUID):
                    cited_ids.add(pid)

    references = await _build_references(db, cited_ids)
    content_markdown = _build_content_markdown(cleaned_sections, references)
    validation_status = "valid" if audit["invalid_citations"] == 0 else "invalid"

    # 10. Persist
    report_title = f"Literature Review: {state.user_topic}"
    try:
        report = await _persist_report(
            db,
            state.project_id,
            state.user_id,
            report_title,
            content_markdown,
            validation_status,
            cleaned_sections,
        )
        logger.info("Persisted report %s (status=%s)", report.id, validation_status)
    except Exception as exc:
        logger.error("Failed to persist report: %s", exc)
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": [f"Failed to persist report: {exc}"],
        }

    return {
        "report_sections": cleaned_sections,
        "report_status": "completed",
        "current_node": "review_writer",
        "citation_validation": audit,
    }


# ── Node 6: Citation Validator ─────────────────────────────────────────────


async def citation_validator_node(state: ResearchState) -> dict:
    """Validate that all cited paper IDs exist in the saved papers."""
    saved_ids = set(state.saved_paper_ids)
    invalid_ids: list[str] = []
    total_cited = 0

    for section in state.report_sections:
        for para in section.get("paragraphs", []):
            for cited in para.get("citation_paper_ids", []):
                total_cited += 1
                try:
                    pid = UUID(cited)
                    if pid not in saved_ids:
                        invalid_ids.append(cited)
                except ValueError:
                    invalid_ids.append(cited)

    valid = len(invalid_ids) == 0

    return {
        "citation_validation": {
            "valid": valid,
            "total_cited": total_cited,
            "invalid_ids": invalid_ids,
            "message": "All citations valid"
            if valid
            else f"{len(invalid_ids)} invalid citation(s) found",
        },
        "current_node": "citation_validator",
        "completed": True,
    }
