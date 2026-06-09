"""Citation-aware hybrid retrieval over saved project paper chunks."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import encode_text
from app.db.models import Paper, PaperChunk, ProjectPaper

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
) -> list[RetrievedChunk]:
    """Retrieve citation-ready evidence chunks for a project query."""
    query_tokens = _tokens(query)
    query_embedding = encode_text(query) if query.strip() else []

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
        vector_score = _vector_score(query_embedding, chunk.embedding)
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


def _vector_score(query_embedding: list[float], embedding_json: str | None) -> float:
    """Score semantic similarity using stored JSON embeddings."""
    if not query_embedding or not embedding_json:
        return 0.0
    try:
        embedding = json.loads(embedding_json)
    except json.JSONDecodeError:
        return 0.0
    if not isinstance(embedding, list):
        return 0.0
    return _cosine(query_embedding, embedding)


def _combined_score(keyword_score: float, vector_score: float, content_type: str | None) -> float:
    """Blend keyword, vector, and section/content priors."""
    boost = _SECTION_BOOSTS.get(content_type or "", 0.0)
    return keyword_score * 0.45 + vector_score * 0.55 + boost


def _cosine(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for two embedding vectors."""
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _tokens(text: str) -> set[str]:
    """Tokenize text for lightweight BM25-like filtering."""
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}
