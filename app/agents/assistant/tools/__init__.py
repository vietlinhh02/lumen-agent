"""
Assistant tools package.

Provides the toolkit abstraction and registry for LangChain-compatible tools.
Each toolkit groups related tools (e.g., project_tools, paper_tools).

Usage:
    from app.agents.assistant.tools import BaseToolkit, get_all_tools

    # Get all tools from all toolkits
    all_tools = get_all_tools(user_id="user-123", project_id="proj-456")
"""

from __future__ import annotations

# Import all tool modules to trigger toolkit registration
# These imports must happen AFTER BaseToolkit is defined
from app.agents.assistant.tools import (
    conflict_tools,  # noqa: F401
    evidence_tools,  # noqa: F401
    gap_tools,  # noqa: F401
    matrix_tools,  # noqa: F401
    paper_tools,  # noqa: F401
    project_tools,  # noqa: F401
    report_tools,  # noqa: F401
)

# Import everything from base module
from app.agents.assistant.tools.base import (
    BaseToolkit,
    get_all_toolkits,
    get_all_tools,
    register_toolkit,
)

__all__ = [
    "BaseToolkit",
    "register_toolkit",
    "get_all_toolkits",
    "get_all_tools",
]
