"""Exa semantic web search source adapter."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.sources.base import PaperSource, RawPaper

logger = logging.getLogger(__name__)

_EXA_SEARCH_URL = "https://api.exa.ai/search"


class ExaSource(PaperSource):
    """Search for research papers using Exa semantic web search."""

    name = "exa"

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        settings = get_settings()
        if not settings.exa_api_key:
            logger.warning("EXA_API_KEY not set, skipping Exa search")
            return []

        body: dict = {
            "query": query,
            "type": "neural",
            "useAutoprompt": False,
            "numResults": min(limit, 25),
        }
        if year_from:
            body["startPublishedDate"] = f"{year_from}-01-01"
        if year_to:
            body["endPublishedDate"] = f"{year_to}-12-31"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _EXA_SEARCH_URL,
                json=body,
                headers={
                    "x-api-key": settings.exa_api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        return [_exa_to_raw(r) for r in results]


def _exa_to_raw(result: dict) -> RawPaper:
    """Map an Exa search result to a canonical RawPaper."""
    published = result.get("publishedDate", "")
    year = _parse_year(published)

    return RawPaper(
        title=result.get("title", ""),
        abstract=result.get("text") or None,
        year=year,
        url=result.get("url") or None,
        authors=_parse_exa_author(result.get("author")),
        source_name="exa",
        source_specific={"exa_raw": result},
    )


def _parse_year(date_str: str) -> int | None:
    """Extract year from an Exa publishedDate string."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str.strip()[:10], fmt).year
        except (ValueError, IndexError):
            continue
    return None


def _parse_exa_author(author: str | None) -> list[dict[str, str]]:
    """Parse Exa author string into canonical author list."""
    if not author:
        return []
    return [{"name": a.strip(), "author_id": ""} for a in author.split(",") if a.strip()]
