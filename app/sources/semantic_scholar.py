"""Semantic Scholar paper source adapter.

Uses the public Academic Graph REST API (no key required).
Rate limit: 100 requests per 5-minute window without an API key.

The /paper/search/bulk endpoint returns relevance-unordered results but is
less aggressively rate-limited than /paper/search.  It uses continuation
tokens instead of offset-based pagination.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.sources.base import PaperSource, RawPaper

logger = logging.getLogger(__name__)

_BASE = "https://api.semanticscholar.org/graph/v1"
_SEARCH_FIELDS = (
    "title,abstract,year,venue,publicationDate,"
    "externalIds,url,citationCount,authors,openAccessPdf,"
    "fieldsOfStudy,journal"
)
_BATCH_SIZE = 100  # API max per page

_HEADERS = {"User-Agent": "LitReviewBot/0.1 (academic research tool)"}


def _build_headers(api_key: str | None = None) -> dict[str, str]:
    """Return request headers, optionally including the S2 API key."""
    headers = dict(_HEADERS)
    if api_key:
        headers["x-api-key"] = api_key
    return headers


class SemanticScholarSource(PaperSource):
    """Search academic papers via the Semantic Scholar bulk endpoint."""

    name = "semantic_scholar"

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        """Fetch up to *limit* papers via the /paper/search/bulk endpoint.

        Uses continuation-token pagination to collect results across
        multiple pages.
        """
        papers: list[RawPaper] = []
        collected = 0
        token: str | None = None
        first = True

        while collected < limit:
            batch_size = min(_BATCH_SIZE, limit - collected)
            batch, token = await self._fetch_page(
                query, token, batch_size, first, year_from, year_to
            )
            first = False
            papers.extend(batch)
            collected += len(batch)
            if not token or len(batch) < batch_size:
                break

        return papers[:limit]

    # ── helpers ──────────────────────────────────────────────────────────────────

    async def _fetch_page(
        self,
        query: str,
        token: str | None,
        limit: int,
        first_page: bool,
        year_from: int | None,
        year_to: int | None,
    ) -> tuple[list[RawPaper], str | None]:
        params: dict = {
            "query": query,
            "limit": str(limit),
            "fields": _SEARCH_FIELDS,
        }
        if not first_page and token:
            params["token"] = token
        if year_from is not None or year_to is not None:
            yf = year_from or ""
            yt = year_to or ""
            params["year"] = f"{yf}-{yt}"

        url = f"{_BASE}/paper/search/bulk"

        async with httpx.AsyncClient(timeout=self._timeout, headers=_build_headers(self._api_key)) as client:
            for attempt in range(3):
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    body = resp.json()
                    hits = [self._parse_hit(h) for h in body.get("data", [])]
                    next_token = body.get("token")
                    return hits, next_token
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        wait = 2 ** attempt
                        logger.warning("Semantic Scholar 429 – retrying in %ss", wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.error("Semantic Scholar HTTP %s: %s", exc.response.status_code, exc)
                    return [], None
                except httpx.RequestError as exc:
                    logger.error("Semantic Scholar request error: %s", exc)
                    return [], None

        return [], None

    @staticmethod
    def _parse_hit(hit: dict) -> RawPaper:
        external = hit.get("externalIds") or {}
        authors = [
            {"name": a["name"], "author_id": a.get("authorId", "")}
            for a in (hit.get("authors") or [])
        ]
        venue_raw = hit.get("venue") or ""
        venue = venue_raw.strip() or None

        return RawPaper(
            title=(hit.get("title") or "").strip(),
            abstract=hit.get("abstract"),
            year=hit.get("year"),
            venue=venue,
            doi=external.get("DOI"),
            arxiv_id=external.get("ArXiv"),
            semantic_scholar_id=hit.get("paperId"),
            openalex_id=None,  # Semantic Scholar doesn't return OpenAlex IDs directly
            url=hit.get("url"),
            citation_count=hit.get("citationCount"),
            authors=authors,
            source_name="semantic_scholar",
            source_specific={
                "corpus_id": hit.get("corpusId"),
                "fields_of_study": hit.get("fieldsOfStudy", []),
                "is_open_access": hit.get("isOpenAccess"),
                "pdf_url": (hit.get("openAccessPdf") or {}).get("url") or None,
            },
        )
