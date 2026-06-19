"""FastRouter — intent classifier for the ReAct agent.

Uses MiMo 2.5 via the OpenAI-compatible endpoint to classify user intent.
Falls back to COMPLEX on any error (timeout, API failure, etc.).

Regex pre-filter handles obvious patterns before hitting the LLM for speed.
"""

from __future__ import annotations

import asyncio
import re
from enum import Enum

from app.agents.assistant.react.prompts import ROUTER_PROMPT
from app.ai.provider import OpenAICompatibleAdapter, get_settings


class Intent(Enum):
    """Possible user intents from the router."""

    AMBIGUOUS = "AMBIGUOUS"
    DIRECT_LIST = "DIRECT_LIST"
    SEARCH = "SEARCH"
    ANALYZE = "ANALYZE"
    REPORT = "REPORT"
    RAG_QA = "RAG_QA"
    COMPLEX = "COMPLEX"


# ── Regex pre-filter ────────────────────────────────────────────────────────


# Fast pattern matching for obvious intents — no LLM needed.
# These fire before any API call and short-circuit classification.
_DIRECT_LIST_PATTERNS = re.compile(
    r"^(list|show|get|view|display)\s+(my\s+)?"
    r"(projects?|papers?|reports?|gaps?|conflicts?|matrices?|results?)"
    r"\b",
    re.IGNORECASE,
)

_ANALYZE_PATTERNS = re.compile(
    r"^(compare|analyze|evaluate|assess)\s+(my\s+)?papers?",
    re.IGNORECASE,
)

_SEARCH_PATTERNS = re.compile(
    r"^(search|find|look\s+up|lookup)\s+(for\s+)?papers?",
    re.IGNORECASE,
)

_REPORT_PATTERNS = re.compile(
    r"^(write|generate|create|make)\s+(me\s+)?a?\s*"
    r"(report|summary|literature\s+review|overview)",
    re.IGNORECASE,
)

_RAG_QA_PATTERNS = re.compile(
    r"what\s+does\s+(paper\s+[\w\d-]+|[\"\']?[^\"\']+[\"\']?)\s+say\s+about",
    re.IGNORECASE,
)

_COMPLEX_PATTERNS = re.compile(
    r"\bthen\b|\band\b.*\b(search|generate|detect|analyze|compare|write)\b",
    re.IGNORECASE,
)


def _regex_classify(message: str) -> Intent | None:
    """Fast regex-based pre-classification. Returns None if no pattern matches."""
    msg = message.strip()

    # NOTE: Order matters! More specific patterns checked before general ones.
    # COMPLEX must come before SEARCH because "search...then..." is complex.
    if _DIRECT_LIST_PATTERNS.match(msg):
        return Intent.DIRECT_LIST
    if _ANALYZE_PATTERNS.match(msg):
        return Intent.ANALYZE
    if _COMPLEX_PATTERNS.search(msg):
        return Intent.COMPLEX
    if _SEARCH_PATTERNS.match(msg):
        return Intent.SEARCH
    if _REPORT_PATTERNS.match(msg):
        return Intent.REPORT
    if _RAG_QA_PATTERNS.search(msg):
        return Intent.RAG_QA

    # Ambiguous check: very short / vague messages
    if len(msg.split()) <= 3 and msg.lower() in (
        "help me",
        "i want something",
        "do something",
        "help",
        "idk",
        "IDk",
        "IDK",
        "IDontKnow",
        "IDontKnowWhatIWant",
    ):
        return Intent.AMBIGUOUS

    return None


# ── FastRouter ──────────────────────────────────────────────────────────────


_ROUTER_MODEL = "mimo-v2.5-pro"
_ROUTER_TIMEOUT_SECONDS = 1.0
_MAX_OUTPUT_TOKENS = 20


class FastRouter:
    """Fast intent classifier using MiMo 2.5.

    Classifies user messages into one of 7 intent buckets.
    Uses regex pre-filtering to skip LLM for obvious patterns.

    Usage:
        router = FastRouter()
        intent = await router.classify("list my projects", has_project=True)
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAICompatibleAdapter(
            model=_ROUTER_MODEL,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    async def classify(
        self,
        message: str,
        has_project: bool = False,
    ) -> Intent:
        """Classify user intent from a message.

        Args:
            message: The raw user message.
            has_project: Whether the user has an active project context.

        Returns:
            One of 7 Intent values.
        """
        # 1. Fast regex pre-filter — no LLM call needed
        intent = _regex_classify(message)
        if intent is not None:
            return intent

        # 2. LLM classification with hard 1s timeout
        try:
            return await asyncio.wait_for(
                self._llm_classify(message, has_project),
                timeout=_ROUTER_TIMEOUT_SECONDS,
            )
        except (TimeoutError, Exception):
            # Any failure → fall back to COMPLEX so the full ReAct loop handles it
            return Intent.COMPLEX

    async def _llm_classify(
        self,
        message: str,
        has_project: bool,
    ) -> Intent:
        """Call the LLM to classify intent."""
        # Inject project context into the prompt
        context_note = (
            " [User has an active project context.]"
            if has_project
            else " [User has no active project.]"
        )

        response_text = await self._client.complete(
            messages=[{"role": "user", "content": message.strip()}],
            system=ROUTER_PROMPT + context_note,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )

        # Parse response — extract the first valid intent label that appears
        # anywhere in the response. The model occasionally adds punctuation
        # or a leading explanation before the label.
        intent_str = _extract_intent_label(response_text)
        if intent_str is None:
            return Intent.COMPLEX

        for intent in Intent:
            if intent.value == intent_str:
                return intent

        return Intent.COMPLEX


def _extract_intent_label(text: str) -> str | None:
    """Extract the first valid intent label from a free-form LLM response.

    Handles cases where the model returns extra explanation or formatting
    around the label (e.g., "**DIRECT_LIST**" or "The intent is DIRECT_LIST.").
    """
    if not text:
        return None
    upper = text.strip().upper()
    valid_values = {intent.value for intent in Intent}
    # Direct match first
    if upper in valid_values:
        return upper
    # Strip common decoration
    cleaned = upper.strip("*` \t\n\r.,:;-")
    if cleaned in valid_values:
        return cleaned
    # Search for any valid label appearing in the response
    for token in upper.replace("\n", " ").split():
        cleaned_token = token.strip("*` \t\n\r.,:;-")
        if cleaned_token in valid_values:
            return cleaned_token
    return None
