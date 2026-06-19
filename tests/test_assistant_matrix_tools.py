"""Tests for assistant matrix tools."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestMatrixToolsSchemas:
    """Test that schema classes are properly defined."""

    def test_generate_matrix_input_schema(self):
        """Test GenerateMatrixInput schema validation."""
        from app.agents.assistant.tools.schemas import GenerateMatrixInput

        # Valid input
        inp = GenerateMatrixInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id == "123e4567-e89b-12d3-a456-426614174000"

    def test_generate_matrix_output_schema(self):
        """Test GenerateMatrixOutput schema."""
        from app.agents.assistant.tools.schemas import GenerateMatrixOutput

        out = GenerateMatrixOutput(status="completed", rows_created=10)
        assert out.status == "completed"
        assert out.rows_created == 10

    def test_list_matrix_rows_input_schema(self):
        """Test ListMatrixRowsInput schema with limit validation."""
        from app.agents.assistant.tools.schemas import ListMatrixRowsInput

        inp = ListMatrixRowsInput(project_id="123e4567-e89b-12d3-a456-426614174000", limit=100)
        assert inp.limit == 100

        # Test limit bounds
        with pytest.raises(ValueError):
            ListMatrixRowsInput(project_id="123e4567-e89b-12d3-a456-426614174000", limit=600)

    def test_matrix_row_schema(self):
        """Test MatrixRow schema."""
        from app.agents.assistant.tools.schemas import MatrixRow

        row = MatrixRow(
            row_id="123e4567-e89b-12d3-a456-426614174000",
            dimension="research_problem",
            cell_content="Test content",
        )
        assert row.dimension == "research_problem"

    def test_update_matrix_row_schemas(self):
        """Test UpdateMatrixRow input/output schemas."""
        from app.agents.assistant.tools.schemas import UpdateMatrixRowInput, UpdateMatrixRowOutput

        inp = UpdateMatrixRowInput(
            row_id="123e4567-e89b-12d3-a456-426614174000",
            field="key_result",
            new_value="New value",
        )
        assert inp.field == "key_result"

        out = UpdateMatrixRowOutput(success=True)
        assert out.success is True


class TestMatrixToolsHelpers:
    """Test helper functions in matrix tools."""

    def test_ok_result_format(self):
        """Test _ok_result helper produces correct format."""
        from app.agents.assistant.tools.matrix_tools import _ok_result

        result = _ok_result("Test message", {"key": "value"})
        assert result["ok"] is True
        assert result["message"] == "Test message"
        assert result["data"] == {"key": "value"}

        # Without data
        result = _ok_result("Test message")
        assert result["ok"] is True
        assert "data" not in result

    def test_error_result_format(self):
        """Test _error_result helper produces correct format."""
        from app.agents.assistant.tools.matrix_tools import _error_result

        result = _error_result("TEST_ERROR", "Error message", {"detail": "info"})
        assert result["ok"] is False
        assert result["error_code"] == "TEST_ERROR"
        assert result["message"] == "Error message"
        assert result["details"] == {"detail": "info"}

        # Without details
        result = _error_result("TEST_ERROR", "Error message")
        assert "details" not in result


@pytest.mark.asyncio
class TestGenerateMatrixImplementation:
    """Test matrix generation implementation."""

    async def test_generate_matrix_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.matrix_tools import _generate_matrix_impl

        result = await _generate_matrix_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )

        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_generate_matrix_invalid_project_id(self):
        """Test that invalid project ID returns error."""
        from app.agents.assistant.tools.matrix_tools import _generate_matrix_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _generate_matrix_impl(
            project_id="invalid-uuid",
            user_id=str(mock_user.id),
            user=mock_user,
        )

        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"

    async def test_generate_matrix_project_not_found(self):
        """Test that non-existent project returns error."""
        from app.agents.assistant.tools.matrix_tools import _generate_matrix_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            # Mock execute to return None (project not found)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await _generate_matrix_impl(
                project_id=str(project_id),
                user_id=str(mock_user.id),
                user=mock_user,
            )

        assert result["ok"] is False
        assert result["error_code"] == "PROJECT_NOT_FOUND"

    async def test_generate_matrix_no_papers(self):
        """Test that project with no saved papers returns error."""
        from app.agents.assistant.tools.matrix_tools import _generate_matrix_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            # First call returns project, second returns 0 for count
            mock_result1 = MagicMock()
            mock_result1.scalar_one_or_none.return_value = mock_project

            mock_result2 = MagicMock()
            mock_result2.scalar.return_value = 0  # No saved papers

            mock_db.execute = AsyncMock(side_effect=[mock_result1, mock_result2])

            result = await _generate_matrix_impl(
                project_id=str(project_id),
                user_id=str(mock_user.id),
                user=mock_user,
            )

        assert result["ok"] is False
        assert result["error_code"] == "NO_PAPERS"

    async def test_generate_matrix_success(self):
        """Test successful matrix generation."""
        from app.agents.assistant.tools.matrix_tools import _generate_matrix_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "pending"

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            # Mock project found and has papers
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.side_effect = [
                mock_project,  # Project found
                5,  # Has 5 saved papers
                mock_job,  # Job created
            ]
            mock_db.execute = AsyncMock(return_value=mock_result)

            # Mock poll to return completed
            with patch("app.agents.assistant.tools.matrix_tools._poll_job", new_callable=AsyncMock) as mock_poll:
                mock_poll.return_value = {
                    "status": "completed",
                    "result": {"created_count": 15},
                    "error": None,
                }

                # Mock the router function
                with patch("app.routers.matrix._run_matrix_job"):
                    result = await _generate_matrix_impl(
                        project_id=str(project_id),
                        user_id=str(mock_user.id),
                        user=mock_user,
                    )

        assert result["ok"] is True
        assert result["data"]["status"] == "completed"


@pytest.mark.asyncio
class TestListMatrixRowsImplementation:
    """Test matrix rows listing implementation."""

    async def test_list_matrix_rows_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.matrix_tools import _list_matrix_rows_impl

        result = await _list_matrix_rows_impl(
            project_id=str(uuid4()),
            limit=100,
            user_id=None,
            user=None,
        )

        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_list_matrix_rows_invalid_project(self):
        """Test that invalid project ID returns error."""
        from app.agents.assistant.tools.matrix_tools import _list_matrix_rows_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _list_matrix_rows_impl(
            project_id="invalid-uuid",
            limit=100,
            user_id=str(mock_user.id),
            user=mock_user,
        )

        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"

    async def test_list_matrix_rows_project_not_found(self):
        """Test project not found returns error."""
        from app.agents.assistant.tools.matrix_tools import _list_matrix_rows_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await _list_matrix_rows_impl(
                project_id=str(project_id),
                limit=100,
                user_id=str(mock_user.id),
                user=mock_user,
            )

        assert result["ok"] is False
        assert result["error_code"] == "PROJECT_NOT_FOUND"

    async def test_list_matrix_rows_success(self):
        """Test successful matrix rows listing."""
        from app.agents.assistant.tools.matrix_tools import _list_matrix_rows_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.id = project_id

        mock_row = MagicMock()
        mock_row.id = uuid4()
        mock_row.research_problem = "Research Problem"
        mock_row.method = "Methodology"
        mock_row.dataset_or_context = None
        mock_row.key_result = "Key Result"
        mock_row.limitation = None
        mock_row.contribution = None
        mock_row.relevance = None
        mock_row.extraction_confidence = None
        mock_row.project_paper_id = None

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_row]

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            # First call returns project, second returns rows
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.side_effect = [
                mock_project,  # Project found
            ]
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_result.scalars.return_value = mock_scalars

            result = await _list_matrix_rows_impl(
                project_id=str(project_id),
                limit=100,
                user_id=str(mock_user.id),
                user=mock_user,
            )

        assert result["ok"] is True
        assert "data" in result
        assert "rows" in result["data"]
        assert len(result["data"]["rows"]) == 1


@pytest.mark.asyncio
class TestUpdateMatrixRowImplementation:
    """Test matrix row update implementation."""

    async def test_update_matrix_row_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.matrix_tools import _update_matrix_row_impl

        result = await _update_matrix_row_impl(
            row_id=str(uuid4()),
            field="key_result",
            new_value="test",
            user_id=None,
            user=None,
        )

        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_update_matrix_row_invalid_field(self):
        """Test that invalid field name returns error."""
        from app.agents.assistant.tools.matrix_tools import _update_matrix_row_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await _update_matrix_row_impl(
            row_id=str(uuid4()),
            field="invalid_field",
            new_value="test",
            user_id=str(mock_user.id),
            user=mock_user,
        )

        assert result["ok"] is False
        assert result["error_code"] == "INVALID_FIELD"

    async def test_update_matrix_row_success(self):
        """Test successful matrix row update."""
        from app.agents.assistant.tools.matrix_tools import _update_matrix_row_impl

        mock_user = MagicMock()
        mock_user.id = uuid4()
        row_id = uuid4()

        mock_row = MagicMock()
        mock_row.id = row_id
        mock_row.research_problem = "Original"

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db

            # Mock row found
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_row
            mock_db.execute = AsyncMock(return_value=mock_result)

            result = await _update_matrix_row_impl(
                row_id=str(row_id),
                field="research_problem",
                new_value="Updated research problem",
                user_id=str(mock_user.id),
                user=mock_user,
            )

        assert result["ok"] is True
        assert result["data"]["success"] is True


@pytest.mark.asyncio
class TestPollJobHelper:
    """Test the _poll_job helper function."""

    async def test_poll_job_completed(self):
        """Test polling a completed job."""
        from app.agents.assistant.tools.matrix_tools import _poll_job

        job_id = uuid4()

        mock_job = MagicMock()
        mock_job.status = "completed"
        mock_job.result = {"rows_created": 10}
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _poll_job(job_id, max_wait=5.0, interval=0.1)

        assert result["status"] == "completed"
        assert result["result"]["rows_created"] == 10

    async def test_poll_job_not_found(self):
        """Test polling a non-existent job."""
        from app.agents.assistant.tools.matrix_tools import _poll_job

        job_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        with patch("app.db.session.async_session_factory") as mock_factory:
            mock_db = AsyncMock()
            mock_db.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_db
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await _poll_job(job_id, max_wait=0.1, interval=0.05)

        assert result["status"] == "failed"
        assert "not found" in result["error"]


class TestMatrixToolDecorators:
    """Test that LangChain tools are properly decorated."""

    def test_generate_matrix_tool_exists(self):
        """Test that generate_matrix is a valid LangChain tool."""
        from app.agents.assistant.tools.matrix_tools import generate_matrix

        assert hasattr(generate_matrix, "name")
        assert generate_matrix.name == "generate_matrix"

    def test_list_matrix_rows_tool_exists(self):
        """Test that list_matrix_rows is a valid LangChain tool."""
        from app.agents.assistant.tools.matrix_tools import list_matrix_rows

        assert hasattr(list_matrix_rows, "name")
        assert list_matrix_rows.name == "list_matrix_rows"

    def test_update_matrix_row_tool_exists(self):
        """Test that update_matrix_row is a valid LangChain tool."""
        from app.agents.assistant.tools.matrix_tools import update_matrix_row

        assert hasattr(update_matrix_row, "name")
        assert update_matrix_row.name == "update_matrix_row"

    def test_tools_have_descriptions(self):
        """Test that tools have descriptions."""
        from app.agents.assistant.tools.matrix_tools import (
            generate_matrix,
            list_matrix_rows,
            update_matrix_row,
        )

        assert hasattr(generate_matrix, "description")
        assert len(generate_matrix.description) > 10
        assert hasattr(list_matrix_rows, "description")
        assert hasattr(update_matrix_row, "description")
