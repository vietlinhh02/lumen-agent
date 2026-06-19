"""
Request-scoped context for assistant tools.

Uses contextvars to store user/project context per-request,
so tools can access authenticated user without explicit threading.

Usage:
    from app.agents.assistant.tools.context import set_user_context, get_user_id

    # At the start of a request (in the router):
    set_user_context(user_id="user-123", project_id="proj-456")

    # Inside a tool (any thread within the same request):
    user_id = get_user_id()  # Returns "user-123"
    project_id = get_project_id()  # Returns "proj-456"

    # Context is cleared automatically when request ends.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from app.db.models import User

# Context variables - these are process-global but values are request-scoped
# Each asyncio task / thread gets its own copy of the context

_user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
_project_id_var: ContextVar[str | None] = ContextVar("project_id", default=None)
_user_var: ContextVar[User | None] = ContextVar("user", default=None)
_tools_var: ContextVar[list[BaseTool] | None] = ContextVar("tools", default=None)


class UserContext:
    """
    Container for user context data.

    Provides a stable interface for accessing context values
    and can be used to restore context later.
    """

    __slots__ = ("user_id", "project_id", "user")

    def __init__(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
        user: User | None = None,
    ) -> None:
        self.user_id = user_id
        self.project_id = project_id
        self.user = user

    def __repr__(self) -> str:
        return f"UserContext(user_id={self.user_id}, project_id={self.project_id})"


def set_user_context(
    user_id: str | None = None,
    project_id: str | None = None,
    user: User | None = None,
    tools: list[BaseTool] | None = None,
) -> None:
    """
    Set user/project context for the current request.

    Call this at the start of each request (in the router) to establish
    the context that tools will use.

    Args:
        user_id: The authenticated user's ID.
        project_id: The active project ID.
        user: The User model instance (optional).
        tools: List of available LangChain tools (optional).
    """
    _user_id_var.set(user_id)
    _project_id_var.set(project_id)
    _user_var.set(user)
    if tools is not None:
        _tools_var.set(tools)


def get_tools() -> list[BaseTool] | None:
    """
    Get the current list of available tools.

    Returns:
        List of BaseTool instances, or None if not set.
    """
    return _tools_var.get()


def get_user_context() -> UserContext:
    """
    Get the current user context.

    Returns:
        UserContext with the current user_id, project_id, and user values.
    """
    return UserContext(
        user_id=_user_id_var.get(),
        project_id=_project_id_var.get(),
        user=_user_var.get(),
    )


def get_user_id() -> str | None:
    """
    Get the current user ID from context.

    Returns:
        The user ID string, or None if not set.
    """
    return _user_id_var.get()


def get_project_id() -> str | None:
    """
    Get the current project ID from context.

    Returns:
        The project ID string, or None if not set.
    """
    return _project_id_var.get()


def get_user() -> User | None:
    """
    Get the current User model instance from context.

    Returns:
        The User instance, or None if not set.
    """
    return _user_var.get()


def clear_user_context() -> None:
    """
    Clear the user context.

    Call this when a request ends to ensure no residual context
    leaks to subsequent requests.
    """
    _user_id_var.set(None)
    _project_id_var.set(None)
    _user_var.set(None)
    _tools_var.set(None)


class UserContextVar:
    """
    Context manager for temporarily setting user context.

    Useful for testing or when you need to run code with a specific
    context without affecting the outer context.

    Example:
        with UserContextVar(user_id="temp-user", project_id="temp-proj"):
            # Inside this block, get_user_id() returns "temp-user"
            do_something()
        # Context is restored after the block
    """

    def __init__(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
        user: User | None = None,
    ) -> None:
        self.user_id = user_id
        self.project_id = project_id
        self.user = user
        self._tokens: tuple = ()

    def __enter__(self) -> UserContextVar:
        # Capture current values BEFORE overwriting - use current if None passed
        current_user_id = self.user_id if self.user_id is not None else _user_id_var.get()
        current_project_id = self.project_id if self.project_id is not None else _project_id_var.get()
        current_user = self.user if self.user is not None else _user_var.get()

        # Save current values and set new ones
        user_id_token = _user_id_var.set(current_user_id)
        project_id_token = _project_id_var.set(current_project_id)
        user_token = _user_var.set(current_user)
        self._tokens = (user_id_token, project_id_token, user_token)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Reset to previous values
        _user_id_var.reset(self._tokens[0])
        _project_id_var.reset(self._tokens[1])
        _user_var.reset(self._tokens[2])


# Re-export UserContext type for convenience
__all__ = [
    "UserContext",
    "set_user_context",
    "get_user_context",
    "get_user_id",
    "get_project_id",
    "get_user",
    "get_tools",
    "clear_user_context",
    "UserContextVar",
] 
