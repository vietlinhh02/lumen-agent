"""ArXiv metadata enrichment service.

Some papers come into the project with an empty ``authors`` field because
the upstream source (Semantic Scholar, Exa, Firecrawl) returned the paper
without an author list. When we have an ``arxiv_id`` we can recover the
author metadata from the arXiv abstract page, which is the canonical source
of record for arXiv submissions.

This service is intentionally:

* read-only with respect to the live arXiv API (one HTTP GET per paper);
* lenient — it never raises; failures are logged and the caller falls
  back to the empty author list;
* rate-limit friendly — concurrent calls are bounded by a small semaphore
  so a single report generation cannot hammer arXiv with 50 parallel
  requests.

Used by:
    * ``report_generation._enrich_paper_metadata`` — back-fills authors
      right before the report's reference list is rendered.
    * (Future) paper ingestion — could be wired in as a side effect of
      saving a paper that came in with no authors.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable

import httpx

logger = logging.getLogger(__name__)

# Bound the in-flight arXiv calls so a 50-paper report does not launch
# 50 parallel requests. arXiv's published rate-limit guidance is one
# request every 3 seconds for the API; the abstract page is more lenient
# but we still cap concurrency defensively.
_ARXIV_FETCH_SEMAPHORE = asyncio.Semaphore(4)

# 5-second per-request timeout — abstract pages are small (< 50 kB).
_ARXIV_TIMEOUT_SECONDS = 5.0

# A single arXiv author block looks like:
#   <meta name="citation_author" content="Yin, Zhuowen" />
# but the abstract HTML also embeds the same data in <div class="authors">
#   <a href="...">Zhuowen Yin</a>
# We support both because the meta-tag form is the most stable.
_META_AUTHOR_RE = re.compile(
    r'<meta\s+name="citation_author"\s+content="([^"]+)"',
    re.IGNORECASE,
)
_AUTHORS_DIV_RE = re.compile(
    r'<div[^>]+class="authors"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_ANCHOR_RE = re.compile(
    r"<a[^>]*>([^<]+)</a>",
    re.IGNORECASE,
)


def _parse_authors_from_html(html: str) -> list[dict[str, str]]:
    """Extract an author list from an arXiv abstract page.

    Returns a list of ``{"name": "Yin, Zhuowen", "author_id": ""}`` dicts
    matching the schema used by ``Paper.authors``. Order is preserved
    (which is author-order on the abstract page).
    """
    # Prefer the meta-tag form — most stable.
    meta_hits = _META_AUTHOR_RE.findall(html)
    if meta_hits:
        # Unescape common HTML entities. arXiv mostly emits names like
        # "Yin, Zhuowen" or "Andr&#233; Martins". We handle the named
        # entities plus numeric character references (decimal form).
        def _unescape(s: str) -> str:
            s = (
                s.replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
                .replace("&apos;", "'")
            )
            # Numeric character references: &#NNN; and &#xHH;
            s = re.sub(
                r"&#(\d+);",
                lambda m: chr(int(m.group(1))),
                s,
            )
            s = re.sub(
                r"&#x([0-9a-fA-F]+);",
                lambda m: chr(int(m.group(1), 16)),
                s,
            )
            return s

        return [{"name": _unescape(name), "author_id": ""} for name in meta_hits]

    # Fallback: scrape the authors <div>.
    div_match = _AUTHORS_DIV_RE.search(html)
    if div_match:
        anchor_names = _ANCHOR_RE.findall(div_match.group(1))
        if anchor_names:
            return [{"name": name.strip(), "author_id": ""} for name in anchor_names if name.strip()]

    return []


async def fetch_arxiv_authors(arxiv_id: str) -> list[dict[str, str]]:
    """Fetch the author list for a paper from its arXiv abstract page.

    Returns an empty list if:
    * the page is not reachable;
    * the page does not embed any author metadata;
    * the network call fails for any reason.

    The function never raises.
    """
    arxiv_id = (arxiv_id or "").strip()
    if not arxiv_id:
        return []

    # Strip the optional ``v1`` version suffix from the ID; the abstract
    # page is the same for every version of a paper.
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id)

    url = f"https://arxiv.org/abs/{arxiv_id}"

    async with _ARXIV_FETCH_SEMAPHORE:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=_ARXIV_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(url)
        except (TimeoutError, httpx.HTTPError) as exc:
            logger.warning("arXiv abstract fetch failed for %s: %s", arxiv_id, exc)
            return []

        if response.status_code != 200:
            logger.warning(
                "arXiv abstract returned HTTP %s for %s",
                response.status_code,
                arxiv_id,
            )
            return []

        return _parse_authors_from_html(response.text)


async def enrich_papers_concurrently(arxiv_ids: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    """Fetch authors for many arXiv IDs in parallel.

    Returns a dict ``{arxiv_id: [author, ...]}``. IDs that fail to resolve
    are simply absent from the dict (or map to ``[]`` when parsing
    succeeded but the page had no author block).
    """
    unique_ids = list({(aid or "").strip() for aid in arxiv_ids if (aid or "").strip()})
    if not unique_ids:
        return {}

    results = await asyncio.gather(
        *(fetch_arxiv_authors(aid) for aid in unique_ids),
        return_exceptions=False,
    )

    return dict(zip(unique_ids, results, strict=True))
