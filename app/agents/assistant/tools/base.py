"""
Base classes for assistant toolkits.

Contains BaseToolkit and the registry functions, separated to avoid circular imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

# LangChain imports - lazily loaded to avoid hard dependency issues
try:
    from langchain_core.tools import BaseTool
except ImportError:
    BaseTool = Any  # type: ignore

if TYPE_CHECKING:
    from app.db.models import User


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
        user_id: str | None = None,
        project_id: str | None = None,
        user: User | None = None,
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
    def get_tools(self) -> list[BaseTool]:
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
_TOOLKIT_REGISTRY: list[type[BaseToolkit]] = []


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
    user_id: str | None = None,
    project_id: str | None = None,
    user: User | None = None,
) -> list[BaseToolkit]:
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
    user_id: str | None = None,
    project_id: str | None = None,
    user: User | None = None,
) -> list[BaseTool]:
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
    all_tools: list[BaseTool] = []
    for toolkit in get_all_toolkits(user_id=user_id, project_id=project_id, user=user):
        all_tools.extend(toolkit.get_tools())
    return all_tools


__all__ = [
    "BaseToolkit",
    "register_toolkit",
    "get_all_toolkits",
    "get_all_tools",
]
