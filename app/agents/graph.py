"""LangGraph research workflow graph.

Compiles the fixed DAG of agent nodes. The graph is stateful: a run
produces intermediate checkpoints that the frontend can poll.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.nodes import (
    citation_validator_node,
    conflict_detection_node,
    gap_analysis_node,
    matrix_extraction_node,
    query_planner_node,
    review_writer_node,
    save_screened_node,
    search_agent_node,
)
from app.agents.state import ResearchState
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


# ── Graph Builder ───────────────────────────────────────────────────────────


def _needs_db(node_fn: Any) -> bool:
    """Check if a node function accepts a ``db`` parameter (by name or type hint)."""
    sig = inspect.signature(node_fn)
    params = list(sig.parameters.values())
    if len(params) < 2:
        return False
    p = params[1]
    return p.name == "db" or "AsyncSession" in str(p.annotation)


def build_research_graph() -> StateGraph:
    """Return a compiled LangGraph for the research workflow.

    Graph topology::

        query_planner → search_agent → save_screened
        → matrix_extraction → gap_analysis → review_writer
        → citation_validator → END
    """
    graph = StateGraph(ResearchState)

    # ── add all nodes ──────────────────────────────────────────────────
    graph.add_node("query_planner", _wrap(query_planner_node))
    graph.add_node("search_agent", _wrap(search_agent_node))
    graph.add_node("save_screened", _wrap(save_screened_node))
    graph.add_node("matrix_extraction", _wrap(matrix_extraction_node))
    graph.add_node("gap_analysis", _wrap(gap_analysis_node))
    graph.add_node("conflict_detection", _wrap(conflict_detection_node))
    graph.add_node("review_writer", _wrap(review_writer_node))
    graph.add_node("citation_validator", _wrap(citation_validator_node))

    # ── linear pipeline ────────────────────────────────────────────────
    graph.set_entry_point("query_planner")
    graph.add_edge("query_planner", "search_agent")
    graph.add_edge("search_agent", "save_screened")
    graph.add_edge("save_screened", "matrix_extraction")
    graph.add_edge("matrix_extraction", "gap_analysis")
    graph.add_edge("gap_analysis", "conflict_detection")
    graph.add_edge("conflict_detection", "review_writer")
    graph.add_edge("review_writer", "citation_validator")
    graph.add_edge("citation_validator", END)

    return graph.compile()


def _wrap(node_fn):
    """Wrap an async node so LangGraph can invoke it.

    LangGraph nodes receive ``state`` and return a dict of partial updates.
    Nodes that accept a second ``db`` parameter receive an async session.
    """
    if _needs_db(node_fn):

        async def wrapper(state: ResearchState) -> dict[str, Any]:
            async with async_session_factory() as db:
                return await node_fn(state, db)
    else:

        async def wrapper(state: ResearchState) -> dict[str, Any]:
            return await node_fn(state)

    return wrapper


# ── Module-level compiled graph ─────────────────────────────────────────────

_research_graph = build_research_graph()


async def run_research_workflow(
    project_id: str,
    user_id: str,
    topic: str,
    research_question: str | None = None,
) -> ResearchState:
    """Execute the full research workflow synchronously (for API endpoints).

    Args:
        project_id: UUID of the project.
        user_id: UUID of the authenticated user.
        topic: The research topic / user query.
        research_question: Optional specific research question.

    Returns:
        The final ``ResearchState`` after all nodes have completed.
    """
    import uuid

    initial_state = ResearchState(
        project_id=uuid.UUID(project_id),
        user_id=uuid.UUID(user_id),
        user_topic=topic,
        research_question=research_question,
    )

    logger.info("Starting research workflow for project %s", project_id)
    final_state = await _research_graph.ainvoke(initial_state)
    logger.info(
        "Research workflow completed for project %s — %d papers, %d gaps, %d sections",
        project_id,
        len(final_state.get("raw_papers", [])),
        len(final_state.get("gaps", [])),
        len(final_state.get("report_sections", [])),
    )
    return ResearchState(**final_state)


async def run_partial_workflow(
    state: ResearchState,
    from_node: str,
    to_node: str | None = None,
) -> ResearchState:
    """Run a subset of the graph starting from ``from_node``.

    Useful for re-running just the matrix extraction or gap analysis
    after the user has edited intermediate data.
    """
    # Clone the compiled graph but only run the requested segment
    # For now we delegate to the full graph — partial runs can be added later.
    logger.warning("Partial workflow not fully implemented — running full graph")
    return ResearchState(**await _research_graph.ainvoke(state))
