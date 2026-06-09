"""LangGraph agent state definition.

The ResearchState is the single source of truth flowing through every node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class ResearchState:
    """State that flows through the LangGraph research workflow.

    Nodes read and write this state. Nothing is hidden in closures or globals.
    """

    # ── Identity ──
    project_id: UUID
    user_id: UUID

    # ── Query Planning ──
    user_topic: str = ""
    research_question: str | None = None
    detected_language: str = ""
    core_concepts: list[str] = field(default_factory=list)
    query_variants: list[dict] = field(default_factory=list)  # [{lang, query, sources}]

    # ── Search ──
    raw_papers: list[dict] = field(default_factory=list)  # canonical RawPaper as dicts
    source_diagnostics: dict = field(default_factory=dict)  # {source_name: {status, count, error}}

    # ── User Screening ──
    saved_paper_ids: list[UUID] = field(default_factory=list)  # ProjectPaper.id
    screened_paper_ids: list[UUID] = field(default_factory=list)

    # ── Matrix Extraction ──
    matrix_rows: list[dict] = field(default_factory=list)  # [{project_paper_id, research_problem, method, ...}]
    matrix_status: str = "idle"  # idle | running | completed | failed

    # ── Gap Analysis ──
    gaps: list[dict] = field(default_factory=list)  # [{title, description, evidence_paper_ids, ...}]
    gap_status: str = "idle"

    # ── Review ──
    report_sections: list[dict] = field(default_factory=list)
    report_status: str = "idle"

    # ── Citation Validation ──
    citation_validation: dict = field(default_factory=dict)  # {valid: bool, invalid_ids: [...]}

    # ── Flow Control ──
    current_node: str = ""
    errors: list[str] = field(default_factory=list)
    completed: bool = False
