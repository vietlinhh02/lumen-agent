"""
Pydantic input/output schemas for all assistant tools.

These schemas define the contract for tool inputs and outputs,
providing validation, documentation, and type safety.

One module = one toolkit (filled in Tasks 4-5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Common / Shared schemas
# =============================================================================


class ToolResult(BaseModel):
    """Standard tool result wrapper."""

    ok: bool = Field(..., description="Whether the tool succeeded")
    error_code: Optional[str] = Field(
        default=None, description="Error code if failed"
    )
    message: str = Field(..., description="Result message or error details")
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional result data"
    )


class PaperSchema(BaseModel):
    """Normalized paper representation across sources."""

    paper_id: str = Field(..., description="Unique paper identifier")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(default_factory=list, description="Author names")
    year: Optional[int] = Field(default=None, description="Publication year")
    doi: Optional[str] = Field(default=None, description="DOI")
    abstract: Optional[str] = Field(default=None, description="Abstract text")
    source: str = Field(..., description="Paper source (e.g., semantic_scholar)")
    url: Optional[str] = Field(default=None, description="Paper URL")
    citation_count: Optional[int] = Field(
        default=None, description="Number of citations"
    )


class ProjectSummary(BaseModel):
    """Lightweight project summary."""

    id: str = Field(..., description="Project ID")
    name: str = Field(..., description="Project name")
    topic: str = Field(..., description="Research topic")


class ProjectDetail(ProjectSummary):
    """Full project detail."""

    research_question: Optional[str] = Field(
        default=None, description="Research question"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    paper_count: int = Field(default=0, description="Number of saved papers")


# =============================================================================
# Project Tool schemas
# =============================================================================


class ListProjectsInput(BaseModel):
    """Input for list_projects tool."""

    pass  # No input needed - returns all projects for current user


class ListProjectsOutput(BaseModel):
    """Output from list_projects tool."""

    projects: List[ProjectSummary] = Field(
        default_factory=list, description="List of projects"
    )


class GetProjectInput(BaseModel):
    """Input for get_project tool."""

    project_id: str = Field(..., description="Project ID to retrieve")


class GetProjectOutput(BaseModel):
    """Output from get_project tool."""

    project: ProjectDetail = Field(..., description="Project details")


class CreateProjectInput(BaseModel):
    """Input for create_project tool."""

    name: str = Field(..., description="Project name", min_length=1, max_length=200)
    topic: str = Field(..., description="Research topic", min_length=1, max_length=500)
    research_question: Optional[str] = Field(
        default=None, description="Optional research question"
    )


class CreateProjectOutput(BaseModel):
    """Output from create_project tool."""

    project_id: str = Field(..., description="New project ID")
    name: str = Field(..., description="Project name")
    deep_link: str = Field(..., description="URL to open the project")


class AskUserClarificationInput(BaseModel):
    """Input for ask_user_clarification tool."""

    question: str = Field(..., description="Question to ask the user")
    options: Optional[List[str]] = Field(
        default=None, description="Multiple choice options"
    )


class AskUserClarificationOutput(BaseModel):
    """Output from ask_user_clarification tool (emits WaitEvent)."""

    status: Literal["waiting"] = Field(
        default="waiting", description="Status indicator"
    )
    question: str = Field(..., description="Question being asked")


# =============================================================================
# Paper Tool schemas
# =============================================================================


class SearchPapersInput(BaseModel):
    """Input for search_papers tool."""

    query: str = Field(..., description="Search query", min_length=1)
    sources: List[str] = Field(
        default=["semantic_scholar"],
        description="Sources to search: semantic_scholar, paperhub",
    )
    year_from: Optional[int] = Field(
        default=None, description="Filter papers from this year"
    )
    year_to: Optional[int] = Field(
        default=None, description="Filter papers until this year"
    )
    limit: int = Field(default=20, description="Max results per source", ge=1, le=100)


class SearchPapersOutput(BaseModel):
    """Output from search_papers tool."""

    papers: List[PaperSchema] = Field(default_factory=list, description="Found papers")
    total_count: int = Field(..., description="Total papers found")
    source_diagnostics: Dict[str, str] = Field(
        default_factory=dict, description="Per-source status messages"
    )


class SavePaperInput(BaseModel):
    """Input for save_paper_to_project tool."""

    project_id: str = Field(..., description="Target project ID")
    paper: PaperSchema = Field(..., description="Paper to save")


class SavePaperOutput(BaseModel):
    """Output from save_paper_to_project tool."""

    project_paper_id: str = Field(..., description="Project-paper association ID")
    status: str = Field(..., description="Save status")
    duplicate: bool = Field(..., description="Whether paper was a duplicate")


class RemovePaperInput(BaseModel):
    """Input for remove_paper_from_project tool."""

    project_id: str = Field(..., description="Project ID")
    project_paper_id: str = Field(..., description="Project-paper ID to remove")


class RemovePaperOutput(BaseModel):
    """Output from remove_paper_from_project tool."""

    success: bool = Field(..., description="Whether removal succeeded")
    message: str = Field(..., description="Result message")


class ListProjectPapersInput(BaseModel):
    """Input for list_project_papers tool."""

    project_id: str = Field(..., description="Project ID")
    status: str = Field(
        default="saved", description="Filter by status: saved, pending, removed"
    )


class ListProjectPapersOutput(BaseModel):
    """Output from list_project_papers tool."""

    papers: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of project papers with metadata",
    )


# =============================================================================
# Matrix Tool schemas
# =============================================================================


class GenerateMatrixInput(BaseModel):
    """Input for generate_matrix tool."""

    project_id: str = Field(..., description="Project ID")


class GenerateMatrixOutput(BaseModel):
    """Output from generate_matrix tool."""

    status: str = Field(..., description="Job status: completed, failed, running")
    rows_created: int = Field(default=0, description="Number of matrix rows created")


class ListMatrixRowsInput(BaseModel):
    """Input for list_matrix_rows tool."""

    project_id: str = Field(..., description="Project ID")
    limit: int = Field(default=200, description="Max rows to return", ge=1, le=500)


class MatrixRow(BaseModel):
    """A single matrix row."""

    row_id: str = Field(..., description="Row ID")
    dimension: str = Field(..., description="Dimension/category")
    cell_content: str = Field(..., description="Cell text content")
    source_paper_id: Optional[str] = Field(
        default=None, description="Supporting paper"
    )


class ListMatrixRowsOutput(BaseModel):
    """Output from list_matrix_rows tool."""

    rows: List[MatrixRow] = Field(default_factory=list, description="Matrix rows")


class UpdateMatrixRowInput(BaseModel):
    """Input for update_matrix_row tool."""

    row_id: str = Field(..., description="Row ID to update")
    field: str = Field(..., description="Field name to update")
    new_value: str = Field(..., description="New value")


class UpdateMatrixRowOutput(BaseModel):
    """Output from update_matrix_row tool."""

    success: bool = Field(..., description="Whether update succeeded")
    row: Optional[MatrixRow] = Field(default=None, description="Updated row")


# =============================================================================
# Gap Tool schemas
# =============================================================================


class DetectGapsInput(BaseModel):
    """Input for detect_research_gaps tool."""

    project_id: str = Field(..., description="Project ID")


class DetectGapsOutput(BaseModel):
    """Output from detect_research_gaps tool."""

    status: str = Field(..., description="Job status")
    gaps_found: int = Field(default=0, description="Number of gaps detected")


class GapSchema(BaseModel):
    """A research gap."""

    gap_id: str = Field(..., description="Gap ID")
    description: str = Field(..., description="Gap description")
    severity: str = Field(..., description="Severity: high, medium, low")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence")


class ListGapsInput(BaseModel):
    """Input for list_gaps tool."""

    project_id: str = Field(..., description="Project ID")


class ListGapsOutput(BaseModel):
    """Output from list_gaps tool."""

    gaps: List[GapSchema] = Field(default_factory=list, description="Detected gaps")


class DeleteGapInput(BaseModel):
    """Input for delete_gap tool."""

    gap_id: str = Field(..., description="Gap ID to delete")


class DeleteGapOutput(BaseModel):
    """Output from delete_gap tool."""

    success: bool = Field(..., description="Whether deletion succeeded")


# =============================================================================
# Conflict Tool schemas
# =============================================================================


class DetectConflictsInput(BaseModel):
    """Input for detect_conflicts tool."""

    project_id: str = Field(..., description="Project ID")


class DetectConflictsOutput(BaseModel):
    """Output from detect_conflicts tool."""

    status: str = Field(..., description="Job status")
    conflicts_found: int = Field(default=0, description="Number of conflicts detected")


class ConflictSchema(BaseModel):
    """A conflict between papers."""

    conflict_id: str = Field(..., description="Conflict ID")
    description: str = Field(..., description="Conflict description")
    paper_ids: List[str] = Field(
        default_factory=list, description="Involved paper IDs"
    )
    severity: str = Field(..., description="Severity: high, medium, low")


class ListConflictsInput(BaseModel):
    """Input for list_conflicts tool."""

    project_id: str = Field(..., description="Project ID")


class ListConflictsOutput(BaseModel):
    """Output from list_conflicts tool."""

    conflicts: List[ConflictSchema] = Field(
        default_factory=list, description="Detected conflicts"
    )


# =============================================================================
# Report Tool schemas
# =============================================================================


class GenerateReportInput(BaseModel):
    """Input for generate_report tool."""

    project_id: str = Field(..., description="Project ID")
    title: Optional[str] = Field(
        default=None, description="Report title (optional)"
    )
    include_gap_section: bool = Field(
        default=True, description="Include research gaps section"
    )
    selected_gap_ids: Optional[List[str]] = Field(
        default=None, description="Specific gaps to include"
    )


class GenerateReportOutput(BaseModel):
    """Output from generate_report tool."""

    report_id: str = Field(..., description="Generated report ID")
    validation_status: str = Field(
        ..., description="Citation validation: valid, invalid, unchecked"
    )
    total_citations: int = Field(default=0, description="Total citations")
    invalid_citations: int = Field(default=0, description="Invalid citations")


class ListReportsInput(BaseModel):
    """Input for list_reports tool."""

    project_id: str = Field(..., description="Project ID")


class ReportSummary(BaseModel):
    """Report summary."""

    report_id: str = Field(..., description="Report ID")
    title: str = Field(..., description="Report title")
    created_at: datetime = Field(..., description="Creation timestamp")
    validation_status: str = Field(..., description="Citation validation status")


class ListReportsOutput(BaseModel):
    """Output from list_reports tool."""

    reports: List[ReportSummary] = Field(default_factory=list, description="Reports")


class GetReportInput(BaseModel):
    """Input for get_report tool."""

    project_id: str = Field(..., description="Project ID")
    report_id: str = Field(..., description="Report ID")


class GetReportOutput(BaseModel):
    """Output from get_report tool."""

    report_id: str = Field(..., description="Report ID")
    title: str = Field(..., description="Report title")
    content: str = Field(..., description="Report markdown content")
    references: List[Dict[str, Any]] = Field(
        default_factory=list, description="Reference list"
    )


class ExportReportInput(BaseModel):
    """Input for export_report_markdown tool."""

    project_id: str = Field(..., description="Project ID")
    report_id: str = Field(..., description="Report ID")


class ExportReportOutput(BaseModel):
    """Output from export_report_markdown tool."""

    markdown: str = Field(..., description="Report as markdown string")


# =============================================================================
# Evidence Tool schemas
# =============================================================================


class RetrieveEvidenceInput(BaseModel):
    """Input for retrieve_evidence tool."""

    project_id: str = Field(..., description="Project ID")
    query: str = Field(..., description="Evidence query", min_length=1)
    k: int = Field(default=8, description="Number of chunks to retrieve", ge=1, le=50)
    content_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by content type: abstract, method, result, conclusion",
    )


class EvidenceChunk(BaseModel):
    """A retrieved evidence chunk."""

    chunk_id: str = Field(..., description="Chunk ID")
    content: str = Field(..., description="Chunk text content")
    project_paper_id: str = Field(..., description="Source project-paper ID")
    score: float = Field(..., description="Relevance score")
    content_type: Optional[str] = Field(default=None, description="Content type")


class RetrieveEvidenceOutput(BaseModel):
    """Output from retrieve_evidence tool."""

    chunks: List[EvidenceChunk] = Field(
        default_factory=list, description="Retrieved evidence chunks"
    )
    query: str = Field(..., description="Original query")


# =============================================================================
# Tool schemas export
# =============================================================================

__all__ = [
    # Common
    "ToolResult",
    "PaperSchema",
    "ProjectSummary",
    "ProjectDetail",
    # Project
    "ListProjectsInput",
    "ListProjectsOutput",
    "GetProjectInput",
    "GetProjectOutput",
    "CreateProjectInput",
    "CreateProjectOutput",
    "AskUserClarificationInput",
    "AskUserClarificationOutput",
    # Paper
    "SearchPapersInput",
    "SearchPapersOutput",
    "SavePaperInput",
    "SavePaperOutput",
    "RemovePaperInput",
    "RemovePaperOutput",
    "ListProjectPapersInput",
    "ListProjectPapersOutput",
    # Matrix
    "GenerateMatrixInput",
    "GenerateMatrixOutput",
    "ListMatrixRowsInput",
    "MatrixRow",
    "ListMatrixRowsOutput",
    "UpdateMatrixRowInput",
    "UpdateMatrixRowOutput",
    # Gap
    "DetectGapsInput",
    "DetectGapsOutput",
    "GapSchema",
    "ListGapsInput",
    "ListGapsOutput",
    "DeleteGapInput",
    "DeleteGapOutput",
    # Conflict
    "DetectConflictsInput",
    "DetectConflictsOutput",
    "ConflictSchema",
    "ListConflictsInput",
    "ListConflictsOutput",
    # Report
    "GenerateReportInput",
    "GenerateReportOutput",
    "ListReportsInput",
    "ReportSummary",
    "ListReportsOutput",
    "GetReportInput",
    "GetReportOutput",
    "ExportReportInput",
    "ExportReportOutput",
    # Evidence
    "RetrieveEvidenceInput",
    "EvidenceChunk",
    "RetrieveEvidenceOutput",
]
