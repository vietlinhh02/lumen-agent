"""
Assistant tools package.

Provides the toolkit abstraction and registry for LangChain-compatible tools.
Each toolkit groups related tools (e.g., project_tools, paper_tools).

Usage:
    from app.agents.assistant.tools import BaseToolkit, get_all_toolkits

    # Get all toolkits for a user/project
    toolkits = get_all_toolkits(user_id="user-123", project_id="proj-456")

    # Get all tools from all toolkits
    all_tools = []
    for toolkit in toolkits:
        all_tools.extend(toolkit.get_tools())
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Optional

# LangChain imports - lazily loaded to avoid hard dependency issues
try:
    from langchain_core.tools import BaseTool
except ImportError:
    BaseTool = Any  # type: ignore

if TYPE_CHECKING:
    from app.db.models import User

# Import all tool modules to ensure they are registered
# These imports trigger the @register_toolkit decorators
from app.agents.assistant.tools import matrix_tools  # noqa: F401
from app.agents.assistant.tools import gap_tools  # noqa: F401
from app.agents.assistant.tools import conflict_tools  # noqa: F401
from app.agents.assistant.tools import report_tools  # noqa: F401
from app.agents.assistant.tools import evidence_tools  # noqa: F401


class BaseToolkit(ABC):
    """
    Abstract base class for assistant toolkits.

    A toolkit groups related tools (e.g., all paper-related tools).
    Subclasses must implement `get_tools()` to return their tool list.

    Example:
        class PaperToolkit(BaseToolkit):
            def get_tools(self) -> list[BaseTool]:
                return [SearchPapersTool(), SavePaperTool()]

        toolkit = PaperToolkit()
        tools = toolkit.get_tools()
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        user: Optional["User"] = None,
    ) -> None:
        """
        Initialize the toolkit with user/project context.

        Args:
            user_id: The authenticated user's ID.
            project_id: The active project ID (may be None if not set).
            user: The User model instance (optional, for richer context).
        """
        self.user_id = user_id
        self.project_id = project_id
        self.user = user

    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """
        Return the list of tools provided by this toolkit.

        Returns:
            List of LangChain BaseTool instances.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement `get_tools()`"
        )

    @property
    def name(self) -> str:
        """Return the toolkit name (derived from class name)."""
        return self.__class__.__name__.replace("Toolkit", "").lower()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(user_id={self.user_id}, project_id={self.project_id})"


# Global toolkit registry for lazy loading
_TOOLKIT_REGISTRY: List[type[BaseToolkit]] = []


def register_toolkit(toolkit_class: type[BaseToolkit]) -> type[BaseToolkit]:
    """
    Register a toolkit class in the global registry.

    Can be used as a decorator:
        @register_toolkit
        class MyToolkit(BaseToolkit):
            ...

    Args:
        toolkit_class: The toolkit class to register.

    Returns:
        The same toolkit class (for decorator chaining).
    """
    _TOOLKIT_REGISTRY.append(toolkit_class)
    return toolkit_class


def get_all_toolkits(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user: Optional["User"] = None,
) -> List[BaseToolkit]:
    """
    Factory function to get all registered toolkits with context.

    Args:
        user_id: The authenticated user's ID.
        project_id: The active project ID.
        user: The User model instance.

    Returns:
        List of instantiated toolkit instances.
    """
    toolkits = []
    for toolkit_class in _TOOLKIT_REGISTRY:
        toolkit = toolkit_class(
            user_id=user_id,
            project_id=project_id,
            user=user,
        )
        toolkits.append(toolkit)
    return toolkits


def get_all_tools(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    user: Optional["User"] = None,
) -> List[BaseTool]:
    """
    Get all tools from all registered toolkits.

    Convenience function that combines get_all_toolkits() and collects
    all tools into a single list.

    Args:
        user_id: The authenticated user's ID.
        project_id: The active project ID.
        user: The User model instance.

    Returns:
        List of all LangChain BaseTool instances from all toolkits.
    """
    all_tools: List[BaseTool] = []
    for toolkit in get_all_toolkits(user_id=user_id, project_id=project_id, user=user):
        all_tools.extend(toolkit.get_tools())
    return all_tools


__all__ = [
    "BaseToolkit",
    "register_toolkit",
    "get_all_toolkits",
    "get_all_tools",
]
