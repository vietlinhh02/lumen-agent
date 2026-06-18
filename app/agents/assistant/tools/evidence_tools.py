"""
Evidence tools for the Assistant.

Provides tools for retrieving relevant evidence chunks from saved papers.

Use these when:
- The user wants to find supporting evidence for a claim
- The user wants to query the knowledge base for specific information
- The user wants to understand what the papers say about a topic
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.tools import tool

from app.agents.assistant.tools.context import get_user, get_user_id

if TYPE_CHECKING:
    pass


def _ok_result(message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a success result dict."""
    result = {"ok": True, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _error_result(error_code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create an error result dict that the LLM can reason about."""
    result = {"ok": False, "error_code": error_code, "message": message}
    if details is not None:
        result["details"] = details
    return result


# ── Implementations ────────────────────────────────────────────────────────


async def _retrieve_evidence_impl(
    project_id: str,
    query: str,
    k: int,
    content_types: Optional[List[str]],
    user_id: Optional[str],
    user: Optional[Any],
) -> Dict[str, Any]:
    """
    Retrieve relevant evidence chunks from saved papers.
    
    Args:
        project_id: Project UUID string.
        query: Evidence query string.
        k: Number of chunks to retrieve.
        content_types: Optional filter for content types.
        user_id: User ID.
        user: User model instance.
    
    Returns:
        Dict with retrieved chunks.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")
    
    try:
        from uuid import UUID as PyUUID
        
        from app.db.session import async_session_factory
        from sqlalchemy import select
        from app.db.models import Project
        from app.services.hybrid_retrieval import retrieve_project_evidence
        
        pid = PyUUID(project_id)
        
        async with async_session_factory() as db:
            # Verify ownership
            project_result = await db.execute(
                select(Project).where(Project.id == pid, Project.owner_id == user.id)
            )
            if project_result.scalar_one_or_none() is None:
                return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")
            
            # Retrieve evidence
            chunks = await retrieve_project_evidence(
                db=db,
                project_id=pid,
                query=query,
                limit=k,
                content_types=content_types,
                use_reranker=True,
            )
        
        # Format chunks for output
        chunk_list = []
        for chunk in chunks:
            chunk_list.append({
                "chunk_id": str(chunk.chunk_id),
                "content": chunk.chunk_text,
                "project_paper_id": str(chunk.project_paper_id),
                "paper_id": str(chunk.paper_id),
                "title": chunk.title,
                "score": chunk.score,
                "content_type": chunk.content_type,
                "section_label": chunk.section_label,
                "section_path": chunk.section_path,
            })
        
        return _ok_result(
            f"Retrieved {len(chunk_list)} evidence chunks",
            {
                "chunks": chunk_list,
                "query": query,
                "total_retrieved": len(chunk_list),
            }
        )
        
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("RETRIEVE_EVIDENCE_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
async def retrieve_evidence(
    project_id: str,
    query: str,
    k: int = 8,
    content_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Retrieve relevant evidence chunks from saved papers for a query.

    Use this when the user wants to find supporting evidence from their saved papers.
    This uses hybrid retrieval (vector + keyword search) with reranking to find
    the most relevant passages.

    Content types filter:
    - abstract: Paper abstracts
    - method: Methodology sections
    - results: Results and findings
    - conclusion: Conclusions and discussions

    Returns:
        List of evidence chunks with relevance scores.

    Args:
        project_id: The project UUID.
        query: The evidence query (e.g., "What datasets were used in RAG systems?").
        k: Number of chunks to retrieve (default 8, max 50).
        content_types: Optional filter for content types to search.
    """
    user = get_user()
    uid = get_user_id()
    return await _retrieve_evidence_impl(project_id, query, k, content_types, uid, user)


# ── Toolkit Registration ─────────────────────────────────────────────────────


from app.agents.assistant.tools.base import BaseToolkit, register_toolkit


@register_toolkit
class EvidenceToolkit(BaseToolkit):
    """Toolkit for evidence retrieval."""

    def get_tools(self):
        return [retrieve_evidence]
