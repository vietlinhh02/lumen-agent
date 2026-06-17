"""Tests for assistant conflict tools."""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4


class TestConflictToolsSchemas:
    """Test that schema classes are properly defined."""

    def test_detect_conflicts_input_schema(self):
        """Test DetectConflictsInput schema validation."""
        from app.agents.assistant.tools.schemas import DetectConflictsInput
        
        inp = DetectConflictsInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id == "123e4567-e89b-12d3-a456-426614174000"

    def test_detect_conflicts_output_schema(self):
        """Test DetectConflictsOutput schema."""
        from app.agents.assistant.tools.schemas import DetectConflictsOutput
        
        out = DetectConflictsOutput(status="completed", conflicts_found=3)
        assert out.status == "completed"
        assert out.conflicts_found == 3

    def test_conflict_schema(self):
        """Test ConflictSchema."""
        from app.agents.assistant.tools.schemas import ConflictSchema
        
        conflict = ConflictSchema(
            conflict_id="123e4567-e89b-12d3-a456-426614174000",
            description="Test conflict description",
            paper_ids=["id1", "id2"],
            severity="medium",
        )
        assert conflict.severity == "medium"
        assert len(conflict.paper_ids) == 2

    def test_list_conflicts_input_schema(self):
        """Test ListConflictsInput schema."""
        from app.agents.assistant.tools.schemas import ListConflictsInput
        
        inp = ListConflictsInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id is not None


class TestConflictToolsHelpers:
    """Test helper functions in conflict tools."""

    def test_ok_result_format(self):
        """Test _ok_result helper produces correct format."""
        from app.agents.assistant.tools.conflict_tools import _ok_result
        
        result = _ok_result("Test message", {"key": "value"})
        assert result["ok"] is True
        assert result["message"] == "Test message"

    def test_error_result_format(self):
        """Test _error_result helper produces correct format."""
        from app.agents.assistant.tools.conflict_tools import _error_result
        
        result = _error_result("CONFLICT_ERROR", "Error message")
        assert result["ok"] is False
        assert result["error_code"] == "CONFLICT_ERROR"


@pytest.mark.asyncio
class TestDetectConflictsImplementation:
    """Test conflict detection implementation."""

    async def test_detect_conflicts_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.conflict_tools import _detect_conflicts_impl
        
        result = await _detect_conflicts_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_detect_conflicts_invalid_project_id(self):
        """Test that invalid project ID returns error."""
        from app.agents.assistant.tools.conflict_tools import _detect_conflicts_impl
        
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        result = await _detect_conflicts_impl(
            project_id="invalid-uuid",
            user_id=str(mock_user.id),
            user=mock_user,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"


@pytest.mark.asyncio
class TestListConflictsImplementation:
    """Test conflict listing implementation."""

    async def test_list_conflicts_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.conflict_tools import _list_conflicts_impl
        
        result = await _list_conflicts_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"


class TestConflictToolDecorators:
    """Test that LangChain tools are properly decorated."""

    def test_detect_conflicts_tool_exists(self):
        """Test that detect_conflicts is a valid LangChain tool."""
        from app.agents.assistant.tools.conflict_tools import detect_conflicts
        
        assert hasattr(detect_conflicts, "name")
        assert detect_conflicts.name == "detect_conflicts"

    def test_list_conflicts_tool_exists(self):
        """Test that list_conflicts is a valid LangChain tool."""
        from app.agents.assistant.tools.conflict_tools import list_conflicts
        
        assert hasattr(list_conflicts, "name")
        assert list_conflicts.name == "list_conflicts"
