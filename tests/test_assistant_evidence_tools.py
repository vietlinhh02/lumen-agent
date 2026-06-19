"""Tests for assistant evidence tools."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest


class TestEvidenceToolsSchemas:
    """Test that schema classes are properly defined."""

    def test_retrieve_evidence_input_schema(self):
        """Test RetrieveEvidenceInput schema validation."""
        from app.agents.assistant.tools.schemas import RetrieveEvidenceInput
        
        inp = RetrieveEvidenceInput(
            project_id="123e4567-e89b-12d3-a456-426614174000",
            query="What methods were used?",
        )
        assert inp.project_id == "123e4567-e89b-12d3-a456-426614174000"
        assert inp.query == "What methods were used?"
        assert inp.k == 8  # default
        assert inp.content_types is None  # default
        
        # With all params
        inp_full = RetrieveEvidenceInput(
            project_id="123e4567-e89b-12d3-a456-426614174000",
            query="What datasets?",
            k=20,
            content_types=["abstract", "method"],
        )
        assert inp_full.k == 20
        assert len(inp_full.content_types) == 2

    def test_retrieve_evidence_input_validation(self):
        """Test that query must be non-empty."""
        from pydantic import ValidationError

        from app.agents.assistant.tools.schemas import RetrieveEvidenceInput
        
        with pytest.raises(ValidationError):
            RetrieveEvidenceInput(
                project_id="123e4567-e89b-12d3-a456-426614174000",
                query="",  # Empty query should fail
            )

    def test_retrieve_evidence_input_k_bounds(self):
        """Test k parameter bounds."""
        from pydantic import ValidationError

        from app.agents.assistant.tools.schemas import RetrieveEvidenceInput
        
        # Valid bounds
        inp = RetrieveEvidenceInput(
            project_id="123e4567-e89b-12d3-a456-426614174000",
            query="test",
            k=1,
        )
        assert inp.k == 1
        
        inp = RetrieveEvidenceInput(
            project_id="123e4567-e89b-12d3-a456-426614174000",
            query="test",
            k=50,
        )
        assert inp.k == 50
        
        # Out of bounds
        with pytest.raises(ValidationError):
            RetrieveEvidenceInput(
                project_id="123e4567-e89b-12d3-a456-426614174000",
                query="test",
                k=0,  # Below minimum
            )
        
        with pytest.raises(ValidationError):
            RetrieveEvidenceInput(
                project_id="123e4567-e89b-12d3-a456-426614174000",
                query="test",
                k=100,  # Above maximum
            )

    def test_evidence_chunk_schema(self):
        """Test EvidenceChunk schema."""
        from app.agents.assistant.tools.schemas import EvidenceChunk
        
        chunk = EvidenceChunk(
            chunk_id="123e4567-e89b-12d3-a456-426614174000",
            content="This is the evidence text.",
            project_paper_id="223e4567-e89b-12d3-a456-426614174000",
            score=0.85,
            content_type="method",
        )
        assert chunk.score == 0.85
        assert chunk.content_type == "method"

    def test_retrieve_evidence_output_schema(self):
        """Test RetrieveEvidenceOutput schema."""
        from app.agents.assistant.tools.schemas import EvidenceChunk, RetrieveEvidenceOutput
        
        chunk = EvidenceChunk(
            chunk_id="123e4567-e89b-12d3-a456-426614174000",
            content="Evidence text",
            project_paper_id="223e4567-e89b-12d3-a456-426614174000",
            score=0.9,
        )
        
        out = RetrieveEvidenceOutput(
            chunks=[chunk],
            query="What methods?",
        )
        assert len(out.chunks) == 1
        assert out.query == "What methods?"


class TestEvidenceToolsHelpers:
    """Test helper functions in evidence tools."""

    def test_ok_result_format(self):
        """Test _ok_result helper produces correct format."""
        from app.agents.assistant.tools.evidence_tools import _ok_result
        
        result = _ok_result("Test message", {"key": "value"})
        assert result["ok"] is True
        assert result["message"] == "Test message"

    def test_error_result_format(self):
        """Test _error_result helper produces correct format."""
        from app.agents.assistant.tools.evidence_tools import _error_result
        
        result = _error_result("EVIDENCE_ERROR", "Error message")
        assert result["ok"] is False
        assert result["error_code"] == "EVIDENCE_ERROR"


@pytest.mark.asyncio
class TestRetrieveEvidenceImplementation:
    """Test evidence retrieval implementation."""

    async def test_retrieve_evidence_unauthorized(self):
        """Test that unauthenticated requests are rejected."""
        from app.agents.assistant.tools.evidence_tools import _retrieve_evidence_impl
        
        result = await _retrieve_evidence_impl(
            project_id=str(uuid4()),
            query="test query",
            k=8,
            content_types=None,
            user_id=None,
            user=None,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "UNAUTHORIZED"

    async def test_retrieve_evidence_invalid_project_id(self):
        """Test that invalid project ID returns error."""
        from app.agents.assistant.tools.evidence_tools import _retrieve_evidence_impl
        
        mock_user = MagicMock()
        mock_user.id = uuid4()
        
        result = await _retrieve_evidence_impl(
            project_id="invalid-uuid",
            query="test query",
            k=8,
            content_types=None,
            user_id=str(mock_user.id),
            user=mock_user,
        )
        
        assert result["ok"] is False
        assert result["error_code"] == "INVALID_PROJECT_ID"


class TestEvidenceToolDecorators:
    """Test that LangChain tools are properly decorated."""

    def test_retrieve_evidence_tool_exists(self):
        """Test that retrieve_evidence is a valid LangChain tool."""
        from app.agents.assistant.tools.evidence_tools import retrieve_evidence
        
        assert hasattr(retrieve_evidence, "name")
        assert retrieve_evidence.name == "retrieve_evidence"

    def test_retrieve_evidence_tool_has_description(self):
        """Test that retrieve_evidence tool has a description."""
        from app.agents.assistant.tools.evidence_tools import retrieve_evidence

        # The tool should have a description attribute explaining its purpose
        assert hasattr(retrieve_evidence, "description")
        assert len(retrieve_evidence.description) > 50  # Reasonable length
