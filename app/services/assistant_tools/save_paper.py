"""Tool: save_paper_to_project — save one paper into the project corpus.

Saves to ProjectPaper + Paper tables, triggers PDF download + background ingestion.
The paper will be available on the Search, Saved Papers, Matrix, Gaps, Conflicts,
and Reports pages.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.schemas.project import SavePaperRequest
from app.services.assistant_tools.ids import coerce_uuid
from app.services.project import save_paper_to_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    project_id = coerce_uuid(args["project_id"])
    paper = args["paper"]

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "save_papers",
                "status": "running",
                "percent": 0,
                "label": f"Saving paper: {paper.get('title', 'unknown')[:50]}",
            }
        )
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": f"💾 Saving: {paper.get('title', 'Untitled')[:60]}",
            }
        )

    authors = []
    for a in paper.get("authors") or []:
        if isinstance(a, dict):
            authors.append({"name": a.get("name", str(a)), "author_id": ""})
        else:
            authors.append({"name": str(a), "author_id": ""})

    req = SavePaperRequest(
        paper_title=paper.get("title", "Untitled"),
        paper_abstract=paper.get("abstract"),
        paper_year=paper.get("year"),
        paper_venue=paper.get("venue"),
        paper_doi=paper.get("doi"),
        paper_arxiv_id=paper.get("arxiv_id"),
        paper_semantic_scholar_id=paper.get("semantic_scholar_id"),
        paper_url=paper.get("url"),
        paper_citation_count=paper.get("citation_count"),
        paper_authors=authors,
        paper_source_names=paper.get("source_names") or ["paperhub"],
        relevance_label=args.get("relevance_label", "related"),
        download_pdf=args.get("download_pdf", True),
        # If search_papers already downloaded the PDF, reuse the local path
        # to skip a redundant network round-trip.
        prefetched_pdf_path=paper.get("pdf_path"),
        prefetched_pdf_source=paper.get("pdf_source"),
        source_specific=paper.get("source_specific") or {},
    )
    resp = await save_paper_to_project(db, user, project_id, req)

    if resp is None:
        if runner:
            await runner.emit(
                {
                    "type": "progress",
                    "step": "save_papers",
                    "status": "failed",
                    "percent": 0,
                    "label": "Paper not saved (duplicate or invalid)",
                }
            )
        return {"saved": False, "error": "duplicate or invalid paper"}

    if runner:
        pdf_status = resp.full_text_status or "pending"
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (f"✓ Saved: {paper.get('title', 'Untitled')[:50]}. PDF: {pdf_status}"),
            }
        )
        await runner.emit(
            {
                "type": "progress",
                "step": "save_papers",
                "status": "done",
                "percent": 100,
                "label": f"Saved: {paper.get('title', 'Untitled')[:40]}",
            }
        )

    return {
        "saved": True,
        "project_paper_id": str(resp.project_paper_id),
        "full_text_status": resp.full_text_status,
    }
