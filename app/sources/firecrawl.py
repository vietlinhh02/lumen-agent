"""Firecrawl utility — crawl paper pages to find direct PDF download links."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.core.config import get_settings
from app.sources.base import RawPaper

logger = logging.getLogger(__name__)

_FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
_PDF_LINK_RE = re.compile(r'https?://[^\s"\'<>]+\.pdf(?:/[^\s"\'<>]*)?', re.IGNORECASE)
_CONCURRENCY = 5
_SCRAPE_TIMEOUT = 15.0


async def crawl_pdf_links(
    papers: list[RawPaper],
    concurrency: int = _CONCURRENCY,
    timeout: float = _SCRAPE_TIMEOUT,
) -> list[RawPaper]:
    """Crawl paper URLs to find direct PDF download links.

    For each paper that has a URL but no ``pdf_url`` in ``source_specific``,
    scrape the page and extract .pdf links from the content.

    Modifies ``paper.source_specific["pdf_url"]`` in-place on success.
    Returns the (possibly modified) list.
    """
    settings = get_settings()
    if not settings.firecrawl_api_key:
        logger.warning("FIRECRAWL_API_KEY not set, skipping Firecrawl crawl")
        return papers

    targets = [p for p in papers if p.url and not p.source_specific.get("pdf_url")]
    if not targets:
        return papers

    sem = asyncio.Semaphore(concurrency)

    async def _crawl_one(paper: RawPaper) -> None:
        async with sem:
            try:
                url = paper.url
                if not url:
                    return
                pdf = await _scrape_pdf_url(url, settings.firecrawl_api_key, timeout)
                if pdf:
                    paper.source_specific["pdf_url"] = pdf
                    logger.info("Firecrawl found PDF: %s", pdf[:100])
            except Exception as exc:
                logger.debug("Firecrawl scrape failed for %s: %s", paper.url, exc)

    await asyncio.gather(*(_crawl_one(p) for p in targets), return_exceptions=True)
    return papers


async def _scrape_pdf_url(
    url: str,
    api_key: str,
    timeout: float,
) -> str | None:
    """Scrape a single URL via Firecrawl to find a direct PDF link."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _FIRECRAWL_SCRAPE_URL,
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("success"):
        return None

    markdown = data.get("data", {}).get("markdown", "")
    if not markdown:
        return None

    match = _PDF_LINK_RE.search(markdown)
    return match.group(0) if match else None
