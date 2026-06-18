"""Tests for the FastRouter intent classifier.

Tests both regex pre-filter (fast path, no LLM) and LLM fallback.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.assistant.react.router import (
    FastRouter,
    Intent,
    _regex_classify,
)


# =============================================================================
# Test cases from spec
# =============================================================================

TEST_CASES = [
    # (input_message, expected_intent)
    ("list my projects", Intent.DIRECT_LIST),
    ("find papers about LLM evaluation", Intent.SEARCH),
    ("compare papers in matrix", Intent.ANALYZE),
    ("write me a report", Intent.REPORT),
    ("what does paper X say about Y?", Intent.RAG_QA),
    ("help me", Intent.AMBIGUOUS),
    ("I want something", Intent.AMBIGUOUS),
    ("search papers about X, then generate matrix and detect gaps", Intent.COMPLEX),
]


class TestRegexPreFilter:
    """Test the fast regex pre-filter — no LLM calls involved."""

    @pytest.mark.parametrize("message,expected", TEST_CASES)
    def test_regex_classify_all_cases(self, message: str, expected: Intent) -> None:
        """All 8 test cases should be caught by regex pre-filter."""
        result = _regex_classify(message)
        assert result == expected, f"Message: {message!r} → got {result}, expected {expected}"

    def test_direct_list_patterns(self) -> None:
        """Various DIRECT_LIST patterns."""
        cases = [
            "list my projects",
            "show my projects",
            "get projects",
            "view papers",
            "display my reports",
            "list gaps",
            "show conflicts",
            "get matrices",
            "list results",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.DIRECT_LIST, f"Failed: {msg!r}"

    def test_search_patterns(self) -> None:
        """Various SEARCH patterns."""
        cases = [
            "search papers about X",
            "find papers",
            "look up papers about AI",
            "lookup papers",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.SEARCH, f"Failed: {msg!r}"

    def test_analyze_patterns(self) -> None:
        """Various ANALYZE patterns."""
        cases = [
            "compare papers",
            "analyze papers",
            "evaluate my papers",
            "assess papers in the matrix",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.ANALYZE, f"Failed: {msg!r}"

    def test_report_patterns(self) -> None:
        """Various REPORT patterns."""
        cases = [
            "write me a report",
            "generate a summary",
            "create a literature review",
            "write a summary",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.REPORT, f"Failed: {msg!r}"

    def test_rag_qa_patterns(self) -> None:
        """Various RAG_QA patterns."""
        cases = [
            "what does paper abc123 say about methodology",
            "what does paper my-paper-v2 say about results",
            "what does paper transformer-paper-2024 say about attention",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.RAG_QA, f"Failed: {msg!r}"

    def test_complex_patterns(self) -> None:
        """Various COMPLEX patterns with 'then' or 'and'."""
        cases = [
            "search papers about X, then generate matrix and detect gaps",
            "find papers and then create report",
            "search papers and generate matrix",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.COMPLEX, f"Failed: {msg!r}"

    def test_ambiguous_patterns(self) -> None:
        """Ambiguous short messages."""
        cases = [
            "help me",
            "i want something",
            "do something",
            "help",
            "idk",
            "IDK",
        ]
        for msg in cases:
            assert _regex_classify(msg) == Intent.AMBIGUOUS, f"Failed: {msg!r}"

    def test_no_match_returns_none(self) -> None:
        """Messages not matching any pattern return None (trigger LLM)."""
        cases = [
            "I need help with my research",
            "Can you summarize this paper?",
            "Tell me about transformer architectures",
            "What's the latest in NLP?",
        ]
        for msg in cases:
            result = _regex_classify(msg)
            assert result is None, f"Message {msg!r} should return None, got {result}"


class TestFastRouter:
    """Test FastRouter with mocked LLM."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        """Create a mock OpenAI-compatible client."""
        mock = MagicMock()
        mock.complete = AsyncMock(return_value="COMPLEX")
        return mock

    @pytest.fixture
    def router(self, mock_client: MagicMock) -> FastRouter:
        """Create FastRouter with mocked client."""
        with patch(
            "app.agents.assistant.react.router.OpenAICompatibleAdapter",
            return_value=mock_client,
        ):
            return FastRouter()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("message,expected", TEST_CASES)
    async def test_classify_all_cases_via_regex(
        self, router: FastRouter, message: str, expected: Intent
    ) -> None:
        """All 8 test cases pass through regex without hitting LLM."""
        result = await router.classify(message)
        assert result == expected

    @pytest.mark.asyncio
    async def test_llm_called_for_unmatched_message(self, router: FastRouter, mock_client: MagicMock) -> None:
        """Messages not matched by regex should call LLM."""
        mock_client.complete = AsyncMock(return_value="SEARCH")
        result = await router.classify("Tell me about transformer architectures")
        assert result == Intent.SEARCH
        mock_client.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_returns_valid_intent(self, router: FastRouter, mock_client: MagicMock) -> None:
        """LLM response is parsed and mapped to Intent."""
        mock_client.complete = AsyncMock(return_value="ANALYZE")
        result = await router.classify("some complex message")
        assert result == Intent.ANALYZE

    @pytest.mark.asyncio
    async def test_llm_returns_unknown_intent_falls_back_to_complex(
        self, router: FastRouter, mock_client: MagicMock
    ) -> None:
        """If LLM returns unknown label, fall back to COMPLEX."""
        mock_client.complete = AsyncMock(return_value="UNKNOWN_INTENT")
        result = await router.classify("some complex message")
        assert result == Intent.COMPLEX

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_complex(self, router: FastRouter, mock_client: MagicMock) -> None:
        """On timeout, fall back to COMPLEX."""
        import asyncio

        mock_client.complete = AsyncMock(side_effect=asyncio.TimeoutError("timeout"))
        result = await router.classify("Tell me about transformers")
        assert result == Intent.COMPLEX

    @pytest.mark.asyncio
    async def test_error_falls_back_to_complex(self, router: FastRouter, mock_client: MagicMock) -> None:
        """On any exception, fall back to COMPLEX."""
        mock_client.complete = AsyncMock(side_effect=RuntimeError("API error"))
        result = await router.classify("Tell me about transformers")
        assert result == Intent.COMPLEX

    @pytest.mark.asyncio
    async def test_has_project_context_passed_to_llm(self, router: FastRouter, mock_client: MagicMock) -> None:
        """has_project=True adds context note to prompt."""
        mock_client.complete = AsyncMock(return_value="DIRECT_LIST")
        await router.classify("tell me something", has_project=True)  # unmatched message triggers LLM
        mock_client.complete.assert_called_once()
        call_kwargs = mock_client.complete.call_args.kwargs
        assert "system" in call_kwargs
        assert "[User has an active project context.]" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_no_project_context_passed_to_llm(self, router: FastRouter, mock_client: MagicMock) -> None:
        """has_project=False adds appropriate context note."""
        mock_client.complete = AsyncMock(return_value="SEARCH")
        await router.classify("tell me something", has_project=False)  # unmatched message triggers LLM
        mock_client.complete.assert_called_once()
        call_kwargs = mock_client.complete.call_args.kwargs
        assert "[User has no active project.]" in call_kwargs["system"]
