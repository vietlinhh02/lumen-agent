"""LangGraph state definition for the assistant agent.

The AssistantGraphState flows through every node in the graph.
This replaces the in-memory Scratchpad with a checkpointable state.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, List, Literal, Optional, TYPE_CHECKING, Union
from uuid import UUID

from langgraph.graph import add_messages

if TYPE_CHECKING:
    from app.agents.assistant.events import BaseEvent

logger = logging.getLogger(__name__)


# ── Supporting Types ────────────────────────────────────────────────────────


@dataclass
class ScratchpadEntry:
    """A single tool execution recorded in the scratchpad.
    
    This is persisted via LangGraph checkpoints, allowing the agent
    to resume with full context without reconstructing from SQL events.
    """

    tool_name: str
    args: dict
    result: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_message(self) -> dict[str, Any]:
        """Convert to a tool message for the LLM."""
        result_str = json.dumps(self.result, default=str, ensure_ascii=False)
        if len(result_str) > 2000:
            result_str = result_str[:2000] + "...[truncated]"
        return {
            "role": "tool",
            "name": self.tool_name,
            "content": result_str,
        }


@dataclass
class ToolCallPending:
    """A tool call awaiting execution."""

    call_id: str
    name: str
    arguments: dict


# ── Graph State ─────────────────────────────────────────────────────────────


@dataclass
class AssistantGraphState:
    """State that flows through the assistant LangGraph.

    Key checkpointed fields:
    - `messages`: Full conversation history (LangGraph handles persistence)
    - `scratchpad_entries`: Tool execution history (previously in-memory only)
    - `iteration`, `current_intent`: ReAct loop control

    Non-checkpointed fields (transient for SSE):
    - `pending_events`: Events to emit to the frontend (not persisted)

    Attributes:
        session_id: The assistant session UUID.
        user_id: The user UUID.
        messages: Chat messages with add_messages reducer.
        scratchpad_entries: Tool execution history for context.
        current_intent: The classified intent for current turn.
        iteration: Current ReAct iteration count.
        is_waiting: Whether the agent is waiting for user clarification.
        waiting_question: The question to ask the user.
        waiting_options: Optional choices for the user.
        pending_tool_calls: Tool calls awaiting execution.
        pending_events: Events to emit (transient, not checkpointed).
        current_streaming_text: Accumulated streaming text for this turn.
        max_iterations: Maximum ReAct iterations allowed.
        max_wall_time_seconds: Maximum wall time for the run.
        start_time: When the run started (for wall time tracking).
    """

    # ── Identity ──────────────────────────────────────────────────────────
    session_id: UUID
    user_id: UUID
    project_context: dict[str, Any] | None = None

    # ── Conversation (LangGraph handles persistence via reducer) ───────────
    messages: Annotated[list[dict[str, Any]], add_messages] = field(
        default_factory=list
    )

    # ── Scratchpad (CHECKPOINTED - was in-memory only) ────────────────────
    scratchpad_entries: list[ScratchpadEntry] = field(default_factory=list)

    # ── ReAct Control ─────────────────────────────────────────────────────
    current_intent: str | None = None
    iteration: int = 0

    # ── Wait/Resume State ──────────────────────────────────────────────────
    is_waiting: bool = False
    waiting_question: str | None = None
    waiting_options: list[str] | None = None
    waiting_placeholder: str | None = None

    # ── Tool Execution ─────────────────────────────────────────────────────
    pending_tool_calls: list[ToolCallPending] = field(default_factory=list)
    last_tool_result: dict[str, Any] | None = None

    # ── Streaming (for SSE) ────────────────────────────────────────────────
    # NOTE: These are NOT checkpointed - they are transient UX state
    pending_events: list[Any] = field(default_factory=list)
    current_streaming_text: str = ""

    # ── Limits ────────────────────────────────────────────────────────────
    max_iterations: int = 15
    max_wall_time_seconds: int = 600
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Errors ────────────────────────────────────────────────────────────
    errors: list[str] = field(default_factory=list)
    is_cancelled: bool = False


# ── Helper Functions ───────────────────────────────────────────────────────


def scratchpad_to_llm_messages(entries: list[ScratchpadEntry]) -> list[dict[str, Any]]:
    """Convert scratchpad entries to LLM-compatible tool messages.

    Args:
        entries: List of scratchpad entries.

    Returns:
        List of message dicts in ChatML format.
    """
    return [entry.to_message() for entry in entries]


def get_last_user_message(state: AssistantGraphState) -> str | None:
    """Extract the last user message from the conversation.

    Handles both dict messages (``{"role": "user", "content": ...}``) and
    LangChain message objects (``HumanMessage``, ``AIMessage``, ...) since
    the LangGraph ``add_messages`` reducer can pass either through.

    Args:
        state: The current graph state.

    Returns:
        The content of the last user message, or None if not found.
    """
    for msg in reversed(state.messages):
        role: str | None = None
        content: Any = None
        if isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        else:
            # LangChain message object: type='human' | 'ai' | ...
            msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
            role_map = {"human": "user", "ai": "assistant", "system": "system"}
            role = role_map.get(msg_type, msg_type)
            content = getattr(msg, "content", None)

        if role == "user" and isinstance(content, str) and content:
            return content
    return None


def check_limits(state: AssistantGraphState) -> str | None:
    """Check if any limit has been exceeded.

    Args:
        state: The current graph state.

    Returns:
        None if within limits, or an error message if exceeded.
    """
    if state.iteration >= state.max_iterations:
        return f"MAX_ITERATIONS: Exceeded {state.max_iterations} iterations"

    if state.start_time:
        elapsed = (datetime.now(timezone.utc) - state.start_time).total_seconds()
        if elapsed >= state.max_wall_time_seconds:
            return f"MAX_WALL_TIME: Exceeded {state.max_wall_time_seconds}s"

    return None


def get_scratchpad_context(state: AssistantGraphState) -> str:
    """Build a context string from scratchpad entries for the LLM.

    Args:
        state: The current graph state.

    Returns:
        A formatted string of recent tool executions.
    """
    if not state.scratchpad_entries:
        return ""

    recent = state.scratchpad_entries[-5:]  # Last 5 entries
    parts = []
    for entry in recent:
        args_str = ", ".join(f"{k}={v!r}" for k, v in entry.args.items())
        result_preview = str(entry.result)[:200]
        parts.append(f"[{entry.tool_name}] args: {args_str}\nResult: {result_preview}")

    return "\n\n".join(parts)
