"""Tool: search_papers — fan out to academic sources."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.db.models import User
from app.schemas.paper import PaperSearchRequest
from app.services.paper_search import search_and_download

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user: "User", args: dict, runner: "AssistantRunner | None" = None) -> dict:
    if runner:
        await runner.emit(
            {"type": "log", "level": "info", "message": f"🔍 Searching: '{args.get('query', '')}'"}
        )

    req = PaperSearchRequest(
        query=args["query"],
        limit=min(args.get("max_results", 25), 100),
        year_from=args.get("year_from"),
        download_pdfs=False,
    )
    outcome = await search_and_download(req)
    papers = [p.model_dump() for p in outcome.response.papers]

    if runner:
        await runner.emit(
            {"type": "log", "level": "info", "message": f"✓ Found {len(papers)} candidates"}
        )

    return {
        "papers": papers,
        "papers_found": len(papers),
        "diagnostics": outcome.response.source_diagnostics,
    }
