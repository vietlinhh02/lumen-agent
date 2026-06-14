"""Tool: save_paper_to_project — save one paper into the project corpus."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from app.schemas.project import SavePaperRequest
from app.services.project import save_paper_to_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: "AssistantRunner | None" = None) -> dict:
    project_id = UUID(args["project_id"])
    paper = args["paper"]
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
        download_pdf=False,
    )
    resp = await save_paper_to_project(db, user, project_id, req)
    if resp is None:
        return {"saved": False, "error": "duplicate or invalid paper"}
    return {"saved": True, "project_paper_id": resp.project_paper_id}
