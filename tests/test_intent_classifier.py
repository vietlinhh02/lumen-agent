"""Tests for IntentClassifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.assistant.react.intent_classifier import (
    VALID_INTENTS,
    IntentClassifier,
    IntentOutput,
)


class TestIntentClassifierParseResult:
    """Tests for IntentClassifier._parse_result."""

    def setup_method(self) -> None:
        self.mock_provider = MagicMock()
        self.classifier = IntentClassifier(self.mock_provider)

    def test_valid_research_pipeline_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "research_pipeline",
            "confidence": 0.95,
            "reasoning": "User wants full research pipeline",
            "query": "LLM evaluation",
            "project_id": None,
            "topic_hint": "LLM evaluation metrics",
        })
        assert result.intent == "research_pipeline"
        assert result.confidence == 0.95
        assert result.query == "LLM evaluation"
        assert result.topic_hint == "LLM evaluation metrics"

    def test_valid_search_only_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "search_only",
            "confidence": 0.88,
            "reasoning": "User only wants to find papers",
            "query": "AI in healthcare",
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "search_only"
        assert result.query == "AI in healthcare"

    def test_valid_matrix_only_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "matrix_only",
            "confidence": 0.90,
            "reasoning": "User wants to generate matrix",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "matrix_only"

    def test_valid_gap_only_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "gap_only",
            "confidence": 0.85,
            "reasoning": "User wants to detect gaps",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "gap_only"

    def test_valid_report_only_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "report_only",
            "confidence": 0.90,
            "reasoning": "User wants to generate report",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "report_only"

    def test_valid_qa_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "qa",
            "confidence": 0.92,
            "reasoning": "User asks a question about papers",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "qa"

    def test_valid_list_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "list",
            "confidence": 0.95,
            "reasoning": "User wants to list projects",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "list"

    def test_valid_create_project_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "create_project",
            "confidence": 0.90,
            "reasoning": "User wants to create a new project",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "create_project"

    def test_valid_chitchat_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "chitchat",
            "confidence": 0.99,
            "reasoning": "User is greeting",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "chitchat"

    def test_valid_ambiguous_intent(self) -> None:
        result = self.classifier._parse_result({
            "intent": "ambiguous",
            "confidence": 0.30,
            "reasoning": "Intent is unclear",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "ambiguous"

    def test_unknown_intent_falls_back_to_ambiguous(self) -> None:
        result = self.classifier._parse_result({
            "intent": "unknown_intent",
            "confidence": 0.50,
            "reasoning": "Something went wrong",
            "query": None,
            "project_id": None,
            "topic_hint": None,
        })
        assert result.intent == "ambiguous"
        assert result.confidence == 0.0

    def test_malformed_output_falls_back_to_ambiguous(self) -> None:
        result = self.classifier._parse_result({
            "intent": "not_a_valid_intent_field",
        })
        assert result.intent == "ambiguous"
        assert result.confidence == 0.0

    def test_missing_optional_fields_accepted(self) -> None:
        result = self.classifier._parse_result({
            "intent": "research_pipeline",
            "confidence": 0.8,
            "reasoning": "User wants to research",
        })
        assert result.intent == "research_pipeline"
        assert result.query is None
        assert result.project_id is None
        assert result.topic_hint is None


class TestIntentOutputModel:
    """Tests for IntentOutput Pydantic model validation."""

    def test_valid_intent_output(self) -> None:
        output = IntentOutput(
            intent="research_pipeline",
            confidence=0.95,
            reasoning="User wants to research LLM evaluation",
            query="LLM evaluation",
            project_id=None,
            topic_hint="LLM evaluation methods",
        )
        assert output.intent == "research_pipeline"
        assert output.confidence == 0.95

    def test_confidence_must_be_0_to_1(self) -> None:
        with pytest.raises(ValueError):  # Pydantic validation error
            IntentOutput(
                intent="research_pipeline",
                confidence=1.5,  # Invalid: > 1.0
                reasoning="test",
            )

    def test_all_valid_intents_accepted(self) -> None:
        for intent in VALID_INTENTS:
            output = IntentOutput(
                intent=intent,
                confidence=0.5,
                reasoning="test",
            )
            assert output.intent == intent


class TestIntentClassifierBuildUserMessage:
    """Tests for _build_user_message."""

    def setup_method(self) -> None:
        self.mock_provider = MagicMock()
        self.classifier = IntentClassifier(self.mock_provider)

    def test_message_only(self) -> None:
        msg = self.classifier._build_user_message(
            "do research on AI", project_context=None
        )
        assert "User message: do research on AI" in msg
        assert "Project context" not in msg

    def test_message_with_project_context(self) -> None:
        ctx = {
            "project_name": "My Project",
            "topic": "LLM evaluation",
            "research_question": "How to evaluate LLMs?",
        }
        msg = self.classifier._build_user_message("do research on AI", ctx)
        assert "Project context: My Project" in msg
        assert "Topic: LLM evaluation" in msg
        assert "Research question: How to evaluate LLMs?" in msg
        assert "User message: do research on AI" in msg


@pytest.mark.asyncio
class TestIntentClassifierClassify:
    """Tests for IntentClassifier.classify."""

    async def test_classify_success(self) -> None:
        mock_provider = MagicMock()
        mock_provider.complete_structured = AsyncMock(return_value={
            "intent": "research_pipeline",
            "confidence": 0.95,
            "reasoning": "User wants full research",
            "query": "LLM evaluation",
            "project_id": None,
            "topic_hint": "LLM evaluation",
        })
        classifier = IntentClassifier(mock_provider)
        result = await classifier.classify("do research on LLM evaluation")
        assert result.intent == "research_pipeline"
        assert result.query == "LLM evaluation"
        mock_provider.complete_structured.assert_called_once()

    async def test_classify_fallback_on_exception(self) -> None:
        mock_provider = MagicMock()
        mock_provider.complete_structured = AsyncMock(
            side_effect=Exception("Network error")
        )
        classifier = IntentClassifier(mock_provider)
        result = await classifier.classify("do research on AI")
        # Should fallback to ambiguous
        assert result.intent == "ambiguous"
        assert result.confidence == 0.0
