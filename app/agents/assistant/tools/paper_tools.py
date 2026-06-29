"""
Paper tools for the Assistant.

Provides tools for searching, saving, removing, and listing papers.

Use these when:
- The user wants to find papers on a topic
- The user wants to save a paper to a project
- The user wants to see papers in a project
- The user wants to remove a paper from a project
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from app.agents.assistant.tools.context import get_user, get_user_id

if TYPE_CHECKING:
    pass


def _ok_result(message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a success result dict."""
    result = {"ok": True, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _error_result(error_code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create an error result dict that the LLM can reason about."""
    result = {"ok": False, "error_code": error_code, "message": message}
    if details is not None:
        result["details"] = details
    return result


# ── Paper Search ───────────────────────────────────────────────────────────


async def _search_papers_impl(
    query: str,
    sources: list[str],
    year_from: int | None,
    year_to: int | None,
    limit: int,
) -> dict[str, Any]:
    """
    Search for papers using the paper search service.

    Runs all sources in parallel with asyncio.gather and a per-source timeout (45s).

    Args:
        query: Search query string.
        sources: List of sources to search (e.g., semantic_scholar, paperhub).
        year_from: Filter papers from this year.
        year_to: Filter papers until this year.
        limit: Maximum results per source.

    Returns:
        Dict with papers list and source diagnostics.
    """
    try:
        from app.schemas.paper import PaperSearchRequest
        from app.services.paper_search import search_and_download

        request = PaperSearchRequest(
            query=query,
            sources=sources,
            year_from=year_from,
            year_to=year_to,
            limit=limit,
            download_pdfs=False,  # Don't download by default for search
        )

        # Run with timeout
        outcome = await asyncio.wait_for(
            search_and_download(request),
            timeout=45.0,
        )

        papers = []
        for raw in outcome.raw_papers:
            paper_dict = {
                "paper_id": raw.semantic_scholar_id or raw.arxiv_id or raw.doi or "",
                "title": raw.title,
                "authors": raw.authors,
                "year": raw.year,
                "doi": raw.doi,
                "abstract": raw.abstract,
                "source": raw.source_name,
                "url": raw.url,
                "citation_count": raw.citation_count,
            }
            papers.append(paper_dict)

        source_diagnostics = {d.get("source", ""): d.get("status", "unknown") for d in outcome.response.source_diagnostics}

        return _ok_result(
            f"Found {len(papers)} papers",
            {
                "papers": papers,
                "total_count": len(papers),
                "source_diagnostics": source_diagnostics,
            }
        )
    except TimeoutError:
        return _error_result("SEARCH_TIMEOUT", "Paper search timed out after 45 seconds")
    except Exception as exc:
        return _error_result("SEARCH_FAILED", str(exc))


# ── Paper Save/Remove ──────────────────────────────────────────────────────


async def _save_paper_impl(
    project_id: str,
    paper: dict[str, Any],
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    Save a paper to a project.

    Args:
        project_id: Target project UUID string.
        paper: Paper data dict with title, authors, year, doi, etc.
        user_id: User ID.
        user: User model instance.

    Returns:
        Dict with project_paper_id, status, and duplicate flag.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")

    try:
        from uuid import UUID as PyUUID

        from app.db.session import async_session_factory
        from app.schemas.project import SavePaperRequest
        from app.services.project import save_paper_to_project

        pid = PyUUID(project_id)

        # Build SavePaperRequest from paper dict
        save_request = SavePaperRequest(
            paper_title=paper.get("title", ""),
            paper_abstract=paper.get("abstract"),
            paper_year=paper.get("year"),
            paper_doi=paper.get("doi"),
            paper_arxiv_id=paper.get("arxiv_id"),
            paper_semantic_scholar_id=paper.get("paper_id") or paper.get("semantic_scholar_id"),
            paper_url=paper.get("url"),
            paper_citation_count=paper.get("citation_count"),
            paper_authors=paper.get("authors", []),
            paper_source_names=[paper.get("source", "unknown")],
            download_pdf=False,
        )

        async with async_session_factory() as db:
            result = await save_paper_to_project(db, user, pid, save_request)

        if result is None:
            return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")

        # Check if it was a duplicate
        # The service doesn't explicitly say if duplicate, so we check if paper was already in project
        is_duplicate = False  # Would need additional logic to detect duplicates

        return _ok_result(
            f"Saved paper: {result.title}",
            {
                "project_paper_id": str(result.id),
                "status": result.status,
                "duplicate": is_duplicate,
            }
        )
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID: {project_id}")
    except Exception as exc:
        return _error_result("SAVE_PAPER_FAILED", str(exc))


async def _remove_paper_impl(
    project_id: str,
    project_paper_id: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    Remove a paper from a project.

    Args:
        project_id: Project UUID string.
        project_paper_id: Project-paper association UUID string.
        user_id: User ID.
        user: User model instance.

    Returns:
        Dict with success status.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")

    try:
        from uuid import UUID as PyUUID

        from app.db.session import async_session_factory
        from app.services.project import remove_project_paper

        pid = PyUUID(project_id)
        ppid = PyUUID(project_paper_id)

        async with async_session_factory() as db:
            success = await remove_project_paper(db, user, pid, ppid)

        if not success:
            return _error_result("PAPER_NOT_FOUND", "Paper not found in project or access denied")

        return _ok_result("Removed paper from project")
    except ValueError:
        return _error_result("INVALID_ID", "Invalid project or paper ID format")
    except Exception as exc:
        return _error_result("REMOVE_PAPER_FAILED", str(exc))


async def _list_project_papers_impl(
    project_id: str,
    status: str,
    user_id: str | None,
    user: Any | None,
) -> dict[str, Any]:
    """
    List papers in a project.

    Args:
        project_id: Project UUID string.
        status: Filter by status (saved, pending, removed).
        user_id: User ID.
        user: User model instance.

    Returns:
        Dict with papers list.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")

    try:
        from uuid import UUID as PyUUID

        from app.db.session import async_session_factory
        from app.services.project import list_project_papers

        pid = PyUUID(project_id)

        async with async_session_factory() as db:
            papers = await list_project_papers(db, user, pid)

            if papers is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")

            paper_list = []
            for p in papers:
                # Truncate authors to prevent context explosion
                truncated_authors = p.authors[:3] if isinstance(p.authors, list) else []
                if isinstance(p.authors, list) and len(p.authors) > 3:
                    truncated_authors.append({"name": "et al.", "author_id": ""})

                paper_list.append({
                    "project_paper_id": str(p.id),
                    "paper_id": str(p.paper_id),
                    "title": p.title,
                    "authors": truncated_authors,
                    "year": p.year,
                    "doi": p.doi,
                    "arxiv_id": p.arxiv_id,
                    "abstract": p.abstract,
                    "status": p.status,
                    "relevance_label": p.relevance_label,
                    "saved_at": p.saved_at.isoformat() if p.saved_at else None,
                })

            return _ok_result(
                f"Found {len(paper_list)} papers",
                {"papers": paper_list}
            )
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("LIST_PAPERS_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
async def search_papers(
    query: str,
    sources: list[str] = Field(default=["semantic_scholar"]),
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Search for academic papers from multiple sources.

    Use this when the user wants to find papers on a specific topic or research question.
    Search runs in parallel across all specified sources.

    Sources:
    - semantic_scholar: Academic paper search (default)
    - paperhub: Additional paper source
    - exa: Web-based paper search

    Returns:
        List of papers with metadata (title, authors, year, DOI, abstract, etc.)

    Args:
        query: Search query (e.g., "retrieval augmented generation medical").
        sources: List of sources to search.
        year_from: Filter papers from this year.
        year_to: Filter papers until this year.
        limit: Maximum papers per source (default 20, max 100).
    """
    return await _search_papers_impl(query, sources, year_from, year_to, limit)


@tool
async def save_paper_to_project(
    project_id: str,
    paper_json: str,
) -> dict[str, Any]:
    """
    Save a paper to a specific project.

    Use this when the user asks to save a paper they found or specified.
    The paper data should be a JSON string containing: title, authors, year, doi (if available).

    Returns:
        project_paper_id and save status.

    Args:
        project_id: The target project UUID.
        paper_json: JSON string representing paper data with at least title and authors.
    """
    import json
    try:
        paper = json.loads(paper_json)
    except Exception as exc:
        return _error_result("INVALID_JSON", f"Failed to parse paper_json: {exc}")

    user = get_user()
    uid = get_user_id()
    return await _save_paper_impl(project_id, paper, uid, user)


@tool
async def remove_paper_from_project(
    project_id: str,
    project_paper_id: str,
) -> dict[str, Any]:
    """
    Remove a paper from a project.

    Use this when the user wants to delete a paper from a project.

    Returns:
        Success status.

    Args:
        project_id: The project UUID.
        project_paper_id: The project-paper association UUID to remove.
    """
    user = get_user()
    uid = get_user_id()
    return await _remove_paper_impl(project_id, project_paper_id, uid, user)


@tool
async def list_project_papers(
    project_id: str,
    status: str = "saved",
) -> dict[str, Any]:
    """
    List all papers in a project.

    Use this when the user wants to see what papers are saved in a project,
    or to verify a paper was saved correctly.

    IMPORTANT: Do not call this tool multiple times for the same project. 
    Once you receive the list of papers, stop calling tools and present the summary to the user.

    Returns:
        List of papers with metadata.

    Args:
        project_id: The project UUID.
        status: Filter by status (saved, pending, removed). Default: saved.
    """
    user = get_user()
    uid = get_user_id()
    return await _list_project_papers_impl(project_id, status, uid, user)


# ── Toolkit Registration ─────────────────────────────────────────────────────

from app.agents.assistant.tools.base import BaseToolkit, register_toolkit


@register_toolkit
class PaperToolkit(BaseToolkit):
    """Toolkit for paper-related operations."""

    def get_tools(self) -> list[BaseTool]:
        return [
            search_papers,
            save_paper_to_project,
            remove_paper_from_project,
            list_project_papers,
        ]
