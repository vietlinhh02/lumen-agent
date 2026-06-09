"""LangGraph agent workflow.

The research graph runs these nodes in sequence::

    query_planner → search_agent → save_screened
    → matrix_extraction → gap_analysis → review_writer
    → citation_validator → END

Each node is a pure async function that reads/writes ``ResearchState``.
"""

from app.agents.graph import run_research_workflow
from app.agents.state import ResearchState

__all__ = ["run_research_workflow", "ResearchState"]
