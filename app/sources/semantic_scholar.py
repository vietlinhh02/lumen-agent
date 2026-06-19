"""Semantic Scholar paper source adapter.

Uses the public Academic Graph REST API (no key required).
Rate limit: 100 requests per 5-minute window without an API key.

The /paper/search/bulk endpoint returns relevance-unordered results but is
less aggressively rate-limited than /paper/search.  It uses continuation
tokens instead of offset-based pagination.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time

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

# Rate limiting: allow max 1 concurrent request, with 1s cooldown between requests
_rate_limit_semaphore: asyncio.Semaphore | None = None
_rate_limit_cooldown: float = 1.0
_last_request_time: float = 0.0


def _get_semaphore() -> asyncio.Semaphore:
    global _rate_limit_semaphore
    if _rate_limit_semaphore is None:
        _rate_limit_semaphore = asyncio.Semaphore(1)
    return _rate_limit_semaphore


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
        self._cache: dict[str, tuple[list[RawPaper], float]] = {}
        self._cache_ttl = 300.0  # 5 min cache

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        """Fetch up to *limit* papers via the /paper/search/bulk endpoint.

        Uses continuation-token pagination to collect results across
        multiple pages. Results are cached for 5 minutes to avoid
        redundant API calls during ReAct loop iterations.
        """
        # Check cache first
        cache_key = self._make_cache_key(query, limit, year_from, year_to)
        now = time.monotonic()
        if cache_key in self._cache:
            cached_papers, cached_at = self._cache[cache_key]
            if now - cached_at < self._cache_ttl:
                logger.debug("Semantic Scholar cache hit for query: %s", query[:50])
                return cached_papers[:limit]

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

        result = papers[:limit]
        # Cache the result
        self._cache[cache_key] = (result, now)
        return result

    def _make_cache_key(
        self,
        query: str,
        limit: int,
        year_from: int | None,
        year_to: int | None,
    ) -> str:
        """Create a cache key for this search query."""
        key_parts = f"{query}:{limit}:{year_from}:{year_to}"
        return hashlib.md5(key_parts.encode()).hexdigest()

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

        # Use rate limiting semaphore to prevent 429 from concurrent requests
        semaphore = _get_semaphore()

        async with semaphore:
            # Enforce cooldown between requests
            global _last_request_time
            now = time.monotonic()
            wait_time = _rate_limit_cooldown - (now - _last_request_time)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            _last_request_time = time.monotonic()

            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers=_build_headers(self._api_key),
            ) as client:
                for attempt in range(6):
                    try:
                        resp = await client.get(url, params=params)
                        resp.raise_for_status()
                        body = resp.json()
                        hits = [self._parse_hit(h) for h in body.get("data", [])]
                        next_token = body.get("token")
                        return hits, next_token
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            import random
                            wait = (2 ** (attempt + 1)) + random.uniform(0.1, 1.0)
                            logger.warning(
                                "Semantic Scholar 429 (Too Many Requests) – retrying attempt %d/6 in %.2fs",
                                attempt + 1,
                                wait,
                            )
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
