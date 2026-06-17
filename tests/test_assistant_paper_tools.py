"""
Tests for assistant paper tools.

Verifies:
- search_papers tool structure
- save_paper_to_project tool structure
- remove_paper_from_project tool structure
- list_project_papers tool structure
- Error handling returns proper error codes
- Tools never raise raw exceptions back to LLM
- Implementation functions with mocked services
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.agents.assistant.tools.paper_tools import (
    _error_result,
    _ok_result,
    search_papers,
    save_paper_to_project,
    remove_paper_from_project,
    list_project_papers,
    _search_papers_impl,
    _save_paper_impl,
    _remove_paper_impl,
    _list_project_papers_impl,
)


class TestOkErrorResults:
    """Tests for result helper functions."""

    def test_ok_result_with_data(self):
        """_ok_result creates correct success dict."""
        result = _ok_result("Success", {"papers": []})
        assert result["ok"] is True
        assert result["message"] == "Success"
        assert "papers" in result["data"]

    def test_error_result_basic(self):
        """_error_result creates correct error dict."""
        result = _error_result("SEARCH_FAILED", "Service unavailable")
        assert result["ok"] is False
        assert result["error_code"] == "SEARCH_FAILED"
        assert result["message"] == "Service unavailable"

    def test_ok_result_without_data(self):
        """_ok_result works without data."""
        result = _ok_result("Success")
        assert result["ok"] is True
        assert "data" not in result

    def test_error_result_with_details(self):
        """Error result includes details when provided."""
        result = _error_result("ERR", "Failed", {"extra": "info"})
        assert result["details"]["extra"] == "info"


class TestLangChainTools:
    """Tests for the LangChain tool decorators."""

    def test_search_papers_tool_callable(self):
        """search_papers is a valid LangChain tool."""
        assert hasattr(search_papers, "invoke")
        assert callable(search_papers.invoke)

    def test_save_paper_tool_callable(self):
        """save_paper_to_project is a valid LangChain tool."""
        assert hasattr(save_paper_to_project, "invoke")
        assert callable(save_paper_to_project.invoke)

    def test_remove_paper_tool_callable(self):
        """remove_paper_from_project is a valid LangChain tool."""
        assert hasattr(remove_paper_from_project, "invoke")
        assert callable(remove_paper_from_project.invoke)

    def test_list_papers_tool_callable(self):
        """list_project_papers is a valid LangChain tool."""
        assert hasattr(list_project_papers, "invoke")
        assert callable(list_project_papers.invoke)

    def test_tools_have_correct_names(self):
        """Tools have expected names."""
        assert search_papers.name == "search_papers"
        assert save_paper_to_project.name == "save_paper_to_project"
        assert remove_paper_from_project.name == "remove_paper_from_project"
        assert list_project_papers.name == "list_project_papers"

    def test_tools_have_schema_with_params(self):
        """Tools have arg schemas describing their parameters."""
        assert hasattr(search_papers, "args")
        assert hasattr(save_paper_to_project, "args")
        assert hasattr(remove_paper_from_project, "args")
        assert hasattr(list_project_papers, "args")

        # search_papers should have query param
        assert "query" in search_papers.args

        # save_paper requires project_id and paper
        save_args = save_paper_to_project.args
        assert "project_id" in save_args
        assert "paper" in save_args

        # remove requires project_id and project_paper_id
        remove_args = remove_paper_from_project.args
        assert "project_id" in remove_args
        assert "project_paper_id" in remove_args

    def test_search_papers_default_limit(self):
        """search_papers has default limit of 20."""
        # Default is set in the function signature
        assert search_papers.args["limit"]["default"] == 20

    def test_search_papers_default_sources(self):
        """search_papers has semantic_scholar as default source."""
        assert search_papers.args["sources"]["default"] == ["semantic_scholar"]

    def test_list_papers_default_status(self):
        """list_project_papers has default status of saved."""
        assert list_project_papers.args["status"]["default"] == "saved"

    def test_tools_have_descriptions(self):
        """Tools have descriptions for LLM."""
        assert hasattr(search_papers, "description")
        assert len(search_papers.description) > 10
        assert hasattr(save_paper_to_project, "description")
        assert len(save_paper_to_project.description) > 10


class TestToolErrorHandling:
    """Tests that tools return error dicts, not raise exceptions."""

    def test_error_results_have_proper_structure(self):
        """Error results have ok=False, error_code, and message."""
        error = _error_result("TEST_CODE", "Test message")
        assert error["ok"] is False
        assert error["error_code"] == "TEST_CODE"
        assert error["message"] == "Test message"

    def test_error_result_allows_details(self):
        """Error results can include details dict."""
        error = _error_result("CODE", "msg", {"key": "val"})
        assert error["details"]["key"] == "val"

    def test_ok_result_structure(self):
        """OK results have ok=True and message."""
        ok = _ok_result("All good", {"data": 123})
        assert ok["ok"] is True
        assert ok["message"] == "All good"
        assert ok["data"]["data"] == 123


@pytest.mark.asyncio
class TestSearchPapersImplementation:
    """Test _search_papers_impl function."""

    async def test_search_papers_success(self):
        """_search_papers_impl returns search results."""
        mock_raw_paper = MagicMock()
        mock_raw_paper.semantic_scholar_id = "ss-123"
        mock_raw_paper.arxiv_id = None
        mock_raw_paper.doi = "10.1234/test"
        mock_raw_paper.title = "Paper One"
        mock_raw_paper.authors = ["Author A"]
        mock_raw_paper.year = 2024
        mock_raw_paper.abstract = "Abstract"
        mock_raw_paper.source_name = "semantic_scholar"
        mock_raw_paper.url = "https://example.com/paper"
        mock_raw_paper.citation_count = 10

        mock_outcome = MagicMock()
        mock_outcome.raw_papers = [mock_raw_paper]
        mock_outcome.response = MagicMock()
        mock_outcome.response.source_diagnostics = []

        with patch("app.services.paper_search.search_and_download", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_outcome

            result = await _search_papers_impl(
                query="RAG medical",
                sources=["semantic_scholar"],
                year_from=2020,
                year_to=None,
                limit=10,
            )

        assert result["ok"] is True
        assert "data" in result
        assert "papers" in result["data"]
        assert len(result["data"]["papers"]) == 1

    async def test_search_papers_timeout(self):
        """_search_papers_impl handles timeout."""
        import asyncio

        with patch("app.services.paper_search.search_and_download", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = asyncio.TimeoutError()

            result = await _search_papers_impl(
                query="test",
                sources=["semantic_scholar"],
                year_from=None,
                year_to=None,
                limit=10,
            )

        assert result["ok"] is False
        assert result["error_code"] == "SEARCH_TIMEOUT"

    async def test_search_papers_service_exception(self):
        """_search_papers_impl handles service exceptions."""
        with patch("app.services.paper_search.search_and_download", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = Exception("Search failed")

            result = await _search_papers_impl(
                query="test",
                sources=["semantic_scholar"],
                year_from=None,
                year_to=None,
                limit=10,
            )

        assert result["ok"] is False
        assert result["error_code"] == "SEARCH_FAILED"


@pytest.mark.asyncio
class TestSavePaperImplementation:
    """Test _save_paper_impl function."""

    async def test_save_paper_unauthorized(self):
        """_save_paper_impl returns error when user is None."""
        result = await _save_paper_impl(
            project_id=str(uuid4()),
            paper={"id": "p1", "title": "Test"},
            user_id=None,
            user=None,
        )
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_save_paper_invalid_project(self):
        """_save_paper_impl returns error for invalid project ID."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _save_paper_impl(
            project_id="invalid-uuid",
            paper={"id": "p1", "title": "Test"},
            user_id=str(mock_user.id),
            user=mock_user,
        )
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"

    async def test_save_paper_success(self):
        """_save_paper_impl saves paper successfully."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_result = MagicMock()
        mock_result.id = uuid4()
        mock_result.title = "Test Paper"
        mock_result.status = "saved"

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.save_paper_to_project", new_callable=AsyncMock) as mock_save:
                mock_save.return_value = mock_result

                result = await _save_paper_impl(
                    project_id=str(project_id),
                    paper={"id": "p1", "title": "Test Paper"},
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is True
        assert "data" in result


@pytest.mark.asyncio
class TestRemovePaperImplementation:
    """Test _remove_paper_impl function."""

    async def test_remove_paper_unauthorized(self):
        """_remove_paper_impl returns error when user is None."""
        result = await _remove_paper_impl(
            project_id=str(uuid4()),
            project_paper_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_remove_paper_invalid_project(self):
        """_remove_paper_impl returns error for invalid project ID."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _remove_paper_impl(
            project_id="invalid-uuid",
            project_paper_id=str(uuid4()),
            user_id=str(mock_user.id),
            user=mock_user,
        )
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_ID"


@pytest.mark.asyncio
class TestListPapersImplementation:
    """Test _list_project_papers_impl function."""

    async def test_list_papers_unauthorized(self):
        """_list_project_papers_impl returns error when user is None."""
        result = await _list_project_papers_impl(
            project_id=str(uuid4()),
            status="saved",
            user_id=None,
            user=None,
        )
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_list_papers_invalid_project(self):
        """_list_project_papers_impl returns error for invalid project ID."""
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _list_project_papers_impl(
            project_id="invalid-uuid",
            status="saved",
            user_id=str(mock_user.id),
            user=mock_user,
        )
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"

    async def test_list_papers_success(self):
        """_list_project_papers_impl returns papers list."""
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_paper = MagicMock()
        mock_paper.id = uuid4()
        mock_paper.paper_id = uuid4()
        mock_paper.title = "Paper One"
        mock_paper.authors = ["Author"]
        mock_paper.year = 2024
        mock_paper.doi = "10.1234/test"
        mock_paper.arxiv_id = None
        mock_paper.abstract = None
        mock_paper.status = "saved"
        mock_paper.relevance_label = None
        mock_paper.saved_at = None

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            with patch("app.services.project.list_project_papers", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = [mock_paper]

                result = await _list_project_papers_impl(
                    project_id=str(project_id),
                    status="saved",
                    user_id=str(mock_user.id),
                    user=mock_user,
                )

        assert result["ok"] is True
        assert "data" in result
        assert "papers" in result["data"]
