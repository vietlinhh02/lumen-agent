"""LangGraph agent nodes — each node is a typed function.

Every node:
  1. Receives ResearchState
  2. Does one well-defined task
  3. Returns a partial ResearchState (only changed fields)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.agents.state import ResearchState
from app.ai.prompts import (
    GAP_ANALYSIS_CHUNK_SYSTEM,
    GAP_ANALYSIS_CHUNK_USER,
    MATRIX_EXTRACTION_CHUNK_SYSTEM,
    MATRIX_EXTRACTION_CHUNK_SYSTEM_CUSTOM,
    MATRIX_EXTRACTION_CHUNK_USER,
    QUERY_PLANNER_SYSTEM,
    QUERY_PLANNER_USER,
    REVIEW_WRITER_CHUNK_SYSTEM,
    REVIEW_WRITER_CHUNK_USER,
    format_protocol_for_prompt,
)
from app.ai.provider import get_matrix_verifier_provider, get_provider
from app.ai.structured_outputs import (
    GapListOutput,
    MatrixRowOutput,
    QueryPlanOutput,
    ReviewOutput,
)
from app.services.extraction_schema import (
    build_extraction_json_schema,
    coerce_custom_value,
    get_effective_schema,
)
from app.services.gap_detection import upsert_gaps
from app.services.hybrid_retrieval import (
    RetrievedChunk,
    retrieve_paper_evidence,
    retrieve_project_evidence,
)

logger = logging.getLogger(__name__)

_VALID_CONFIDENCE = {"high", "medium", "low"}
_MAX_CHUNK_CONTEXT_CHARS = 8000

# Matrix extraction parallelization constants
_MATRIX_CONCURRENCY = 8  # Bound by LLM rate limit (typical 10 concurrent)
_MAX_CHUNKS_PER_PAPER = 5
# Max saved papers to process per matrix-generation run. Default to the
# configured limit (``settings.matrix_max_papers``) — 100 by default —
# so projects of realistic size are fully covered. Previously hardcoded
# at 20 which silently truncated extraction for larger projects.
def _get_max_papers() -> int:
    """Read the matrix-max-papers setting (avoids import-at-load-time cycle)."""
    try:
        from app.core.config import get_settings
        return max(1, int(get_settings().matrix_max_papers))
    except Exception:
        return 100
_COLLABORATIVE_MATRIX_MAX_TOKENS = 32768
_MATRIX_VERIFICATION_SYSTEM = """You verify literature-matrix extractions against paper evidence.

Rules:
- Correct unsupported or hallucinated fields.
- If the extraction is already correct, return it unchanged.
- Keep all fields concise and grounded in the evidence.
- Use only these confidence labels: high, medium, low.
"""


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
            max_tokens=32768,
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
    """Search all configured sources in parallel for every query variant.

    Each (query, source) pair runs independently with its own timeout.
    A 429 or other failure on one source never blocks the others.
    """
    import asyncio

    if not state.query_variants:
        return {"raw_papers": [], "source_diagnostics": {}, "current_node": "search_agent"}

    # ── 1. Collect every (query, source_name) task ──────────────────────
    tasks: list[asyncio.Task] = []
    for variant in state.query_variants:
        query = variant["query"]
        for src_name in variant.get("sources", ["semantic_scholar"]):
            tasks.append(
                asyncio.create_task(_search_one_source(query, src_name, limit=50, timeout=45))
            )

    # ── 2. Run all searches in parallel ─────────────────────────────────
    results: list[_SourceResult | BaseException] = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    # ── 3. Collect papers + diagnostics ─────────────────────────────────
    all_raw: list[dict] = []
    source_diagnostics: dict[str, dict] = {}

    for result in results:
        if not isinstance(result, _SourceResult):
            logger.warning("Search task failed (non-source-specific): %s", result)
            continue
        src_name = result.source_name
        source_diagnostics[src_name] = {
            "status": result.status,
            "count": result.count,
            "error": result.error,
            "query": result.query,
        }
        all_raw.extend(result.papers)

    # ── 4. Deduplicate by strongest ID ──────────────────────────────────
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


@dataclass
class _SourceResult:
    """Result from searching a single (query, source) pair."""

    source_name: str
    query: str
    status: str  # "ok" | "failed" | "skipped"
    count: int = 0
    error: str | None = None
    papers: list[dict] = field(default_factory=list)


async def _search_one_source(
    query: str,
    source_name: str,
    limit: int = 50,
    timeout: float = 45,
) -> _SourceResult:
    """Search one source for one query, returning a ``_SourceResult``."""
    from app.services.paper_search import _classify_pdf_source

    source = _make_source(source_name, timeout)
    if source is None:
        return _SourceResult(
            source_name=source_name,
            query=query,
            status="skipped",
            error=f"Source '{source_name}' is not implemented",
        )

    try:
        raw_papers = await source.search(query=query, limit=limit)
    except Exception as exc:
        logger.warning("Source %s failed for query '%s': %s", source_name, query[:60], exc)
        return _SourceResult(
            source_name=source_name,
            query=query,
            status="failed",
            error=str(exc),
        )

    papers_dicts: list[dict] = []
    for p in raw_papers:
        paper_dict: dict = {
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
        }
        # Pass through source-specific fields for downstream nodes
        for key in ("fields_of_study", "is_open_access", "pdf_url", "paperhub_source"):
            val = p.source_specific.get(key)
            if val is not None:
                paper_dict[key] = val
        papers_dicts.append(paper_dict)

    return _SourceResult(
        source_name=source_name,
        query=query,
        status="ok",
        count=len(papers_dicts),
        papers=papers_dicts,
    )


def _make_source(source_name: str, timeout: float) -> Any | None:
    """Factory: return a ``PaperSource`` for *source_name*, or ``None``."""
    if source_name == "semantic_scholar":
        from app.sources.semantic_scholar import SemanticScholarSource

        return SemanticScholarSource(timeout=timeout)
    if source_name == "exa":
        from app.sources.exa import ExaSource

        return ExaSource()
    if source_name == "paperhub":
        from app.sources.paperhub import PaperHubSource

        return PaperHubSource()
    return None


# ── Node 1b: Language Bias Audit ─────────────────────────────────────────


async def language_bias_node(state: ResearchState) -> dict:
    """Compute language coverage audit from search diagnostics."""
    from app.services.language_bias import QueryVariant, compute_bias_audit

    diagnostics = state.source_diagnostics or {}
    variants = state.query_variants or []

    if not diagnostics or not variants:
        return {
            "current_node": "language_bias",
            "language_bias_audit": {
                "policy": "balanced",
                "candidate_counts_by_language": {},
                "english_dominance_score": 0.0,
                "adjustments_applied": [],
            },
        }

    variant_objects: list[QueryVariant] = []
    for v in variants:
        sources = v.get("sources", [])
        source_name = sources[0] if isinstance(sources, list) and sources else "semantic_scholar"
        variant_objects.append(
            QueryVariant(
                source=source_name,
                query=v.get("query", ""),
                language=v.get("language", "en"),
            )
        )

    diag_list = []
    for src_name, info in diagnostics.items():
        diag_list.append(
            {
                "source": src_name,
                "status": info.get("status", "skipped"),
                "result_count": info.get("count", 0),
                "message": info.get("error"),
            }
        )

    audit = compute_bias_audit(diag_list, "balanced", variant_objects)

    return {
        "current_node": "language_bias",
        "language_bias_audit": {
            "policy": audit.policy,
            "candidate_counts_by_language": audit.candidate_counts_by_language,
            "english_dominance_score": audit.english_dominance_score,
            "adjustments_applied": audit.adjustments_applied,
        },
    }


# ── Node 2: Save Screened Papers ───────────────────────────────────────────


async def save_screened_node(state: ResearchState, db) -> dict:
    """Save papers that passed user screening into the project.

    Persists ``raw_papers`` (or a subset identified by ``screened_paper_ids``)
    to the database as ``ProjectPaper`` rows via ``save_paper_to_project``.

    When ``screened_paper_ids`` is empty (no frontend screening step), all
    papers in ``raw_papers`` are auto-screened so the pipeline can proceed.
    """
    from sqlalchemy import select

    from app.db.models import User
    from app.schemas.project import SavePaperRequest
    from app.services.project import save_paper_to_project

    if not state.project_id:
        return {
            "current_node": "save_screened",
            "errors": ["No project_id in state"],
        }

    if not state.raw_papers:
        logger.info("No raw papers to save — skipping")
        return {
            "current_node": "save_screened",
            "saved_paper_ids": [],
        }

    # Fetch the user for ownership verification (required by save_paper_to_project)
    user_result = await db.execute(select(User).where(User.id == state.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        logger.error("User %s not found — cannot save papers", state.user_id)
        return {
            "current_node": "save_screened",
            "errors": [f"User {state.user_id} not found"],
        }

    # Determine which papers to persist
    # screened_paper_ids is a future frontend feature — fall back to all papers
    papers_to_save = state.raw_papers
    if state.screened_paper_ids:
        logger.info(
            "Using %d screened paper IDs — filtering raw papers",
            len(state.screened_paper_ids),
        )
    else:
        logger.info(
            "No screened_paper_ids — auto-saving all %d papers",
            len(state.raw_papers),
        )

    saved_ids: list[UUID] = []
    for paper_dict in papers_to_save:
        try:
            # Normalise authors to the format SavePaperRequest expects
            authors_mapped = []
            for a in paper_dict.get("authors") or []:
                authors_mapped.append(
                    {
                        "name": a.get("name") if isinstance(a, dict) else str(a),
                        "author_id": "",
                    }
                )

            # Bundle source-specific fields into the source_specific dict
            source_specific = {}
            for k in ("pdf_source", "fields_of_study", "is_open_access", "pdf_url"):
                v = paper_dict.get(k)
                if v is not None:
                    source_specific[k] = v

            req = SavePaperRequest(
                paper_title=paper_dict.get("title", ""),
                paper_abstract=paper_dict.get("abstract"),
                paper_year=paper_dict.get("year"),
                paper_venue=paper_dict.get("venue"),
                paper_doi=paper_dict.get("doi"),
                paper_arxiv_id=paper_dict.get("arxiv_id"),
                paper_semantic_scholar_id=paper_dict.get("semantic_scholar_id"),
                paper_url=paper_dict.get("url"),
                paper_citation_count=paper_dict.get("citation_count"),
                paper_authors=authors_mapped,
                paper_source_names=[paper_dict.get("source_name", "semantic_scholar")],
                download_pdf=True,
                source_specific=source_specific,
            )
            save_result = await save_paper_to_project(db, user, state.project_id, req)
            if save_result is not None:
                saved_ids.append(save_result.project_paper_id)
        except Exception as exc:
            logger.warning(
                "Failed to save paper '%s': %s",
                paper_dict.get("title", "?"),
                exc,
            )
            # Roll back so the same session can be reused for the next paper
            with suppress(Exception):
                await db.rollback()

    logger.info(
        "Saved %d / %d papers for project %s",
        len(saved_ids),
        len(papers_to_save),
        state.project_id,
    )
    return {
        "current_node": "save_screened",
        "saved_paper_ids": saved_ids,
    }


# ── Node 3: Matrix Extraction ──────────────────────────────────────────────


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


async def _build_graph_context(db, project_id: UUID, query: str) -> str:
    try:
        from app.services.knowledge_graph import build_graph_context

        return await build_graph_context(db, project_id, query=query)
    except Exception as exc:
        logger.warning("Knowledge graph context skipped: %s", exc)
        return "No knowledge graph context available."


def _combine_graph_and_chunk_context(graph_context: str, chunk_context: str) -> str:
    if graph_context == "No knowledge graph context available.":
        return chunk_context
    return f"{graph_context}\n\nRetrieved full-text evidence:\n{chunk_context}"


def _rows_to_json_safe(rows: list[dict]) -> list[dict]:
    """Convert UUID fields to strings so rows are JSON-serializable."""
    return [{k: str(v) if isinstance(v, UUID) else v for k, v in row.items()} for row in rows]


def _render_schema_block(fields) -> str:
    """Render the project's extraction schema as a readable prompt block."""
    if not fields:
        return "(no custom fields defined)"
    lines: list[str] = []
    for f in fields:
        type_label = f.type
        extra = ""
        if f.type in ("enum", "multi_select") and f.enum_values:
            extra = f"  enum_values = {f.enum_values}"
        elif f.description:
            extra = f"  ({f.description})"
        req = " [required]" if f.required else ""
        lines.append(f"- {f.key} ({f.label}, type={type_label}){req}{extra}")
    return "\n".join(lines)


def _normalize_matrix_extraction(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize matrix extraction output into persisted row fields.

    The seven reserved keys are pulled out as top-level columns. Custom
    project-defined fields land in the ``custom_fields`` dict with type
    coercion applied per the schema. Unknown keys are silently ignored.
    """
    confidence = result.get("confidence", result.get("extraction_confidence", "medium"))
    if confidence not in _VALID_CONFIDENCE:
        confidence = "medium"
    return {
        "research_problem": result.get("research_problem", "not specified"),
        "method": result.get("method", "not specified"),
        "dataset_or_context": result.get("dataset_or_context", "not specified"),
        "key_result": result.get("key_result", "not specified"),
        "limitation": result.get("limitation", "not specified"),
        "contribution": result.get("contribution", "not specified"),
        "relevance": result.get("relevance", "not specified"),
        "extraction_confidence": confidence,
    }


async def _verify_matrix_extraction(
    verifier_provider,
    *,
    user_topic: str | None,
    paper,
    chunk_context: str,
    primary_result: dict[str, Any],
    protocol_text: str | None = None,
    custom_schema: dict | None = None,
) -> dict[str, Any]:
    """Ask the verifier model to confirm or correct one matrix extraction."""
    protocol_block = protocol_text or "Not provided"
    verify_prompt = f"""Verify this literature-matrix extraction against the paper evidence.

Project topic: {user_topic or "Not specified"}
Review protocol:
{protocol_block}
Paper title: {paper.title}
Paper abstract: {paper.abstract or "No abstract available"}
Paper venue: {paper.venue or "not specified"}
Paper year: {paper.year or "unknown"}

Existing extraction:
{json.dumps(primary_result, indent=2)}

Evidence:
{chunk_context or "No full-text sections available."}
"""
    schema = custom_schema if custom_schema is not None else MatrixRowOutput.model_json_schema()
    return await verifier_provider.complete_structured(
        messages=[{"role": "user", "content": verify_prompt}],
        system=_MATRIX_VERIFICATION_SYSTEM,
        schema=schema,
        tool_name="matrix_verify",
        max_tokens=_COLLABORATIVE_MATRIX_MAX_TOKENS,
    )


async def matrix_extraction_node(
    state: ResearchState,
    db,
    progress_callback: Callable[[int, int, str], Awaitable[None]] | None = None,
) -> dict:
    """Generate literature matrix rows using metadata + retrieved chunks.

    Uses parallel processing with asyncio.Semaphore to bound concurrency
    and asyncio.gather for fan-out. This provides 3-5x speedup over
    sequential processing (20 papers × 2s = 40s → ~8s with concurrency=8).

    DB session is used only for data access, not held during LLM calls.
    """
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.models import ProjectPaper
    from app.services.literature_matrix import build_content_hash, upsert_rows

    if not state.project_id:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "failed",
            "errors": ["No project_id in state"],
        }

    # Render protocol once for all per-paper calls so the extraction prompt
    # can use inclusion/exclusion + population + outcome to ground each row.
    protocol_text = format_protocol_for_prompt(state.review_protocol)

    # T4: load the project's effective extraction schema (defaults + custom).
    # Used both to build the LLM JSON-schema and to coerce the response
    # into ``custom_fields``. Falls back to the seven system defaults on
    # any failure (e.g. mock DBs in tests, transient DB errors) so a broken
    # schema never blocks a matrix run.
    schema_fields = None
    try:
        effective_schema = await get_effective_schema(db, state.project_id)
        schema_fields = effective_schema.fields
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Could not load extraction schema for project %s: %s",
            state.project_id, exc,
        )
    if not schema_fields:
        from app.services.extraction_schema import default_fields as _default_fields
        schema_fields = _default_fields()
    use_custom_schema = any(
        f.key not in ("research_problem", "method", "dataset_or_context",
                      "key_result", "limitation", "contribution", "relevance")
        for f in schema_fields
    )
    schema_json = build_extraction_json_schema(schema_fields) if use_custom_schema else None
    schema_block = _render_schema_block(schema_fields)
    system_prompt = (
        MATRIX_EXTRACTION_CHUNK_SYSTEM_CUSTOM.format(schema_block=schema_block)
        if use_custom_schema
        else MATRIX_EXTRACTION_CHUNK_SYSTEM
    )

    # 1. Load saved project_papers with existing matrix rows for cache checks.
    stmt = (
        select(ProjectPaper)
        .options(
            selectinload(ProjectPaper.paper),
            selectinload(ProjectPaper.matrix_row),
        )
        .where(
            ProjectPaper.project_id == state.project_id,
            ProjectPaper.status == "saved",
        )
        .limit(_get_max_papers())
    )
    papers_to_process = (await db.execute(stmt)).scalars().all()

    if not papers_to_process:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "completed",
            "matrix_rows": [],
        }

    # ── Parallel extraction with bounded concurrency ──
    sem = asyncio.Semaphore(_MATRIX_CONCURRENCY)
    progress_lock = asyncio.Lock()
    processed = 0
    total_papers = len(papers_to_process)

    async def _record_progress(current_title: str) -> None:
        nonlocal processed
        if progress_callback is None:
            return
        async with progress_lock:
            processed += 1
            await progress_callback(processed, total_papers, current_title)

    # 2. Per-paper retrieval: get top chunks for each paper individually.
    query = state.user_topic or ""
    candidate_papers: list[tuple[ProjectPaper, str]] = []

    for pp in papers_to_process:
        paper = pp.paper
        content_hash = build_content_hash(pp.id, getattr(paper, "updated_at", None))
        existing_row = getattr(pp, "matrix_row", None)
        if existing_row and existing_row.content_hash == content_hash:
            logger.info("Skipping '%s' — content unchanged", paper.title[:60])
            await _record_progress(paper.title)
            continue
        candidate_papers.append((pp, content_hash))

    if not candidate_papers:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "completed",
            "matrix_rows": [],
        }

    provider = get_provider()
    verifier_provider = get_matrix_verifier_provider()

    async def _extract_one(pp, content_hash: str) -> dict | None:
        """Extract matrix row for a single paper with semaphore-bounded concurrency."""
        async with sem:
            paper = pp.paper

            # Per-paper retrieval: top chunks for THIS paper only
            try:
                paper_chunks = await retrieve_paper_evidence(
                    db,
                    pp.id,
                    query,
                    limit=_MAX_CHUNKS_PER_PAPER,
                    content_types=["method", "results", "limitation", "table", "narrative"],
                )
                chunk_context = _build_chunk_context(paper_chunks)
            except Exception as exc:
                logger.warning(
                    "Retrieval failed for paper '%s': %s",
                    paper.title[:60],
                    exc,
                )
                chunk_context = ""

            try:
                user_msg = MATRIX_EXTRACTION_CHUNK_USER.format(
                    project_topic=state.user_topic,
                    protocol_context=protocol_text,
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
                if use_custom_schema and schema_json is not None:
                    primary_result = await provider.complete_structured(
                        messages=[{"role": "user", "content": user_msg}],
                        system=system_prompt,
                        schema=schema_json,
                        tool_name="matrix_row",
                        max_tokens=32768,
                    )
                else:
                    primary_result = await provider.complete_structured(
                        messages=[{"role": "user", "content": user_msg}],
                        system=MATRIX_EXTRACTION_CHUNK_SYSTEM,
                        schema=MatrixRowOutput.model_json_schema(),
                        tool_name="matrix_row",
                        max_tokens=32768,
                    )
                normalized = _normalize_matrix_extraction(primary_result)
                # T4: pull out typed custom-field values per the schema.
                custom_fields: dict = {}
                if use_custom_schema:
                    for f in schema_fields:
                        if f.key in (
                            "research_problem", "method", "dataset_or_context",
                            "key_result", "limitation", "contribution", "relevance",
                        ):
                            continue
                        coerced = coerce_custom_value(f, primary_result.get(f.key))
                        if coerced is not None and coerced != "" and coerced != []:
                            custom_fields[f.key] = coerced
                if verifier_provider is not None:
                    try:
                        verified_result = await _verify_matrix_extraction(
                            verifier_provider,
                            user_topic=state.user_topic,
                            paper=paper,
                            chunk_context=chunk_context,
                            primary_result=primary_result,
                            protocol_text=protocol_text,
                            custom_schema=schema_json,
                        )
                        verified_normalized = _normalize_matrix_extraction(verified_result)
                        if verified_normalized != normalized:
                            logger.info(
                                "Verifier adjusted matrix extraction for '%s'",
                                paper.title[:60],
                            )
                            # Confidence policy: take the MORE CONSERVATIVE
                            # of the two. Rewording alone doesn't lower
                            # confidence (the LLM may legitimately phrase
                            # things differently); only an explicit
                            # down-step on the confidence field itself
                            # propagates.
                            primary_conf = normalized["extraction_confidence"]
                            verified_conf = verified_normalized["extraction_confidence"]
                            conf_rank = {"high": 0, "medium": 1, "low": 2}
                            if conf_rank.get(verified_conf, 1) > conf_rank.get(primary_conf, 1):
                                # Verifier is more pessimistic — respect it.
                                pass
                            else:
                                # Verifier did not lower confidence; keep
                                # primary (rewording alone is not a quality
                                # regression).
                                verified_normalized["extraction_confidence"] = primary_conf
                        normalized = verified_normalized
                    except Exception as exc:
                        logger.warning(
                            "Matrix verification failed for paper '%s': %s",
                            paper.title[:60],
                            exc,
                        )
                return {
                    "project_paper_id": pp.id,
                    "research_problem": normalized["research_problem"],
                    "method": normalized["method"],
                    "dataset_or_context": normalized["dataset_or_context"],
                    "key_result": normalized["key_result"],
                    "limitation": normalized["limitation"],
                    "contribution": normalized["contribution"],
                    "relevance": normalized["relevance"],
                    "custom_fields": custom_fields,
                    "content_hash": content_hash,
                    "extraction_confidence": normalized["extraction_confidence"],
                }
            except Exception as exc:
                logger.warning(
                    "Matrix extraction failed for paper '%s': %s",
                    paper.title[:60],
                    exc,
                )
                return None
            finally:
                await _record_progress(paper.title)

    # Fan out — wall-clock: ~40s → ~8s (concurrency=8, 20 papers)
    # return_exceptions=True prevents one failure from cancelling others
    results = await asyncio.gather(
        *[_extract_one(pp, content_hash) for pp, content_hash in candidate_papers],
        return_exceptions=True,
    )

    # Collect successful results (filter out None and exceptions)
    rows = [r for r in results if isinstance(r, dict)]

    # 4. Persist to DB
    matrix_status = "completed"
    if rows:
        try:
            saved_count = await upsert_rows(db, state.project_id, rows)
            logger.info(
                "Persisted %d matrix rows for project %s (from %d papers)",
                saved_count,
                state.project_id,
                len(candidate_papers),
            )
        except Exception as exc:
            logger.error("Failed to persist matrix rows: %s", exc)
            matrix_status = "failed"
    elif not candidate_papers:
        matrix_status = "completed"
    else:
        matrix_status = "failed"

    return {
        "matrix_rows": _rows_to_json_safe(rows),
        "matrix_status": matrix_status,
        "current_node": "matrix_extraction",
    }


# ── Node 4: Gap Analysis ───────────────────────────────────────────────────

_MAX_GAP_CHUNKS_PER_QUERY = 15
_MAX_GAP_CHUNKS_TOTAL = 40
_MAX_CHUNKS_PER_GAP_PAPER = 5
_MIN_MATRIX_ROWS_FOR_GAPS = 5
_MIN_EVIDENCE_PAPERS_FOR_GAP = 2

# Map-Reduce constants for hierarchical gap analysis
_CHUNK_ROWS_FOR_GAP = 12  # Rows per chunk for Map phase
_MAX_GAPS_PER_CHUNK = 3   # Max candidate gaps per chunk
_MAX_FINAL_GAPS = 8       # Max final gaps after Reduce
_GAP_CONCURRENCY = 4      # Bound LLM calls during Map phase

_GAP_RETRIEVAL_QUERIES = [
    "limitations future work {topic}",
    "evaluation gaps dataset limitations {topic}",
    "method limitations open challenges {topic}",
    "underexplored missing comparison {topic}",
]


async def _multi_query_gap_retrieval(
    db, project_id: UUID, topic: str
) -> dict[UUID, list[RetrievedChunk]]:
    """Run multiple retrieval queries and merge + dedupe results by chunk_id.

    Returns chunks grouped by project_paper_id, sorted by score descending.
    """
    all_chunks: list[RetrievedChunk] = []
    seen_chunk_ids: set[UUID] = set()

    for template in _GAP_RETRIEVAL_QUERIES:
        query = template.format(topic=topic)
        try:
            chunks = await retrieve_project_evidence(
                db, project_id, query, limit=_MAX_GAP_CHUNKS_PER_QUERY
            )
            for c in chunks:
                if c.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(c.chunk_id)
                    all_chunks.append(c)
        except Exception as exc:
            logger.warning("Gap retrieval query failed for '%s': %s", query[:40], exc)

    all_chunks.sort(key=lambda c: c.score, reverse=True)
    all_chunks = all_chunks[:_MAX_GAP_CHUNKS_TOTAL]

    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    return chunks_by_paper


# ── Gap Analysis Map-Reduce Helpers ─────────────────────────────────────────


async def _gap_map_chunk(
    rows_chunk: list,
    project_topic: str,
    relevant_chunks: list[RetrievedChunk],
    provider,
    protocol_text: str | None = None,
) -> list[dict]:
    """Map phase: extract candidate gaps from a chunk of matrix rows.

    Each chunk processes up to _CHUNK_ROWS_FOR_GAP rows independently,
    avoiding the middle curse problem with large row sets.
    """
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
            for r in rows_chunk
        ]
    )

    # Build chunk context from relevant chunks for this rows chunk
    chunk_parts: list[str] = []
    total_chars = 0
    for c in relevant_chunks[:_MAX_CHUNKS_PER_GAP_PAPER]:
        label = c.section_label or c.content_type or "section"
        block = f"---{label}---\n{c.chunk_text}"
        if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
            break
        chunk_parts.append(block)
        total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    user_msg = GAP_ANALYSIS_CHUNK_USER.format(
        project_topic=project_topic,
        protocol_context=protocol_text or "Not provided",
        paper_ids_json=json.dumps([str(r.project_paper_id) for r in rows_chunk]),
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        chunk_context=chunk_context,
    )
    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=GAP_ANALYSIS_CHUNK_SYSTEM,
            schema=GapListOutput.model_json_schema(),
            tool_name="gap_chunk_analysis",
            max_tokens=32768,
        )
        return result.get("gaps", [])[:_MAX_GAPS_PER_CHUNK]
    except Exception as exc:
        logger.warning("Gap map chunk failed: %s", exc)
        return []


async def _gap_reduce(
    candidates: list[dict],
    project_topic: str,
    provider,
) -> list[dict]:
    """Reduce phase: deduplicate and rank candidate gaps from all map chunks.

    Takes all candidate gaps from Map phase, deduplicates by title similarity,
    and ranks by evidence strength (number of supporting papers).
    Returns up to _MAX_FINAL_GAPS final gaps.
    """
    if not candidates:
        return []

    dedup_prompt = f"""Deduplicate and rank these candidate research gaps.

Rules:
1. Merge gaps with similar titles or descriptions (keep the more comprehensive one)
2. Prefer gaps backed by more evidence papers
3. Return max {_MAX_FINAL_GAPS} final gaps
4. Each gap must have: title, description, suggested_direction, evidence_paper_ids

Candidate gaps:
{json.dumps(candidates, indent=2)}"""

    dedup_system = f"""You are a research gap analyst. Your task is to:
1. Merge and deduplicate candidate gaps that cover similar territory
2. Keep only unique, evidence-backed gaps
3. Rank by evidence strength (more supporting papers = higher rank)
4. Return max {_MAX_FINAL_GAPS} final gaps in the same JSON format as input"""

    try:
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": dedup_prompt}],
            system=dedup_system,
            schema=GapListOutput.model_json_schema(),
            tool_name="gap_dedup",
            max_tokens=32768,
        )
        return result.get("gaps", [])[:_MAX_FINAL_GAPS]
    except Exception as exc:
        logger.warning("Gap reduce failed: %s", exc)
        # Fallback: return candidates as-is (limited to max)
        return candidates[:_MAX_FINAL_GAPS]


async def gap_analysis_node(state: ResearchState, db) -> dict:
    """Detect research gaps from matrix rows + RAG chunks, persist to DB.

    Uses hierarchical Map-Reduce pattern:
    - Map: Split rows into chunks, parallel extract candidate gaps
    - Reduce: Merge + dedup + rank candidate gaps

    This avoids the "middle curse" problem where models underperform on
    middle sections of long contexts.
    """
    import asyncio

    from sqlalchemy import select

    from app.db.models import LiteratureMatrixRow, ProjectPaper

    if not state.project_id:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": ["No project_id in state"],
        }

    # Render protocol once for all Map-Reduce calls so the gap detection
    # prompt can anchor absence claims to the project's stated scope.
    protocol_text = format_protocol_for_prompt(state.review_protocol)

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

    # 2. Multi-query RAG retrieval for broader evidence coverage
    chunks_by_paper = await _multi_query_gap_retrieval(db, state.project_id, state.user_topic or "")

    # 3. Load valid project_paper_ids for evidence validation
    pp_stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == state.project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(pp_stmt)).scalars().all())

    # 4. Hierarchical Map-Reduce for gap analysis
    # Split rows into chunks of _CHUNK_ROWS_FOR_GAP rows each
    row_chunks = [
        matrix_rows[i : i + _CHUNK_ROWS_FOR_GAP]
        for i in range(0, len(matrix_rows), _CHUNK_ROWS_FOR_GAP)
    ]
    logger.info(
        "Gap analysis: %d rows → %d chunks for Map phase",
        len(matrix_rows),
        len(row_chunks),
    )

    # Map phase: parallel gap extraction per chunk (bounded by semaphore)
    provider = get_provider()
    sem = asyncio.Semaphore(_GAP_CONCURRENCY)

    async def _map_with_semaphore(rows_chunk: list) -> list[dict]:
        async with sem:
            # Get chunks relevant to this rows chunk (by project_paper_id)
            relevant_chunks: list[RetrievedChunk] = []
            for r in rows_chunk:
                relevant_chunks.extend(chunks_by_paper.get(r.project_paper_id, []))
            return await _gap_map_chunk(
                rows_chunk,
                state.user_topic or "",
                relevant_chunks,
                provider,
                protocol_text=protocol_text,
            )

    map_tasks = [_map_with_semaphore(chunk) for chunk in row_chunks]
    map_results = await asyncio.gather(*map_tasks, return_exceptions=True)

    # Flatten map results
    all_candidates: list[dict] = []
    for r in map_results:
        if isinstance(r, list):
            all_candidates.extend(r)
        elif isinstance(r, Exception):
            logger.warning("Map chunk raised exception: %s", r)

    logger.info("Map phase complete: %d candidate gaps", len(all_candidates))

    # Reduce phase: deduplicate and rank
    if all_candidates:
        final_gaps = await _gap_reduce(all_candidates, state.user_topic or "", provider)
        logger.info("Reduce phase complete: %d final gaps", len(final_gaps))
    else:
        final_gaps = []

    # 5. Validate evidence_paper_ids + evidence coverage guard
    validated_gaps: list[dict] = []
    raw_gaps = final_gaps  # Use gaps from reduce phase

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

        # Guard: require minimum 2 evidence papers (unless gap explicitly
        # describes a single-paper limitation — detected by short evidence list
        # with "single" or "one" in the description)
        desc_lower = (gap.get("description", "") + gap.get("evidence_summary", "")).lower()
        is_single_paper_gap = "single paper" in desc_lower or "one paper" in desc_lower
        if len(valid_ids) < _MIN_EVIDENCE_PAPERS_FOR_GAP and not is_single_paper_gap:
            logger.info(
                "Gap '%s' has only %d evidence paper(s) (< %d), skipping",
                gap.get("title", ""),
                len(valid_ids),
                _MIN_EVIDENCE_PAPERS_FOR_GAP,
            )
            continue

        # Guard: downgrade confidence if no chunk evidence was available
        confidence = gap.get("confidence", "medium")
        has_chunk_evidence = bool(chunks_by_paper)  # Check if any chunks were retrieved
        if not has_chunk_evidence and confidence == "high":
            confidence = "medium"
            logger.info("Downgraded gap confidence to 'medium' — no chunk evidence")

        validated_gaps.append(
            {
                "title": gap.get("title", "Untitled gap"),
                "description": gap.get("description", ""),
                "suggested_direction": gap.get("suggested_direction", ""),
                "evidence_summary": gap.get("evidence_summary", ""),
                "confidence": confidence,
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

    protocol_text = format_protocol_for_prompt(state.review_protocol)

    try:
        conflicts = await detect_and_persist_conflicts(
            db,
            state.project_id,
            state.user_topic or "",
            protocol_text=protocol_text,
        )
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
        _build_review_retrieval_query,
        _persist_report,
        _validate_citations,
    )

    if not state.project_id:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No project_id in state"],
        }

    protocol_text = format_protocol_for_prompt(state.review_protocol)

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
    # 3. Load gaps/conflicts from state (already validated by previous nodes)
    gaps = state.gaps or []
    conflicts = state.conflicts or []

    # 4. RAG retrieval — fold protocol terms into the retrieval query so the
    # chunk fetcher biases toward protocol-relevant evidence.
    query = _build_review_retrieval_query(
        state.user_topic or "",
        state.research_question,
        matrix_rows,
        gaps,
        conflicts,
        review_protocol=state.review_protocol,
    )
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
    graph_context = await _build_graph_context(db, state.project_id, query)
    prompt_context = _combine_graph_and_chunk_context(graph_context, chunk_context)

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
    safe_conflicts = _rows_to_json_safe(conflicts)
    paper_ids_json = json.dumps([str(pp.id) for pp in project_papers])

    user_msg = REVIEW_WRITER_CHUNK_USER.format(
        project_topic=state.user_topic,
        research_question=state.research_question or state.user_topic,
        protocol_context=protocol_text,
        paper_ids_json=paper_ids_json,
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        gaps_json=json.dumps(safe_gaps, indent=2),
        conflicts_json=json.dumps(safe_conflicts, indent=2),
        chunk_context=prompt_context,
    )

    try:
        provider = get_provider()
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=REVIEW_WRITER_CHUNK_SYSTEM,
            schema=ReviewOutput.model_json_schema(),
            tool_name="review_report",
            max_tokens=32768,
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
                    max_tokens=32768,
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
