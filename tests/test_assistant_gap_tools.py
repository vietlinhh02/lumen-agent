"""Tests for assistant gap tools."""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4


class TestGapToolsSchemas:
    """Test that schema classes are properly defined."""

    def test_detect_gaps_input_schema(self):
        """Test DetectGapsInput schema validation."""
        from app.agents.assistant.tools.schemas import DetectGapsInput
        
        inp = DetectGapsInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id == "123e4567-e89b-12d3-a456-426614174000"

    def test_detect_gaps_output_schema(self):
        """Test DetectGapsOutput schema."""
        from app.agents.assistant.tools.schemas import DetectGapsOutput
        
        out = DetectGapsOutput(status="completed", gaps_found=5)
        assert out.status == "completed"
        assert out.gaps_found == 5

    def test_gap_schema(self):
        """Test GapSchema."""
        from app.agents.assistant.tools.schemas import GapSchema
        
        gap = GapSchema(
            gap_id="123e4567-e89b-12d3-a456-426614174000",
            description="Test gap description",
            severity="high",
            evidence=["paper1", "paper2"],
        )
        assert gap.severity == "high"
        assert len(gap.evidence) == 2

    def test_list_gaps_input_schema(self):
        """Test ListGapsInput schema."""
        from app.agents.assistant.tools.schemas import ListGapsInput
        
        inp = ListGapsInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id is not None

    def test_delete_gap_schemas(self):
        """Test DeleteGap input/output schemas."""
        from app.agents.assistant.tools.schemas import DeleteGapInput, DeleteGapOutput
        
        inp = DeleteGapInput(gap_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.gap_id == "123e4567-e89b-12d3-a456-426614174000"
        
        out = DeleteGapOutput(success=True)
        assert out.success is True


class TestGapToolsHelpers:
    """Test helper functions in gap tools."""

    def test_ok_result_format(self):
        """Test _ok_result helper produces correct format."""
        from app.agents.assistant.tools.gap_tools import _ok_result
        
        result = _ok_result("Test message", {"key": "value"})
        assert result["ok"] is True
        assert result["message"] == "Test message"

    def test_error_result_format(self):
        """Test _error_result helper produces correct format."""
        from app.agents.assistant.tools.gap_tools import _error_result
        
        result = _error_result("GAP_ERROR", "Error message")
        assert result["ok"] is False
        assert result["error_code"] == "GAP_ERROR"


@pytest.mark.asyncio
class TestDetectGapsImplementation:
    """Test gap detection implementation."""

    async def test_detect_gaps_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.gap_tools import _detect_gaps_impl
        
        result = await _detect_gaps_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_detect_gaps_invalid_project_id(self):
        """Test that invalid project ID returns error."""
        from app.agents.assistant.tools.gap_tools import _detect_gaps_impl
        
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        result = await _detect_gaps_impl(
            project_id="invalid-uuid",
            user_id=str(mock_user.id),
            user=mock_user,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"


@pytest.mark.asyncio
class TestListGapsImplementation:
    """Test gap listing implementation."""

    async def test_list_gaps_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.gap_tools import _list_gaps_impl
        
        result = await _list_gaps_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
class TestDeleteGapImplementation:
    """Test gap deletion implementation."""

    async def test_delete_gap_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.gap_tools import _delete_gap_impl
        
        result = await _delete_gap_impl(
            gap_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_delete_gap_invalid_id(self):
        """Test that invalid gap ID returns error."""
        from app.agents.assistant.tools.gap_tools import _delete_gap_impl
        
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        result = await _delete_gap_impl(
            gap_id="invalid-uuid",
            user_id=str(mock_user.id),
            user=mock_user,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_GAP_ID"


class TestGapToolDecorators:
    """Test that LangChain tools are properly decorated."""

    def test_detect_research_gaps_tool_exists(self):
        """Test that detect_research_gaps is a valid LangChain tool."""
        from app.agents.assistant.tools.gap_tools import detect_research_gaps
        
        assert hasattr(detect_research_gaps, "name")
        assert detect_research_gaps.name == "detect_research_gaps"

    def test_list_gaps_tool_exists(self):
        """Test that list_gaps is a valid LangChain tool."""
        from app.agents.assistant.tools.gap_tools import list_gaps
        
        assert hasattr(list_gaps, "name")
        assert list_gaps.name == "list_gaps"

    def test_delete_gap_tool_exists(self):
        """Test that delete_gap is a valid LangChain tool."""
        from app.agents.assistant.tools.gap_tools import delete_gap
        
        assert hasattr(delete_gap, "name")
        assert delete_gap.name == "delete_gap"
