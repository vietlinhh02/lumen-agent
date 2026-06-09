"""LangGraph agent nodes — each node is a typed function.

Every node:
  1. Receives ResearchState
  2. Does one well-defined task
  3. Returns a partial ResearchState (only changed fields)
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from app.agents.state import ResearchState
from app.ai.prompts import (
    FACET_EXTRACTION_SYSTEM,
    FACET_EXTRACTION_USER,
    GAP_ANALYSIS_SYSTEM,
    GAP_ANALYSIS_USER,
    QUERY_PLANNER_SYSTEM,
    QUERY_PLANNER_USER,
    REVIEW_WRITER_SYSTEM,
    REVIEW_WRITER_USER,
)
from app.ai.provider import get_provider
from app.ai.structured_outputs import QueryPlanOutput

logger = logging.getLogger(__name__)


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
        query_variants.append({
            "language": "original",
            "query": plan.original_language_query,
            "sources": plan.suggested_sources,
        })

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
    from app.sources.semantic_scholar import SemanticScholarSource
    from app.services.paper_search import _classify_pdf_source

    all_raw: list[dict] = []
    source_diagnostics: dict = {}

    for variant in state.query_variants:
        query = variant["query"]
        sources = variant.get("sources", ["semantic_scholar"])

        for src_name in sources:
            if src_name != "semantic_scholar":
                source_diagnostics[src_name] = {"status": "skipped", "count": 0, "error": "Not implemented yet"}
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
                    all_raw.append({
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
                    })
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


async def matrix_extraction_node(state: ResearchState) -> dict:
    """Generate literature matrix rows for saved papers using DeepSeek V4."""
    if not state.raw_papers:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "failed",
            "errors": ["No papers to extract matrix from"],
        }

    provider = get_provider()
    rows: list[dict] = []

    for i, paper in enumerate(state.raw_papers[:20]):  # limit batch size
        try:
            user_msg = FACET_EXTRACTION_USER.format(
                title=paper["title"],
                abstract=paper.get("abstract") or "No abstract available",
                project_topic=state.user_topic,
            )
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                system=FACET_EXTRACTION_SYSTEM,
                schema={
                    "type": "object",
                    "properties": {
                        "research_problem": {"type": "string"},
                        "method": {"type": "string"},
                        "dataset_or_context": {"type": "string"},
                        "key_result": {"type": "string"},
                        "limitation": {"type": "string"},
                        "contribution": {"type": "string"},
                        "relevance": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["research_problem", "method", "key_result", "confidence"],
                },
                tool_name="matrix_row",
                max_tokens=2000,
            )
            rows.append({
                "paper_index": i,
                "paper_title": paper["title"],
                "research_problem": result.get("research_problem", "not specified"),
                "method": result.get("method", "not specified"),
                "dataset_or_context": result.get("dataset_or_context", "not specified"),
                "key_result": result.get("key_result", "not specified"),
                "limitation": result.get("limitation", "not specified"),
                "contribution": result.get("contribution", "not specified"),
                "relevance": result.get("relevance", "not specified"),
                "confidence": result.get("confidence", "medium"),
            })
        except Exception as exc:
            logger.warning("Matrix extraction failed for paper '%s': %s", paper["title"][:60], exc)

    return {
        "matrix_rows": rows,
        "matrix_status": "completed" if rows else "failed",
        "current_node": "matrix_extraction",
    }


# ── Node 4: Gap Analysis ───────────────────────────────────────────────────


async def gap_analysis_node(state: ResearchState) -> dict:
    """Detect research gaps from matrix rows using DeepSeek V4."""
    if not state.matrix_rows:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": ["No matrix rows for gap analysis"],
        }

    provider = get_provider()
    import json
    try:
        user_msg = GAP_ANALYSIS_USER.format(
            project_topic=state.user_topic,
            paper_ids_json=json.dumps([str(i) for i in range(len(state.matrix_rows))]),
            matrix_rows_json=json.dumps(state.matrix_rows[:15], indent=2),
        )
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=GAP_ANALYSIS_SYSTEM,
            schema={
                "type": "object",
                "properties": {
                    "gaps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "evidence_paper_ids": {"type": "array", "items": {"type": "string"}},
                                "evidence_summary": {"type": "string"},
                                "suggested_direction": {"type": "string"},
                                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                            },
                            "required": ["title", "description", "evidence_paper_ids", "suggested_direction"],
                        },
                    },
                },
                "required": ["gaps"],
            },
            tool_name="gap_analysis",
            max_tokens=4000,
        )
        gaps = result.get("gaps", [])
    except Exception as exc:
        logger.exception("Gap analysis failed")
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": [f"Gap analysis failed: {exc}"],
        }

    return {
        "gaps": gaps,
        "gap_status": "completed" if gaps else "failed",
        "current_node": "gap_analysis",
    }


# ── Node 5: Review Writer ──────────────────────────────────────────────────


async def review_writer_node(state: ResearchState) -> dict:
    """Generate a citation-safe literature review draft."""
    if not state.matrix_rows:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No evidence to write review from"],
        }

    provider = get_provider()
    import json
    try:
        user_msg = REVIEW_WRITER_USER.format(
            project_topic=state.user_topic,
            research_question=state.research_question or state.user_topic,
            evidence_json=json.dumps(state.matrix_rows[:15], indent=2),
            gaps_json=json.dumps(state.gaps, indent=2),
        )
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=REVIEW_WRITER_SYSTEM,
            schema={
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "paragraphs": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "text": {"type": "string"},
                                            "citation_paper_ids": {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        },
                                        "required": ["text", "citation_paper_ids"],
                                    },
                                },
                            },
                            "required": ["heading", "paragraphs"],
                        },
                    },
                },
                "required": ["sections"],
            },
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

    return {
        "report_sections": sections,
        "report_status": "completed" if sections else "failed",
        "current_node": "review_writer",
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
            "message": "All citations valid" if valid else f"{len(invalid_ids)} invalid citation(s) found",
        },
        "current_node": "citation_validator",
        "completed": True,
    }
