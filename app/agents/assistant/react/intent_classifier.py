"""Structured intent classifier for the ReAct agent.

Uses LLM with JSON schema output to classify user intent. Replaces regex-based
FastRouter with a semantically-aware classifier that handles natural language
variation (English, Vietnamese, etc.).

The classifier extracts intent plus pre-structured parameters (query, project_id)
so downstream code does not need to re-parse from free-form text.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.ai.provider import AIProvider

logger = logging.getLogger(__name__)


# ── Output Schema ────────────────────────────────────────────────────────────────


class IntentOutput(BaseModel):
    """Schema-enforced output of the intent classifier.

    Attributes:
        intent: One of the defined intent labels.
        confidence: Float 0.0-1.0 indicating classification certainty.
        reasoning: Short explanation of why this intent was chosen.
        query: The research topic if present in the message, None otherwise.
        project_id: Project ID if explicitly mentioned, None otherwise.
        topic_hint: Refined search query derived from the message.
    """

    intent: str = Field(
        description=(
            "One of: search_only | qa | list | chitchat | ambiguous"
        )
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence score.")
    reasoning: str = Field(max_length=300, description="One-sentence explanation.")
    query: str | None = Field(
        default=None,
        description="Research topic or query extracted from the message.",
    )
    project_id: str | None = Field(
        default=None,
        description="Project ID if explicitly mentioned in the message.",
    )
    topic_hint: str | None = Field(
        default=None,
        description="Refined search query derived from the message.",
    )


# ── System Prompt ───────────────────────────────────────────────────────────────


INTENT_SYSTEM_PROMPT = """\
You are an intent classifier for a research assistant. Analyze the user's
message and return structured JSON matching the IntentOutput schema.

INTENT DEFINITIONS:

- search_only: User wants to search for general information on the web/Google.
  Signals: "search for X", "tìm kiếm thông tin X", "tìm hiểu về X", "Google X".

- qa: User asks a specific question about content in papers already saved in
  their project. Signals: "what does paper X say about Y?", "summarize my papers",
  "what methods were used", "tóm tắt papers của tôi", "phương pháp nào được dùng".

- list: User wants to list or retrieve existing data (projects, papers, matrices, reports,
  gaps). Signals: "list my projects", "show papers", "what papers do I have",
  "danh sách project", "xem báo cáo", "show me the matrix".

- chitchat: Greeting, thanks, off-topic, meta questions about the assistant.
  Signals: "hi", "hello", "thanks", "thank you", "how are you", "what can you do",
  "xin chào", "cảm ơn".

- ambiguous: Truly unclear. Ask for clarification.

EXTRACTION RULES:
- query: Extract the main research topic/subject from the message.
  "research on LLM evaluation" -> query = "LLM evaluation"
  "tìm hiểu về AI trong y tế" -> query = "AI trong y tế"
- topic_hint: A refined English query suitable for academic search (optional).
- project_id: Only if user explicitly says "in project X" or "dự án X" with a name/ID.

LANGUAGE: The classifier must handle both English and Vietnamese messages.
Always return a valid IntentOutput JSON object.
"""


# ── Classifier ─────────────────────────────────────────────────────────────────


# Valid intent values (for validation after parsing)
VALID_INTENTS = frozenset([
    "search_only",
    "qa",
    "list",
    "chitchat",
    "ambiguous",
])


class IntentClassifier:
    """Structured LLM-based intent classifier.

    Uses the AI provider's complete_structured method to get a schema-enforced
    IntentOutput. Falls back to "ambiguous" with low confidence on any error.

    Usage:
        classifier = IntentClassifier(provider=get_provider())
        result = await classifier.classify("do research on AI in healthcare")
        if result.intent == "research_pipeline":
            ...
    """

    # Timeout for the classification call (seconds)
    TIMEOUT_SECONDS = 30.0

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    async def classify(
        self,
        message: str,
        project_context: dict[str, Any] | None = None,
    ) -> IntentOutput:
        """Classify user intent with structured output.

        Args:
            message: The raw user message.
            project_context: Optional dict with project metadata to help
                the classifier disambiguate. Keys: project_name, topic,
                research_question.

        Returns:
            IntentOutput with intent, confidence, reasoning, and extracted params.
        """
        import asyncio

        # Build enriched message with project context
        user_content = self._build_user_message(message, project_context)

        try:
            result = await asyncio.wait_for(
                self._call_llm(user_content),
                timeout=self.TIMEOUT_SECONDS,
            )
            return self._parse_result(result)
        except TimeoutError:
            logger.warning("Intent classification timed out after %ds", self.TIMEOUT_SECONDS)
        except Exception as exc:
            logger.warning("Intent classification failed: %s", exc)

        # Fallback: mark as ambiguous with low confidence
        return IntentOutput(
            intent="ambiguous",
            confidence=0.0,
            reasoning="Classification failed, defaulting to ambiguous.",
            query=None,
            project_id=None,
            topic_hint=None,
        )

    async def _call_llm(self, user_content: str) -> dict[str, Any]:
        """Call the LLM for structured classification."""
        schema = IntentOutput.model_json_schema()

        result = await self._provider.complete_structured(
            messages=[{"role": "user", "content": user_content}],
            schema=schema,
            tool_name="classify_intent",
            system=INTENT_SYSTEM_PROMPT,
            max_tokens=32768,
        )
        return result

    def _build_user_message(
        self,
        message: str,
        project_context: dict[str, Any] | None,
    ) -> str:
        """Build the user message passed to the classifier."""
        parts = []

        if project_context:
            parts.append(
                f"Project context: {project_context.get('project_name', 'unknown')}\n"
                f"Topic: {project_context.get('topic', '')}\n"
                f"Research question: {project_context.get('research_question', '')}\n"
            )

        parts.append(f"User message: {message.strip()}")
        return "\n\n".join(parts)

    def _parse_result(self, result: dict[str, Any]) -> IntentOutput:
        """Validate and normalize the LLM result."""
        try:
            # Pydantic validation will catch type errors
            output = IntentOutput.model_validate(result)
        except Exception:
            # Malformed output — fall back
            logger.warning("Malformed intent output: %s", result)
            return IntentOutput(
                intent="ambiguous",
                confidence=0.0,
                reasoning="Malformed LLM output, defaulting to ambiguous.",
                query=None,
                project_id=None,
                topic_hint=None,
            )

        # Validate intent value
        if output.intent not in VALID_INTENTS:
            logger.warning("Unknown intent '%s' from LLM, defaulting to ambiguous", output.intent)
            return IntentOutput(
                intent="ambiguous",
                confidence=0.0,
                reasoning=f"Unknown intent '{output.intent}' from LLM.",
                query=output.query,
                project_id=output.project_id,
                topic_hint=output.topic_hint,
            )

        return output
