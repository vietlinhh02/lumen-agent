"""Tests for the Auto-RAG injector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInject:
    """Test the inject() function."""

    @pytest.fixture
    def scratchpad(self):
        """Create a fresh scratchpad."""
        from app.agents.assistant.react.memory import Scratchpad
        return Scratchpad()

    @pytest.mark.asyncio
    async def test_skips_when_no_project_id(self, scratchpad) -> None:
        """inject() returns False when project_id is None."""
        from app.agents.assistant.react.rag_injector import inject

        result = await inject(
            message="Tell me about AI",
            project_id=None,
            scratchpad=scratchpad,
            user_id="user123",
        )

        assert result is False
        assert scratchpad.rag_chunks == []

    @pytest.mark.asyncio
    async def test_skips_when_project_id_empty(self, scratchpad) -> None:
        """inject() returns False when project_id is empty string."""
        from app.agents.assistant.react.rag_injector import inject

        result = await inject(
            message="Tell me about AI",
            project_id="",
            scratchpad=scratchpad,
            user_id="user123",
        )

        assert result is False
        assert scratchpad.rag_chunks == []

    @pytest.mark.asyncio
    async def test_skips_when_project_id_invalid(self, scratchpad) -> None:
        """inject() returns False for invalid UUID format."""
        from app.agents.assistant.react.rag_injector import inject

        result = await inject(
            message="Tell me about AI",
            project_id="not-a-valid-uuid",
            scratchpad=scratchpad,
            user_id="user123",
        )

        assert result is False
        assert scratchpad.rag_chunks == []

    @pytest.mark.asyncio
    async def test_injects_chunks_when_retrieval_succeeds(self, scratchpad) -> None:
        """inject() stores chunks in scratchpad on success."""
        from app.agents.assistant.react.rag_injector import inject
        from app.services.hybrid_retrieval import RetrievedChunk

        # Create mock chunks
        mock_chunks = [
            MagicMock(spec=RetrievedChunk, chunk_text="Chunk 1 content"),
            MagicMock(spec=RetrievedChunk, chunk_text="Chunk 2 content"),
            MagicMock(spec=RetrievedChunk, chunk_text="Chunk 3 content"),
        ]

        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                new_callable=AsyncMock,
                return_value=mock_chunks,
            ):
                result = await inject(
                    message="What about AI in healthcare?",
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                    k=3,
                )

        assert result is True
        assert len(scratchpad.rag_chunks) == 3
        assert scratchpad.rag_chunks[0] == "Chunk 1 content"
        assert scratchpad.rag_chunks[1] == "Chunk 2 content"
        assert scratchpad.rag_chunks[2] == "Chunk 3 content"

    @pytest.mark.asyncio
    async def test_skips_when_no_chunks_retrieved(self, scratchpad) -> None:
        """inject() returns False when retrieval returns empty list."""
        from app.agents.assistant.react.rag_injector import inject

        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                new_callable=AsyncMock,
                return_value=[],  # No chunks
            ):
                result = await inject(
                    message="What about AI?",
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                )

        assert result is False
        assert scratchpad.rag_chunks == []

    @pytest.mark.asyncio
    async def test_returns_false_on_retrieval_error(self, scratchpad) -> None:
        """inject() returns False when retrieval raises an exception."""
        from app.agents.assistant.react.rag_injector import inject

        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Database connection failed"),
            ):
                result = await inject(
                    message="What about AI?",
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                )

        assert result is False
        assert scratchpad.rag_chunks == []

    @pytest.mark.asyncio
    async def test_uses_k_parameter(self, scratchpad) -> None:
        """inject() respects the k parameter."""
        from app.agents.assistant.react.rag_injector import inject

        # Create 5 mock chunks
        mock_chunks = [
            MagicMock(chunk_text=f"Chunk {i} content")
            for i in range(5)
        ]

        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            retrieve_mock = AsyncMock(return_value=mock_chunks)

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                retrieve_mock,
            ):
                await inject(
                    message="Test query",
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                    k=5,
                )

        # Verify limit parameter was passed
        retrieve_mock.assert_called_once()
        call_kwargs = retrieve_mock.call_args.kwargs
        assert call_kwargs["limit"] == 5


class TestInjectForTool:
    """Test the inject_for_tool() function."""

    @pytest.fixture
    def scratchpad(self):
        from app.agents.assistant.react.memory import Scratchpad
        return Scratchpad()

    @pytest.mark.asyncio
    async def test_skips_when_no_project_id(self, scratchpad) -> None:
        """inject_for_tool() returns False when project_id is None."""
        from app.agents.assistant.react.rag_injector import inject_for_tool

        result = await inject_for_tool(
            tool_name="generate_matrix",
            tool_args={"project_id": "some-id"},
            project_id=None,
            scratchpad=scratchpad,
            user_id="user123",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_injects_for_generate_matrix(self, scratchpad) -> None:
        """inject_for_tool() generates correct query for generate_matrix."""
        from app.agents.assistant.react.rag_injector import inject_for_tool

        mock_chunks = [MagicMock(chunk_text="Chunk 1")]
        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            retrieve_mock = AsyncMock(return_value=mock_chunks)

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                retrieve_mock,
            ):
                await inject_for_tool(
                    tool_name="generate_matrix",
                    tool_args={"project_id": project_uuid},
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                )

        # Verify query contains matrix-related terms
        call_kwargs = retrieve_mock.call_args.kwargs
        assert "compare" in call_kwargs["query"].lower()
        assert "papers" in call_kwargs["query"].lower()

    @pytest.mark.asyncio
    async def test_injects_for_detect_research_gaps(self, scratchpad) -> None:
        """inject_for_tool() generates correct query for detect_research_gaps."""
        from app.agents.assistant.react.rag_injector import inject_for_tool

        mock_chunks = [MagicMock(chunk_text="Chunk 1")]
        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            retrieve_mock = AsyncMock(return_value=mock_chunks)

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                retrieve_mock,
            ):
                await inject_for_tool(
                    tool_name="detect_research_gaps",
                    tool_args={},
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                )

        call_kwargs = retrieve_mock.call_args.kwargs
        query = call_kwargs["query"].lower()
        assert "gap" in query or "limitation" in query or "future" in query

    @pytest.mark.asyncio
    async def test_uses_explicit_query_for_generate_report(self, scratchpad) -> None:
        """inject_for_tool() uses explicit query for generate_report."""
        from app.agents.assistant.react.rag_injector import inject_for_tool

        mock_chunks = [MagicMock(chunk_text="Chunk 1")]
        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.db.session.async_session_factory"
        ) as mock_session_factory:
            mock_db = AsyncMock()
            mock_session_factory.return_value.__aenter__.return_value = mock_db

            retrieve_mock = AsyncMock(return_value=mock_chunks)

            with patch(
                "app.services.hybrid_retrieval.retrieve_project_evidence",
                retrieve_mock,
            ):
                await inject_for_tool(
                    tool_name="generate_report",
                    tool_args={"query": "Specific query about transformers"},
                    project_id=project_uuid,
                    scratchpad=scratchpad,
                    user_id="user123",
                )

        call_kwargs = retrieve_mock.call_args.kwargs
        assert "Specific query about transformers" in call_kwargs["query"]

    @pytest.mark.asyncio
    async def test_no_injection_for_unknown_tool(self, scratchpad) -> None:
        """inject_for_tool() returns False for unknown tools."""
        from app.agents.assistant.react.rag_injector import inject_for_tool

        project_uuid = "550e8400-e29b-41d4-a716-446655440000"

        result = await inject_for_tool(
            tool_name="unknown_tool",
            tool_args={},
            project_id=project_uuid,
            scratchpad=scratchpad,
            user_id="user123",
        )

        # Unknown tools should not trigger injection
        assert result is False
        assert scratchpad.rag_chunks == []


class TestBuildQueryForTool:
    """Test the _build_query_for_tool helper."""

    def test_generate_matrix_query(self) -> None:
        """generate_matrix generates comparison query."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "generate_matrix",
            {"project_id": "some-id"},
        )

        assert "compare" in query.lower()
        assert "papers" in query.lower()

    def test_detect_research_gaps_query(self) -> None:
        """detect_research_gaps generates gaps query."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "detect_research_gaps",
            {},
        )

        assert query  # Not empty
        assert any(
            term in query.lower()
            for term in ["gap", "limitation", "future", "unresolved"]
        )

    def test_detect_conflicts_query(self) -> None:
        """detect_conflicts generates conflicts query."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "detect_conflicts",
            {},
        )

        assert query
        assert any(
            term in query.lower()
            for term in ["conflict", "contradict", "disagree"]
        )

    def test_generate_report_with_explicit_query(self) -> None:
        """generate_report uses explicit query if provided."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "generate_report",
            {"query": "My specific research question"},
        )

        assert query == "My specific research question"

    def test_generate_report_without_query(self) -> None:
        """generate_report generates summary query if no explicit query."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "generate_report",
            {},
        )

        assert query
        assert any(
            term in query.lower()
            for term in ["findings", "methodology", "conclusions", "summarize"]
        )

    def test_retrieve_evidence_uses_explicit_query(self) -> None:
        """retrieve_evidence uses its query argument."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "retrieve_evidence",
            {"query": "What datasets were used?"},
        )

        assert query == "What datasets were used?"

    def test_unknown_tool_returns_empty(self) -> None:
        """Unknown tools return empty string."""
        from app.agents.assistant.react.rag_injector import _build_query_for_tool

        query = _build_query_for_tool(
            "some_random_tool",
            {"arg": "value"},
        )

        assert query == ""
