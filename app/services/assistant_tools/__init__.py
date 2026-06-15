"""Tool registry: name → async handler(db, user, args, runner).

This module is the single import surface the assistant runner uses.
For tools that actually run in a sandbox container, the handler is a
thin wrapper that delegates to ``app.services.sandbox.router``.

Layout:
  * Local fast-path tools live in their own files (search_papers.py,
    save_paper.py, etc.) — they remain unchanged.
  * Sandbox-backed tools live in ``run_python.py``, ``run_shell.py``,
    ``file_io.py``, ``pdf_tools.py``, ``install_packages.py`` — they
    forward to the sandbox router.
"""

from app.services.assistant_tools import (
    create_project,
    detect_conflicts,
    detect_gaps,
    edit_report_section,
    file_io,
    generate_matrix,
    generate_report,
    install_packages,
    pdf_tools,
    qa_search_papers,
    run_python,
    run_shell,
    save_paper,
    save_papers_batch,
    search_papers,
    trigger_normalization,
)

TOOL_REGISTRY = {
    # Local fast path
    "create_project": create_project.handle,
    "search_papers": search_papers.handle,
    "save_paper_to_project": save_paper.handle,
    "save_papers_batch": save_papers_batch.handle,
    "generate_matrix": generate_matrix.handle,
    "trigger_normalization": trigger_normalization.handle,
    "detect_gaps": detect_gaps.handle,
    "detect_conflicts": detect_conflicts.handle,
    "generate_report": generate_report.handle,
    "edit_report_section": edit_report_section.handle,
    "qa_search_papers": qa_search_papers.handle,
    # Sandbox path
    "run_python": run_python.handle,
    "run_shell": run_shell.handle,
    "read_file": file_io._read,
    "write_file": file_io._write,
    "list_files": file_io._list,
    "open_pdf_page": pdf_tools.open_page,
    "grep_pdf": pdf_tools.grep,
    "install_packages": install_packages.handle,
}


def get_handler(name: str):
    return TOOL_REGISTRY.get(name)
