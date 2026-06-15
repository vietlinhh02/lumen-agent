"""Citation-aware hybrid retrieval over saved project paper chunks.

Uses pgvector DB-side cosine distance for vector search instead of loading
all chunks into Python. Pipeline: DB vector search → keyword scoring →
blend → rerank → top-K.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import encode_text
from app.db.models import Paper, PaperChunk, ProjectPaper

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_SECTION_BOOSTS = {
    "abstract": 0.08,
    "method": 0.08,
    "results": 0.12,
    "limitation": 0.16,
    "table": 0.1,
    "figure_caption": 0.08,
}


@dataclass(frozen=True)
class RetrievedChunk:
    """Evidence chunk returned by hybrid retrieval."""

    project_paper_id: UUID
    paper_id: UUID
    chunk_id: UUID
    title: str
    chunk_text: str
    section_label: str | None
    section_path: str | None
    chunk_index: int | None
    content_type: str | None
    page_start: int | None
    page_end: int | None
    content_hash: str | None
    score: float
    keyword_score: float
    vector_score: float


async def retrieve_project_evidence(
    db: AsyncSession,
    project_id: UUID,
    query: str,
    limit: int = 8,
    content_types: list[str] | None = None,
    use_reranker: bool = True,
) -> list[RetrievedChunk]:
    """Retrieve citation-ready evidence chunks for a project query.

    Pipeline: DB-side vector search (pgvector HNSW) → keyword scoring →
    blend → rerank → top-K.

    When ``use_reranker`` is True (default), retrieves ``reranker_top_n``
    candidates first, reranks with the cross-encoder, then returns top-K.
    """
    from app.core.config import get_settings

    settings = get_settings()

    if not query.strip():
        return []

    retrieval_query = await _expand_query_with_graph(db, project_id, query)
    query_tokens = _tokens(retrieval_query)

    query_embedding = await encode_text(retrieval_query)
    if not query_embedding or all(v == 0.0 for v in query_embedding):
        logger.warning("Query produced zero embedding, falling back to keyword-only")
        return await _keyword_only_fallback(db, project_id, query_tokens, limit, content_types)

    # Retrieve more candidates when reranking
    candidate_limit = settings.reranker_top_n if use_reranker else limit
    # Fetch extra for keyword scoring headroom
    fetch_limit = min(candidate_limit * 3, 200)

    # DB-side vector search using pgvector cosine distance
    # cosine_distance = 1 - cosine_similarity, so lower = more similar
    cosine_dist = PaperChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(ProjectPaper, Paper, PaperChunk, cosine_dist.label("vector_dist"))
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .join(PaperChunk, PaperChunk.project_paper_id == ProjectPaper.id)
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
            PaperChunk.chunk_type == "full_text",
            PaperChunk.embedding.isnot(None),
        )
        .order_by(cosine_dist)
        .limit(fetch_limit)
    )
    if content_types:
        stmt = stmt.where(PaperChunk.content_type.in_(content_types))

    rows = (await db.execute(stmt)).all()

    ranked: list[RetrievedChunk] = []
    for project_paper, paper, chunk, vector_dist in rows:
        # Convert distance to similarity score (0-1 range)
        vector_score = max(0.0, 1.0 - vector_dist)
        keyword_score = _keyword_score(query_tokens, paper, chunk)
        score = _combined_score(keyword_score, vector_score, chunk.content_type)
        if score <= 0:
            continue
        ranked.append(
            RetrievedChunk(
                project_paper_id=project_paper.id,
                paper_id=paper.id,
                chunk_id=chunk.id,
                title=paper.title,
                chunk_text=chunk.chunk_text,
                section_label=chunk.section_label,
                section_path=chunk.section_path,
                chunk_index=chunk.chunk_index,
                content_type=chunk.content_type,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content_hash=chunk.content_hash,
                score=score,
                keyword_score=keyword_score,
                vector_score=vector_score,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    candidates = ranked[:candidate_limit]

    # Always rerank when enabled — reranker is the final quality gate
    if use_reranker and candidates:
        try:
            from app.services.reranker import rerank

            docs = [c.chunk_text for c in candidates]
            reranked = await rerank(retrieval_query, docs, top_k=limit)
            # Filter by score threshold to exclude irrelevant chunks
            min_score = 0.05
            candidates = [
                replace(candidates[idx], score=float(reranker_score))
                for idx, reranker_score in reranked
                if reranker_score >= min_score
            ]
        except Exception as exc:
            logger.warning("Reranker failed, falling back to hybrid scores: %s", exc)
            candidates = candidates[:limit]
    else:
        candidates = candidates[:limit]

    return candidates


async def _expand_query_with_graph(db: AsyncSession, project_id: UUID, query: str) -> str:
    """Use the project's knowledge graph concepts to improve evidence retrieval."""
    try:
        from app.services.knowledge_graph import expand_query_with_graph_context

        return await expand_query_with_graph_context(db, project_id, query)
    except Exception as exc:
        logger.warning("Knowledge graph query expansion skipped: %s", exc)
        return query


async def retrieve_paper_evidence(
    db: AsyncSession,
    project_paper_id: UUID,
    query: str,
    limit: int = 8,
    content_types: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Retrieve top chunks for a single paper, used by matrix extraction.

    Uses DB-side vector search scoped to one project_paper_id.
    """
    query_tokens = _tokens(query)

    if not query.strip():
        return []

    query_embedding = await encode_text(query)
    if not query_embedding or all(v == 0.0 for v in query_embedding):
        return []

    cosine_dist = PaperChunk.embedding.cosine_distance(query_embedding)

    stmt = (
        select(ProjectPaper, Paper, PaperChunk, cosine_dist.label("vector_dist"))
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .join(PaperChunk, PaperChunk.project_paper_id == ProjectPaper.id)
        .where(
            ProjectPaper.id == project_paper_id,
            PaperChunk.chunk_type == "full_text",
            PaperChunk.embedding.isnot(None),
        )
        .order_by(cosine_dist)
        .limit(limit * 2)
    )
    if content_types:
        stmt = stmt.where(PaperChunk.content_type.in_(content_types))

    rows = (await db.execute(stmt)).all()

    ranked: list[RetrievedChunk] = []
    for project_paper, paper, chunk, vector_dist in rows:
        vector_score = max(0.0, 1.0 - vector_dist)
        keyword_score = _keyword_score(query_tokens, paper, chunk)
        score = _combined_score(keyword_score, vector_score, chunk.content_type)
        if score <= 0:
            continue
        ranked.append(
            RetrievedChunk(
                project_paper_id=project_paper.id,
                paper_id=paper.id,
                chunk_id=chunk.id,
                title=paper.title,
                chunk_text=chunk.chunk_text,
                section_label=chunk.section_label,
                section_path=chunk.section_path,
                chunk_index=chunk.chunk_index,
                content_type=chunk.content_type,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content_hash=chunk.content_hash,
                score=score,
                keyword_score=keyword_score,
                vector_score=vector_score,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]


async def _keyword_only_fallback(
    db: AsyncSession,
    project_id: UUID,
    query_tokens: set[str],
    limit: int,
    content_types: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Fallback when embedding is unavailable — keyword scoring only."""
    stmt = (
        select(ProjectPaper, Paper, PaperChunk)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .join(PaperChunk, PaperChunk.project_paper_id == ProjectPaper.id)
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.status == "saved",
            PaperChunk.chunk_type == "full_text",
        )
    )
    if content_types:
        stmt = stmt.where(PaperChunk.content_type.in_(content_types))

    rows = (await db.execute(stmt)).all()
    ranked: list[RetrievedChunk] = []
    for project_paper, paper, chunk in rows:
        keyword_score = _keyword_score(query_tokens, paper, chunk)
        score = _combined_score(keyword_score, 0.0, chunk.content_type)
        if score <= 0:
            continue
        ranked.append(
            RetrievedChunk(
                project_paper_id=project_paper.id,
                paper_id=paper.id,
                chunk_id=chunk.id,
                title=paper.title,
                chunk_text=chunk.chunk_text,
                section_label=chunk.section_label,
                section_path=chunk.section_path,
                chunk_index=chunk.chunk_index,
                content_type=chunk.content_type,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                content_hash=chunk.content_hash,
                score=score,
                keyword_score=keyword_score,
                vector_score=0.0,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]


def _keyword_score(query_tokens: set[str], paper: Paper, chunk: PaperChunk) -> float:
    """Score exact keyword overlap across metadata and evidence text."""
    if not query_tokens:
        return 0.0
    fields = [
        paper.title,
        paper.abstract or "",
        chunk.section_label or "",
        chunk.content_type or "",
        chunk.chunk_text,
    ]
    text_tokens = _tokens(" ".join(fields))
    if not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / math.sqrt(len(query_tokens) * len(text_tokens))


def _combined_score(keyword_score: float, vector_score: float, content_type: str | None) -> float:
    """Blend keyword, vector, and section/content priors."""
    boost = _SECTION_BOOSTS.get(content_type or "", 0.0)
    return keyword_score * 0.45 + vector_score * 0.55 + boost


def _tokens(text: str) -> set[str]:
    """Tokenize text for lightweight BM25-like filtering."""
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}
