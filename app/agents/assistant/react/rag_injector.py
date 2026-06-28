"""Auto-RAG injector for the ReAct agent.

Pre-fetches relevant context from the knowledge base before the reasoning loop starts.
Stores top-k chunks in the scratchpad for use by the LLM.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from app.agents.assistant.react.memory import Scratchpad
from app.services.eval_counters import eval_counters

logger = logging.getLogger(__name__)

# Default number of chunks to retrieve
DEFAULT_K = 3


async def inject(
    message: str,
    project_id: str | None,
    scratchpad: Scratchpad,
    user_id: str,
    k: int = DEFAULT_K,
) -> bool:
    """Inject relevant RAG context into the scratchpad.

    This function:
    1. Skips if project_id is None or empty
    2. Retrieves top-k chunks from the knowledge base using hybrid retrieval
    3. Stores the chunk texts in the scratchpad for the LLM to use

    Args:
        message: The user's message (used as the query).
        project_id: The project UUID string, or None if no project context.
        scratchpad: The ReAct scratchpad to inject context into.
        user_id: The authenticated user's ID.
        k: Number of chunks to retrieve (default 3).

    Returns:
        True if chunks were injected, False if skipped (no project, empty, or error).
    """
    start_time = time.monotonic()

    # Skip if no project context
    if not project_id:
        logger.debug("inject: skipped - no project_id")
        return False

    try:
        from uuid import UUID as PyUUID

        from app.db.session import async_session_factory
        from app.services.hybrid_retrieval import retrieve_project_evidence

        # Validate project_id format
        try:
            pid = PyUUID(project_id)
        except (ValueError, TypeError):
            logger.warning("inject: skipped - invalid project_id format: %s", project_id)
            return False

        # Retrieve evidence chunks
        async with async_session_factory() as db:
            chunks = await retrieve_project_evidence(
                db=db,
                project_id=pid,
                query=message,
                limit=k,
                use_reranker=True,
            )

        # Check if any chunks were retrieved
        if not chunks:
            logger.debug("inject: skipped - no chunks retrieved for project %s", project_id)
            return False

        # Extract text content from chunks
        chunk_texts = [chunk.chunk_text for chunk in chunks]

        # Store in scratchpad
        scratchpad.add_context(chunk_texts)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "inject: injected %d chunks (%.1fms) for project %s",
            len(chunk_texts),
            elapsed_ms,
            project_id,
        )

        # Record into eval counters for /api/stats/eval
        eval_counters.rag_injector.record(elapsed_ms)

        # Check latency requirement
        if elapsed_ms > 500:
            logger.warning(
                "inject: latency %.1fms exceeds 500ms threshold", elapsed_ms
            )

        return True

    except Exception as exc:
        # Never block the agent loop on RAG failures
        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.warning(
            "inject: failed (%.1fms) - %s: %s",
            elapsed_ms,
            type(exc).__name__,
            exc,
        )
        return False


async def inject_for_tool(
    tool_name: str,
    tool_args: dict,
    project_id: str | None,
    scratchpad: Scratchpad,
    user_id: str,
    k: int = DEFAULT_K,
) -> bool:
    """Inject RAG context tailored for a specific tool call.

    Use this when you know which tool will be called next and want
    more targeted context.

    Args:
        tool_name: The tool that will be called next.
        tool_args: The arguments being passed to the tool.
        project_id: The project UUID string.
        scratchpad: The ReAct scratchpad to inject context into.
        user_id: The authenticated user's ID.
        k: Number of chunks to retrieve (default 3).

    Returns:
        True if chunks were injected, False otherwise.
    """
    if not project_id:
        return False

    # Build a query from tool context
    query = _build_query_for_tool(tool_name, tool_args)

    if not query:
        logger.debug("inject_for_tool: no query generated for %s", tool_name)
        return False

    return await inject(
        message=query,
        project_id=project_id,
        scratchpad=scratchpad,
        user_id=user_id,
        k=k,
    )


def _build_query_for_tool(tool_name: str, tool_args: dict) -> str:
    """Build a retrieval query from tool context.

    Args:
        tool_name: Name of the tool being called.
        tool_args: Arguments to the tool.

    Returns:
        A query string for RAG retrieval, or empty string if not applicable.
    """
    # Specific queries based on tool
    if tool_name == "generate_matrix":
        # Get context about paper comparisons and evaluation metrics
        tool_args.get("project_id", "")
        return "Compare papers in project: methods, datasets, results, evaluation metrics"

    if tool_name == "detect_research_gaps":
        return "Research gaps, limitations, future work, unresolved problems"

    if tool_name == "detect_conflicts":
        return "Contradicting results, conflicting findings, disagreements"

    if tool_name == "generate_report":
        # Use explicit query if provided
        query = tool_args.get("query", "")
        if query:
            return query
        return "Summarize main findings, methodology, and conclusions"

    if tool_name == "retrieve_evidence":
        # Use the explicit query from tool args
        return tool_args.get("query", "")

    # For other tools, return empty (no targeted injection)
    return ""
