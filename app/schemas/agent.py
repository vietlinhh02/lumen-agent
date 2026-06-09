"""Pydantic models for the agent workflow API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StartWorkflowRequest(BaseModel):
    """Request to start a research workflow for a project."""

    project_id: str = Field(..., description="UUID of the project")
    topic: str = Field(..., min_length=2, max_length=500)
    research_question: str | None = None


class WorkflowStatusResponse(BaseModel):
    """Status of a running or completed workflow."""

    project_id: str
    current_node: str
    completed: bool

    # Search results
    papers_found: int = 0
    source_diagnostics: dict = Field(default_factory=dict)

    # Matrix
    matrix_rows: int = 0
    matrix_status: str = "idle"

    # Gaps
    gaps_count: int = 0
    gap_status: str = "idle"

    # Review
    report_sections: list[dict] = Field(default_factory=list)
    report_status: str = "idle"

    # Citation validation
    citation_valid: bool | None = None
    invalid_citation_ids: list[str] = Field(default_factory=list)

    # Errors
    errors: list[str] = Field(default_factory=list)


class WorkflowStepResponse(BaseModel):
    """Result of a single workflow node."""
    node_name: str
    status: str  # "completed" | "failed" | "skipped"
    output_summary: str
    error: str | None = None
