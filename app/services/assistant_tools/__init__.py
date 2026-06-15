"""Tool registry: name → async handler(db, user, args, runner)."""

from app.services.assistant_tools import (
    create_project,
    detect_conflicts,
    detect_gaps,
    edit_report_section,
    generate_matrix,
    generate_report,
    qa_search_papers,
    save_paper,
    save_papers_batch,
    search_papers,
    trigger_normalization,
)

TOOL_REGISTRY = {
    "create_project": create_project.handle,
    "search_papers": search_papers.handle,
    "save_paper_to_project": save_paper.handle,
    "save_papers_batch": save_papers_batch.handle,
    "generate_matrix": generate_matrix.handle,
    "detect_gaps": detect_gaps.handle,
    "detect_conflicts": detect_conflicts.handle,
    "generate_report": generate_report.handle,
    "edit_report_section": edit_report_section.handle,
    "qa_search_papers": qa_search_papers.handle,
    "trigger_normalization": trigger_normalization.handle,
}


def get_handler(name: str):
    return TOOL_REGISTRY.get(name)
