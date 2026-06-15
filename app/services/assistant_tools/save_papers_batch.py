"""Tool: save_papers_batch — save many papers into the project in one call.

This is the bulk counterpart of ``save_paper_to_project`` for the agent
pipeline. It saves papers one at a time on the caller's ``AsyncSession`` and
returns a single summary so the agent doesn't have to issue N separate tool
calls. Pre-downloaded PDFs from ``search_papers`` are reused to avoid
re-downloading the same files.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING

from app.schemas.project import SavePaperRequest
from app.services.assistant_tools.ids import coerce_uuid
from app.services.project import save_paper_to_project

if TYPE_CHECKING:
    from app.services.assistant_runner import AssistantRunner

logger = logging.getLogger(__name__)


async def handle(db, user, args: dict, runner: AssistantRunner | None = None) -> dict:
    project_id = coerce_uuid(args["project_id"])
    papers: list[dict] = args.get("papers") or []
    relevance_label = args.get("relevance_label", "related")
    download_pdf = args.get("download_pdf", True)

    if not papers:
        return {"saved": 0, "skipped": 0, "failed": 0, "pdfs_available": 0}

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "save_papers",
                "status": "running",
                "percent": 0,
                "label": f"Saving {len(papers)} papers...",
            }
        )
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (
                    f"💾 Batch-saving {len(papers)} papers"
                ),
            }
        )

    saved_ids: list[str] = []
    failed_titles: list[str] = []
    pdfs_available = 0
    completed = 0
    total = len(papers)

    async def _save_one(paper: dict) -> None:
        nonlocal completed, pdfs_available
        try:
            title = paper.get("title", "Untitled")
            authors = []
            for author in paper.get("authors") or []:
                if isinstance(author, dict):
                    authors.append(
                        {"name": author.get("name", str(author)), "author_id": ""}
                    )
                else:
                    authors.append({"name": str(author), "author_id": ""})

            req = SavePaperRequest(
                paper_title=title,
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
                relevance_label=relevance_label,
                download_pdf=download_pdf,
                prefetched_pdf_path=paper.get("pdf_path"),
                prefetched_pdf_source=paper.get("pdf_source"),
                source_specific=paper.get("source_specific") or {},
            )
            resp = await save_paper_to_project(db, user, project_id, req)
            if resp is None:
                failed_titles.append(title[:80])
            else:
                saved_ids.append(str(resp.project_paper_id))
                if paper.get("pdf_downloaded") or paper.get("pdf_path"):
                    pdfs_available += 1
        except Exception as exc:
            logger.warning("Batch save failed for paper: %s", exc)
            with suppress(Exception):
                await db.rollback()
            failed_titles.append(str(paper.get("title", "?"))[:80])
        finally:
            completed += 1
            if runner and total > 0 and (completed % 5 == 0 or completed == total):
                pct = int(100 * completed / total)
                await runner.emit(
                    {
                        "type": "progress",
                        "step": "save_papers",
                        "status": "running",
                        "percent": pct,
                        "label": f"Saved {completed}/{total} papers",
                    }
                )

    for paper in papers:
        await _save_one(paper)

    saved = len(saved_ids)
    failed = len(failed_titles)

    if runner:
        await runner.emit(
            {
                "type": "progress",
                "step": "save_papers",
                "status": "done",
                "percent": 100,
                "label": f"Saved {saved}/{total} papers ({pdfs_available} PDFs ready)",
            }
        )
        await runner.emit(
            {
                "type": "log",
                "level": "info",
                "message": (
                    f"✓ Batch save complete: {saved} saved, "
                    f"{failed} failed, {pdfs_available} PDFs available"
                ),
            }
        )

    return {
        "saved": saved,
        "failed": failed,
        "skipped": 0,
        "total": total,
        "pdfs_available": pdfs_available,
        "saved_ids": saved_ids[:20],  # cap response size
        "failed_titles": failed_titles[:10],
    }
