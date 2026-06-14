"""Tool registry: name → async handler(db, user, args, runner)."""

from app.services.assistant_tools import (
    create_project,
    detect_gaps,
    edit_report_section,
    generate_matrix,
    generate_report,
    qa_search_papers,
    save_paper,
    search_papers,
)

TOOL_REGISTRY = {
    "create_project": create_project.handle,
    "search_papers": search_papers.handle,
    "save_paper_to_project": save_paper.handle,
    "generate_matrix": generate_matrix.handle,
    "detect_gaps": detect_gaps.handle,
    "generate_report": generate_report.handle,
    "edit_report_section": edit_report_section.handle,
    "qa_search_papers": qa_search_papers.handle,
}


def get_handler(name: str):
    return TOOL_REGISTRY.get(name)
