"""Tests for assistant report tools."""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4


class TestReportToolsSchemas:
    """Test that schema classes are properly defined."""

    def test_generate_report_input_schema(self):
        """Test GenerateReportInput schema validation."""
        from app.agents.assistant.tools.schemas import GenerateReportInput
        
        inp = GenerateReportInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id == "123e4567-e89b-12d3-a456-426614174000"
        assert inp.include_gap_section is True  # default
        assert inp.title is None
        
        # With all params
        inp_full = GenerateReportInput(
            project_id="123e4567-e89b-12d3-a456-426614174000",
            title="My Report",
            include_gap_section=False,
            selected_gap_ids=["gid1", "gid2"],
        )
        assert inp_full.title == "My Report"
        assert inp_full.include_gap_section is False
        assert len(inp_full.selected_gap_ids) == 2

    def test_generate_report_output_schema(self):
        """Test GenerateReportOutput schema."""
        from app.agents.assistant.tools.schemas import GenerateReportOutput
        
        out = GenerateReportOutput(
            report_id="123e4567-e89b-12d3-a456-426614174000",
            validation_status="valid",
            total_citations=25,
            invalid_citations=0,
        )
        assert out.validation_status == "valid"
        assert out.total_citations == 25
        assert out.invalid_citations == 0

    def test_list_reports_input_schema(self):
        """Test ListReportsInput schema."""
        from app.agents.assistant.tools.schemas import ListReportsInput
        
        inp = ListReportsInput(project_id="123e4567-e89b-12d3-a456-426614174000")
        assert inp.project_id is not None

    def test_report_summary_schema(self):
        """Test ReportSummary schema."""
        from datetime import datetime
        from app.agents.assistant.tools.schemas import ReportSummary
        
        summary = ReportSummary(
            report_id="123e4567-e89b-12d3-a456-426614174000",
            title="Test Report",
            created_at=datetime.now(),
            validation_status="valid",
        )
        assert summary.title == "Test Report"
        assert summary.validation_status == "valid"

    def test_get_report_input_schema(self):
        """Test GetReportInput schema."""
        from app.agents.assistant.tools.schemas import GetReportInput
        
        inp = GetReportInput(
            project_id="pid",
            report_id="rid",
        )
        assert inp.project_id == "pid"
        assert inp.report_id == "rid"

    def test_get_report_output_schema(self):
        """Test GetReportOutput schema."""
        from app.agents.assistant.tools.schemas import GetReportOutput
        
        out = GetReportOutput(
            report_id="123e4567-e89b-12d3-a456-426614174000",
            title="Test Report",
            content="# Header\nContent",
            references=[{"id": "1", "title": "Paper 1"}],
        )
        assert out.title == "Test Report"
        assert "Header" in out.content
        assert len(out.references) == 1

    def test_export_report_schemas(self):
        """Test ExportReport input/output schemas."""
        from app.agents.assistant.tools.schemas import ExportReportInput, ExportReportOutput
        
        inp = ExportReportInput(
            project_id="pid",
            report_id="rid",
        )
        assert inp.project_id == "pid"
        
        out = ExportReportOutput(markdown="# Report\nContent here")
        assert "# Report" in out.markdown


class TestReportToolsHelpers:
    """Test helper functions in report tools."""

    def test_ok_result_format(self):
        """Test _ok_result helper produces correct format."""
        from app.agents.assistant.tools.report_tools import _ok_result
        
        result = _ok_result("Test message", {"key": "value"})
        assert result["ok"] is True
        assert result["message"] == "Test message"

    def test_error_result_format(self):
        """Test _error_result helper produces correct format."""
        from app.agents.assistant.tools.report_tools import _error_result
        
        result = _error_result("REPORT_ERROR", "Error message")
        assert result["ok"] is False
        assert result["error_code"] == "REPORT_ERROR"


@pytest.mark.asyncio
class TestGenerateReportImplementation:
    """Test report generation implementation."""

    async def test_generate_report_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.report_tools import _generate_report_impl
        
        result = await _generate_report_impl(
            project_id=str(uuid4()),
            title="Test",
            include_gap_section=True,
            selected_gap_ids=None,
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_generate_report_invalid_project_id(self):
        """Test that invalid project ID returns error."""
        from app.agents.assistant.tools.report_tools import _generate_report_impl
        
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        result = await _generate_report_impl(
            project_id="invalid-uuid",
            title="Test",
            include_gap_section=True,
            selected_gap_ids=None,
            user_id=str(mock_user.id),
            user=mock_user,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"

    async def test_generate_report_invalid_gap_id(self):
        """Test that invalid gap ID in selected_gap_ids returns error."""
        from app.agents.assistant.tools.report_tools import _generate_report_impl
        
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        result = await _generate_report_impl(
            project_id=str(uuid4()),
            title="Test",
            include_gap_section=True,
            selected_gap_ids=["invalid-gap-id"],
            user_id=str(mock_user.id),
            user=mock_user,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_GAP_ID"


@pytest.mark.asyncio
class TestListReportsImplementation:
    """Test report listing implementation."""

    async def test_list_reports_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.report_tools import _list_reports_impl
        
        result = await _list_reports_impl(
            project_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
class TestGetReportImplementation:
    """Test report retrieval implementation."""

    async def test_get_report_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.report_tools import _get_report_impl
        
        result = await _get_report_impl(
            project_id=str(uuid4()),
            report_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
class TestExportReportImplementation:
    """Test report export implementation."""

    async def test_export_report_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.report_tools import _export_report_markdown_impl
        
        result = await _export_report_markdown_impl(
            project_id=str(uuid4()),
            report_id=str(uuid4()),
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"


class TestReportToolDecorators:
    """Test that LangChain tools are properly decorated."""

    def test_generate_report_tool_exists(self):
        """Test that generate_report is a valid LangChain tool."""
        from app.agents.assistant.tools.report_tools import generate_report
        
        assert hasattr(generate_report, "name")
        assert generate_report.name == "generate_report"

    def test_list_reports_tool_exists(self):
        """Test that list_reports is a valid LangChain tool."""
        from app.agents.assistant.tools.report_tools import list_reports
        
        assert hasattr(list_reports, "name")
        assert list_reports.name == "list_reports"

    def test_get_report_tool_exists(self):
        """Test that get_report is a valid LangChain tool."""
        from app.agents.assistant.tools.report_tools import get_report
        
        assert hasattr(get_report, "name")
        assert get_report.name == "get_report"

    def test_export_report_markdown_tool_exists(self):
        """Test that export_report_markdown is a valid LangChain tool."""
        from app.agents.assistant.tools.report_tools import export_report_markdown
        
        assert hasattr(export_report_markdown, "name")
        assert export_report_markdown.name == "export_report_markdown"
