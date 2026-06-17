"""
Project tools for the Assistant.

Provides tools for listing, getting, creating projects and asking user clarifications.

Use these when:
- The user wants to see their projects
- The user wants to create a new project
- The user is unsure which project to use and needs to be prompted
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from app.agents.assistant.tools.context import get_project_id, get_user, get_user_id
from app.agents.assistant.tools.schemas import (
    AskUserClarificationInput,
    AskUserClarificationOutput,
    CreateProjectInput,
    CreateProjectOutput,
    GetProjectInput,
    GetProjectOutput,
    ListProjectsInput,
    ListProjectsOutput,
    ProjectDetail,
    ProjectSummary,
    ToolResult,
)
from app.db.models import User
from app.schemas.project import ProjectCreate

if TYPE_CHECKING:
    from uuid import UUID


def _ok_result(message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a success result dict (not a Pydantic model, to avoid serialization issues)."""
    result = {"ok": True, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _error_result(error_code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create an error result dict that the LLM can reason about."""
    result = {"ok": False, "error_code": error_code, "message": message}
    if details is not None:
        result["details"] = details
    return result


def _tool_error(error_code: str, message: str) -> ToolResult:
    """Create a ToolResult with error."""
    return ToolResult(ok=False, error_code=error_code, message=message)


# ── Tool Implementations ────────────────────────────────────────────────────


async def _list_projects_impl(
    user_id: Optional[str],
    user: Optional[User],
) -> Dict[str, Any]:
    """
    List all projects for the current user.

    Returns:
        Dict with projects list or error.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")

    try:
        from app.db.session import async_session_factory
        from app.services.project import list_projects

        async with async_session_factory() as db:
            project_responses = await list_projects(db, user)

        projects = [
            ProjectSummary(
                id=str(p.id),
                name=p.title,
                topic=p.topic,
            ).model_dump()
            for p in project_responses
        ]

        return _ok_result(
            f"Found {len(projects)} projects",
            {"projects": projects}
        )
    except Exception as exc:
        return _error_result("LIST_PROJECTS_FAILED", str(exc))


async def _get_project_impl(
    project_id: str,
    user_id: Optional[str],
    user: Optional[User],
) -> Dict[str, Any]:
    """
    Get full project details by ID.

    Args:
        project_id: The project UUID string.

    Returns:
        Dict with project details or error.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")

    try:
        from uuid import UUID as PyUUID

        from app.db.session import async_session_factory
        from app.services.project import get_project

        pid = PyUUID(project_id)
        async with async_session_factory() as db:
            project = await get_project(db, user, pid)

        if project is None:
            return _error_result("PROJECT_NOT_FOUND", f"Project {project_id} not found or access denied")

        detail = ProjectDetail(
            id=str(project.id),
            name=project.title,
            topic=project.topic,
            research_question=project.research_question,
            created_at=project.created_at,
            updated_at=project.updated_at,
            paper_count=project.paper_count,
        ).model_dump()

        return _ok_result(f"Project: {project.title}", {"project": detail})
    except ValueError:
        return _error_result("INVALID_PROJECT_ID", f"Invalid project ID format: {project_id}")
    except Exception as exc:
        return _error_result("GET_PROJECT_FAILED", str(exc))


async def _create_project_impl(
    name: str,
    topic: str,
    research_question: Optional[str],
    user_id: Optional[str],
    user: Optional[User],
) -> Dict[str, Any]:
    """
    Create a new project.

    Args:
        name: Project name (title).
        topic: Research topic.
        research_question: Optional research question.

    Returns:
        Dict with new project_id and deep link or error.
    """
    if not user:
        return _error_result("UNAUTHORIZED", "User not authenticated")

    try:
        from app.db.session import async_session_factory
        from app.services.project import create_project

        data = ProjectCreate(
            title=name,
            topic=topic,
            research_question=research_question,
        )

        async with async_session_factory() as db:
            project = await create_project(db, user, data)

        return _ok_result(
            f"Created project: {project.title}",
            {
                "project_id": str(project.id),
                "name": project.title,
                "deep_link": f"/projects/{project.id}",
            }
        )
    except Exception as exc:
        return _error_result("CREATE_PROJECT_FAILED", str(exc))


# ── LangChain Tools ─────────────────────────────────────────────────────────


@tool
def list_projects(
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List all projects for the current user.

    Use this when the user asks to see their projects or wants to select a project.

    Returns:
        A list of project summaries with id, name, and topic.

    Args:
        user_id: (Optional) The user ID. If not provided, retrieved from context.
    """
    # Note: This is a sync wrapper. The actual implementation is async.
    # In the execution agent, we use asyncio.run() or call the async version directly.
    user = get_user()
    uid = user_id or get_user_id()

    # Run sync for LangChain compatibility
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # If we're already in an async context, create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _list_projects_impl(uid, user))
            return future.result()
    except RuntimeError:
        # No running event loop
        return asyncio.run(_list_projects_impl(uid, user))


@tool
def get_project(
    project_id: str,
) -> Dict[str, Any]:
    """
    Get full project details by ID.

    Use this when the user specifies a project ID or when you need to verify
    a project exists and get its metadata.

    Returns:
        Full project details including metadata.

    Args:
        project_id: The project UUID string.
    """
    user = get_user()
    uid = get_user_id()

    import asyncio
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _get_project_impl(project_id, uid, user))
            return future.result()
    except RuntimeError:
        return asyncio.run(_get_project_impl(project_id, uid, user))


@tool
def create_project(
    name: str,
    topic: str,
    research_question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new research project.

    Use this when the user wants to create a new project. Provide a clear name
    and topic. The research_question is optional but recommended.

    Returns:
        New project_id and a deep link to the project.

    Args:
        name: Project name/title.
        topic: Research topic description.
        research_question: Optional research question.
    """
    user = get_user()
    uid = get_user_id()

    import asyncio
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _create_project_impl(name, topic, research_question, uid, user))
            return future.result()
    except RuntimeError:
        return asyncio.run(_create_project_impl(name, topic, research_question, uid, user))


@tool
def ask_user_clarification(
    question: str,
    options: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Ask the user a clarification question and wait for their response.

    Use this when the user's intent is ambiguous and you need them to clarify:
    - Which project to use (if multiple exist or none specified)
    - Which papers to include
    - Any other decision that requires user input

    This tool emits a WaitEvent and pauses the executor until the user responds.

    Returns:
        A dict with status 'waiting' and the question.

    Args:
        question: The question to ask the user.
        options: Optional list of multiple choice options.
    """
    # This tool doesn't actually wait - it returns a signal that the
    # execution agent interprets as a WaitEvent
    return {
        "ok": True,
        "status": "waiting",
        "question": question,
        "options": options,
        "message": "Waiting for user response",
    }
