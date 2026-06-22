"""REST endpoints for paper search + download.

``POST /api/papers/search``          — search Semantic Scholar, optionally download PDFs
``POST /api/papers/suggest-queries`` — AI-generated search query suggestions
``POST /api/papers/screen``           — AI relevance screening for search results
``GET  /api/papers/pdf-status``       (future) — query PDF status for a set of papers
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status

from app.ai.prompts import (
    PAPER_SCREEN_SYSTEM,
    PAPER_SCREEN_USER,
    SEARCH_SUGGEST_SYSTEM,
    SEARCH_SUGGEST_USER,
    format_protocol_for_prompt,
)
from app.ai.provider import get_provider
from app.schemas.paper import (
    PaperSearchRequest,
    PaperSearchResponse,
    ScreenPapersRequest,
    ScreenPapersResponse,
    SuggestQueriesRequest,
    SuggestQueriesResponse,
)
from app.services.paper_search import search_and_download

logger = logging.getLogger(__name__)

router = APIRouter(tags=["papers"])


@router.post("/search", response_model=PaperSearchResponse)
async def search_papers(request: PaperSearchRequest) -> PaperSearchResponse:
    """Search for academic papers and optionally download their PDFs.

    Powered by Semantic Scholar.  PDFs are downloaded from arXiv CDN
    (when an arXiv ID is available) or from Semantic Scholar's open-access
    links.
    """
    try:
        outcome = await search_and_download(request)
        return outcome.response
    except Exception as exc:
        logger.exception("Paper search failed for query '%s'", request.query)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Search failed: {exc}",
        ) from exc


@router.post("/suggest-queries", response_model=SuggestQueriesResponse)
async def suggest_queries(request: SuggestQueriesRequest) -> SuggestQueriesResponse:
    """Generate optimized academic search queries from a research topic.

    Uses the configured LLM to produce 4–6 specific, varied search queries
    that cover different angles (methods, applications, comparisons, trends).

    When ``review_protocol`` is supplied (or a ``project_id`` is provided),
    the inclusion/exclusion criteria and population/comparison/outcome anchors
    bias query formulation — we avoid queries that primarily target excluded
    populations and prioritize anchor terms from inclusion criteria.
    """
    provider = get_provider()
    protocol_text = format_protocol_for_prompt(request.review_protocol)
    user_msg = SEARCH_SUGGEST_USER.format(
        title=request.title,
        topic=request.topic,
        research_question=request.research_question or request.topic,
        protocol_context=protocol_text,
    )

    try:
        raw = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=SEARCH_SUGGEST_SYSTEM,
            schema={
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 4,
                        "maxItems": 6,
                    },
                },
                "required": ["queries"],
            },
            tool_name="suggest_queries",
            max_tokens=1000,
        )
        return SuggestQueriesResponse(queries=raw.get("queries", []))
    except Exception as exc:
        logger.exception("Query suggestion failed for topic '%s'", request.topic)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Query suggestion failed: {exc}",
        ) from exc


@router.post("/screen", response_model=ScreenPapersResponse)
async def screen_papers(request: ScreenPapersRequest) -> ScreenPapersResponse:
    """Screen paper search results for relevance to a research topic.

    Uses the configured LLM to score each paper as "high", "medium",
    or "low" relevance based on title and abstract match with the topic
    (and the optional review protocol).

    Uses raw completion instead of structured output to avoid
    tool_choice incompatibility with DeepSeek thinking mode.
    """
    provider = get_provider()

    paper_list = "\n\n".join(
        f"[{i}] {p.title}\nAbstract: {p.abstract or 'N/A'}" for i, p in enumerate(request.papers)
    )

    protocol_text = format_protocol_for_prompt(request.review_protocol)
    user_msg = PAPER_SCREEN_USER.format(
        topic=request.topic,
        research_question=request.research_question or "Not specified",
        review_protocol=protocol_text,
        paper_list=paper_list,
    )

    try:
        raw_text = await provider.complete(
            messages=[{"role": "user", "content": user_msg}],
            system=PAPER_SCREEN_SYSTEM,
            max_tokens=500,
        )
        scores = _parse_screening_scores(raw_text, len(request.papers))
        return ScreenPapersResponse(scores=scores)
    except Exception as exc:
        logger.exception("Paper screening failed for topic '%s'", request.topic)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"Paper screening failed: {exc}",
        ) from exc


def _parse_screening_scores(raw: str, expected_count: int) -> list[str]:
    """Parse screening scores from raw LLM text output."""
    import re

    raw = raw.strip().lower()

    # Try JSON array first
    import json

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            scores = [s.lower() for s in parsed]
            valid = {"high", "medium", "low"}
            scores = [s if s in valid else "medium" for s in scores]
            if len(scores) >= expected_count:
                return scores[:expected_count]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try comma-separated
    items = [s.strip() for s in re.split(r"[,\n]+", raw) if s.strip()]
    valid = {"high", "medium", "low"}
    scores = []
    for item in items:
        for v in valid:
            if v in item:
                scores.append(v)
                break
        else:
            scores.append("medium")

    while len(scores) < expected_count:
        scores.append("medium")
    return scores[:expected_count]
