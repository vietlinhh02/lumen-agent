"""Tool: search_papers — fan out to academic sources.

Uses the same search_and_download service as the Search page, ensuring consistent
results across the platform. Downloads PDFs when requested.

The tool returns TWO views of the result set:
- ``paper_brief`` — compact one-line-per-paper dict with id/title/year/authors
  designed to fit inside the 16K-char tool summary the runner hands to the LLM.
  Each brief is ~150 bytes; 100 papers fit easily.
- ``papers`` — full dicts with abstract, source_specific, etc. The LLM does NOT
  see this in the truncated summary, but it can pass these dicts to
  ``save_papers_batch`` to save the full paper (including abstract).

This split solves the bug where the runner's 1500-char truncation was
collapsing 50 papers into 2-3, causing the LLM to save just 1 paper per turn.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.db.models import User
from app.schemas.paper import PaperSearchRequest
from app.services.paper_search import search_and_download

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)

# Briefs are kept to ~120 bytes so 100 of them fit in the 16K-char tool
# summary the runner sends to the LLM. We deliberately drop the abstract
# from the LLM-visible brief — the LLM doesn't need it to decide which
# papers to save, and the full abstract is still passed through in
# ``papers`` when the LLM forwards papers to save_papers_batch.
_AUTHOR_PREVIEW_COUNT = 3
_TITLE_PREVIEW_CHARS = 120


def _make_brief(paper: dict) -> dict:
    """Compress a full paper dict to a 1-line view safe for the LLM summary.

    Keeps the fields needed to *decide* which papers to save. The full paper
    object (with abstract) is also returned in ``papers`` and can be passed
    to ``save_papers_batch`` directly.
    """
    title = paper.get("title", "")
    return {
        # Stable identifier the LLM can refer to
        "id": (
            paper.get("arxiv_id")
            or paper.get("doi")
            or paper.get("semantic_scholar_id")
            or title[:60]
        ),
        "title": title[:_TITLE_PREVIEW_CHARS],
        "year": paper.get("year"),
        "venue": paper.get("venue"),
        "authors": [
            a.get("name") if isinstance(a, dict) else str(a)
            for a in (paper.get("authors") or [])[:_AUTHOR_PREVIEW_COUNT]
        ],
        "citation_count": paper.get("citation_count"),
        "arxiv_id": paper.get("arxiv_id"),
        "doi": paper.get("doi"),
        "semantic_scholar_id": paper.get("semantic_scholar_id"),
        "pdf_downloaded": paper.get("pdf_downloaded", False),
        "pdf_path": paper.get("pdf_path"),
        "pdf_source": paper.get("pdf_source"),
    }


async def handle(db, user: User, args: dict, runner: AssistantRunner | None = None) -> dict:
    query = args.get("query", "")
    # Default to 50 — high enough to get good coverage but not wasteful
    max_results = min(args.get("max_results", 50), 100)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "search_papers",
                "status": "running",
                "percent": 5,
                "label": f"Searching: '{query}' (max {max_results})",
            }
        )
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (
                    f"🔍 Searching {max_results} papers for: '{query}' — "
                    "PDFs will be downloaded in parallel"
                ),
            }
        )

    req = PaperSearchRequest(
        query=query,
        limit=max_results,
        year_from=args.get("year_from"),
        download_pdfs=args.get("download_pdfs", True),
    )

    try:
        outcome = await search_and_download(req)
    except Exception as exc:
        logger.exception("Search failed")
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "search_papers",
                    "status": "failed",
                    "percent": 0,
                    "label": f"Search failed: {exc}",
                }
            )
        return {"error": str(exc), "papers_found": 0}

    papers = [p.model_dump() for p in outcome.response.papers]
    total = outcome.response.total_returned
    downloaded = outcome.response.pdfs_downloaded
    failed = outcome.response.pdfs_failed

    # Build a brief + full view. Briefs are LLM-visible; full dicts are passed
    # to save_papers_batch by the LLM. Order is preserved (PDFs-first).
    paper_briefs = [_make_brief(p) for p in papers]

    if runner:
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (
                    f"✓ Found {total} papers. "
                    f"PDFs ready: {downloaded}/{total} "
                    f"({failed} not downloadable). "
                    f"Downloadable papers are sorted to the top."
                ),
            }
        )
        await runner.emit(
            {
                "type": "progress",
                "step": "search_papers",
                "status": "done",
                "percent": 100,
                "label": (
                    f"Found {total} papers · "
                    f"{downloaded} PDFs ready (sorted to top)"
                ),
            }
        )

    # NOTE: `paper_brief` comes BEFORE `papers` in the dict so the 16K-char
    # tool-summary truncation (applied by the runner) keeps the LLM-visible
    # brief intact. Full paper dicts are preserved at the end of the payload
    # so the LLM can pass them verbatim to save_papers_batch.
    return {
        "paper_brief": paper_briefs,
        "papers": papers,
        "papers_found": total,
        "pdfs_downloaded": downloaded,
        "pdfs_failed": failed,
        "diagnostics": outcome.response.source_diagnostics,
    }
