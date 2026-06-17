"""
Tests for assistant project tools.

Verifies:
- list_projects returns project list
- get_project returns project details
- create_project creates and returns new project
- ask_user_clarification returns wait signal
- Error handling returns proper error codes
- Implementation functions with mocked services
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.agents.assistant.tools.project_tools import (
    _error_result,
    _ok_result,
    list_projects,
    get_project,
    create_project,
    ask_user_clarification,
    _list_projects_impl,
    _get_project_impl,
    _create_project_impl,
)


class TestOkErrorResults:
    """Tests for result helper functions."""

    def test_ok_result_with_data(self):
        """_ok_result creates correct success dict."""
        result = _ok_result("Success", {"key": "value"})
        assert result["ok"] is True
        assert result["message"] == "Success"
        assert result["data"]["key"] == "value"

    def test_ok_result_without_data(self):
        """_ok_result works without data."""
        result = _ok_result("Success")
        assert result["ok"] is True
        assert result["message"] == "Success"
        assert "data" not in result

    def test_error_result_basic(self):
        """_error_result creates correct error dict."""
        result = _error_result("TEST_ERROR", "Something failed")
        assert result["ok"] is False
        assert result["error_code"] == "TEST_ERROR"
        assert result["message"] == "Something failed"

    def test_error_result_with_details(self):
        """_error_result includes details when provided."""
        result = _error_result("ERR", "Failed", {"extra": "info"})
        assert result["details"]["extra"] == "info"

    def test_ok_result_with_none_data(self):
        """_ok_result handles None data gracefully."""
        result = _ok_result("Success", None)
        assert result["ok"] is True
        assert "data" not in result

    def test_error_result_with_empty_message(self):
        """_error_result works with empty message."""
        result = _error_result("ERR", "")
        assert result["ok"] is False
        assert result["message"] == ""


class TestLangChainTools:
    """Tests for the LangChain tool decorators."""

    def test_list_projects_tool_callable(self):
        """list_projects is a valid LangChain tool."""
        assert hasattr(list_projects, "invoke")
        assert callable(list_projects.invoke)

    def test_get_project_tool_callable(self):
        """get_project is a valid LangChain tool."""
        assert hasattr(get_project, "invoke")
        assert callable(get_project.invoke)

    def test_create_project_tool_callable(self):
        """create_project is a valid LangChain tool."""
        assert hasattr(create_project, "invoke")
        assert callable(create_project.invoke)

    def test_ask_user_clarification_returns_wait_status(self):
        """ask_user_clarification returns status=waiting."""
        result = ask_user_clarification.invoke({
            "question": "Which project?",
            "options": ["A", "B"],
        })
        assert result["ok"] is True
        assert result["status"] == "waiting"
        assert result["question"] == "Which project?"
        assert result["options"] == ["A", "B"]

    def test_ask_user_clarification_without_options(self):
        """ask_user_clarification works without options."""
        result = ask_user_clarification.invoke({
            "question": "What would you like to do?",
        })
        assert result["ok"] is True
        assert result["status"] == "waiting"
        assert result["options"] is None

    def test_tools_have_name(self):
        """Tools have names for identification."""
        assert list_projects.name == "list_projects"
        assert get_project.name == "get_project"
        assert create_project.name == "create_project"
        assert ask_user_clarification.name == "ask_user_clarification"

    def test_tools_have_schema_with_query_params(self):
        """Tools have arg schemas describing their parameters."""
        # Check that tools have args defined
        assert hasattr(list_projects, "args")
        assert hasattr(get_project, "args")
        assert hasattr(create_project, "args")
        assert hasattr(ask_user_clarification, "args")

        # get_project should require project_id
        assert "project_id" in get_project.args

        # create_project should require name and topic
        args = create_project.args
        assert "name" in args
        assert "topic" in args

    def test_ask_user_clarification_includes_message(self):
        """ask_user_clarification returns a message."""
        result = ask_user_clarification.invoke({
            "question": "Which project should I use?",
        })
        assert "message" in result
        assert result["message"] == "Waiting for user response"

    def test_list_projects_has_description(self):
        """list_projects has a description for LLM."""
        assert hasattr(list_projects, "description")
        assert len(list_projects.description) > 10

    def test_get_project_has_description(self):
        """get_project has a description for LLM."""
        assert hasattr(get_project, "description")
        assert len(get_project.description) > 10

    def test_create_project_has_description(self):
        """create_project has a description for LLM."""
        assert hasattr(create_project, "description")
        assert len(create_project.description) > 10


@pytest.mark.asyncio
class TestListProjectsImplementation:
    """Test _list_projects_impl function."""

    async def test_list_projects_unauthorized(self):
        """_list_projects_impl returns error when user is None."""
        result = await _list_projects_impl(user_id=None, user=None)
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_list_projects_with_mocked_service(self):
        """_list_projects_impl calls service correctly."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        # Mock the service and session
        mock_project = MagicMock()
        mock_project.id = uuid4()
        mock_project.title = "Test Project"
        mock_project.topic = "Testing"

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.list_projects", new_callable=AsyncMock) as mock_list:
                mock_list.return_value = [mock_project]

                result = await _list_projects_impl(
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is True
        assert "data" in result
        assert "projects" in result["data"]

    async def test_list_projects_service_exception(self):
        """_list_projects_impl handles service exceptions."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.list_projects", new_callable=AsyncMock) as mock_list:
                mock_list.side_effect = Exception("Service error")

                result = await _list_projects_impl(
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is False
        assert result["error_code"] == "LIST_PROJECTS_FAILED"


@pytest.mark.asyncio
class TestGetProjectImplementation:
    """Test _get_project_impl function."""

    async def test_get_project_unauthorized(self):
        """_get_project_impl returns error when user is None."""
        result = await _get_project_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_get_project_invalid_uuid(self):
        """_get_project_impl returns error for invalid UUID."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _get_project_impl(
            project_id="invalid-uuid",
            user_id=str(mock_user.id),
            user=mock_user,
        )
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"

    async def test_get_project_not_found(self):
        """_get_project_impl returns error when project not found."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.get_project", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = None

                result = await _get_project_impl(
                    project_id=str(uuid4()),
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is False
        assert result["error_code"] == "PROJECT_NOT_FOUND"

    async def test_get_project_success(self):
        """_get_project_impl returns project details."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.title = "Test Project"
        mock_project.topic = "Testing"
        mock_project.research_question = "What is testing?"
        mock_project.created_at = MagicMock()
        mock_project.updated_at = MagicMock()
        mock_project.paper_count = 5

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.get_project", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_project

                result = await _get_project_impl(
                    project_id=str(project_id),
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is True
        assert "data" in result
        assert "project" in result["data"]


@pytest.mark.asyncio
class TestCreateProjectImplementation:
    """Test _create_project_impl function."""

    async def test_create_project_unauthorized(self):
        """_create_project_impl returns error when user is None."""
        result = await _create_project_impl(
            name="Test",
            topic="Testing",
            research_question=None,
            user_id=None,
            user=None,
        )
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_create_project_success(self):
        """_create_project_impl creates project successfully."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id
        mock_project.title = "New Project"

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.create_project", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = mock_project

                result = await _create_project_impl(
                    name="New Project",
                    topic="Testing",
                    research_question="What is testing?",
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is True
        assert "data" in result
        assert result["data"]["project_id"] == str(project_id)
        assert "deep_link" in result["data"]

    async def test_create_project_service_exception(self):
        """_create_project_impl handles service exceptions."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.create_project", new_callable=AsyncMock) as mock_create:
                mock_create.side_effect = Exception("Creation failed")

                result = await _create_project_impl(
                    name="Test",
                    topic="Testing",
                    research_question=None,
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is False
        assert result["error_code"] == "CREATE_PROJECT_FAILED"
