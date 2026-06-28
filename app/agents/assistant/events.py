"""
Event schemas for the Assistant SSE stream.

Defines the full event model used by the SSE stream for the ReAct agent.

Each event carries:
- id: unique event identifier
- timestamp: datetime in memory, ISO-8601 string on the wire
- type: Literal discriminator for Union parsing
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())


def now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------


class BaseEvent(BaseModel):
    """Base class for all assistant events."""

    id: str = Field(default_factory=generate_event_id)
    timestamp: datetime = Field(default_factory=now)
    type: str = ""
    turn_id: str | None = Field(
        default=None,
        description=(
            "Turn identifier grouping all events for a single user request. "
            "All events (user message, assistant response, tools, etc.) "
            "belonging to the same turn share the same turn_id."
        ),
    )

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Concrete events
# ---------------------------------------------------------------------------


class MessageEvent(BaseEvent):
    """A text message event (user or assistant)."""

    type: Literal["message"] = "message"
    role: Literal["user", "assistant"] = Field(..., description="Message author role")
    content: str = Field(..., description="Message text content")
    attachments: list[dict[str, Any]] | None = Field(
        default=None, description="Optional file attachments"
    )


class TitleEvent(BaseEvent):
    """A session title event."""

    type: Literal["title"] = "title"
    title: str = Field(..., description="Session title")


class ToolEvent(BaseEvent):
    """A tool call event (both calling and result)."""

    type: Literal["tool"] = "tool"
    tool_call_id: str = Field(..., description="Unique tool call identifier")
    name: str = Field(..., description="Tool name")
    status: Literal["calling", "called", "failed"] = Field(
        ..., description="Tool call status"
    )
    function: str = Field(..., description="Function/tool name being called")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: Any | None = Field(
        default=None, description="Tool execution result (if completed)"
    )
    error: str | None = Field(
        default=None, description="Error message (if failed)"
    )


class DoneEvent(BaseEvent):
    """Signals that the session has completed."""

    type: Literal["done"] = "done"
    summary: str | None = Field(
        default=None, description="Optional session summary"
    )
    usage: dict[str, Any] | None = Field(
        default=None, description="LLM token usage {input_tokens, output_tokens, model}"
    )


class ErrorEvent(BaseEvent):
    """Signals an error condition."""

    type: Literal["error"] = "error"
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Additional error details"
    )


class WaitEvent(BaseEvent):
    """Signals that the assistant is waiting for user input."""

    type: Literal["wait"] = "wait"
    question: str = Field(..., description="Question to ask the user")
    options: list[str] | None = Field(
        default=None, description="Optional multiple choice options"
    )
    placeholder: str | None = Field(
        default=None, description="Input placeholder text"
    )


class ThoughtEvent(BaseEvent):
    """A streaming chunk of the agent's chain-of-thought (ReAct).

    The frontend should accumulate ``delta`` into a per-iteration buffer
    so the user sees the reasoning tokens stream in real time.
    """

    type: Literal["thought"] = "thought"
    delta: str = Field(..., description="Incremental token chunk")
    iteration: int = Field(..., ge=0, description="ReAct iteration index (0-indexed)")
    is_final: bool = Field(
        default=False,
        description="True for the last token of the current Thought",
    )


class IterationEvent(BaseEvent):
    """Marks the start of a new ReAct iteration and its current phase.

    Emitted by the agent loop right before reasoning (streaming Thought
    tokens) and again right before acting (executing tool calls).
    """

    type: Literal["iteration"] = "iteration"
    n: int = Field(..., ge=0, description="Current iteration number (0-indexed)")
    max: int = Field(..., ge=1, description="Max iterations cap (e.g., 15)")
    phase: Literal["reasoning", "acting"] = Field(
        ..., description="Current phase within the iteration"
    )


class ProgressEvent(BaseEvent):
    """Marks progress in a multi-stage pipeline.

    Emitted by pipeline orchestrators (e.g., ResearchPipeline) so the UI
    can render a real-time progress bar without having to parse tool
    events. Distinct from ToolEvent: ToolEvent signals a single tool
    invocation; ProgressEvent signals a stage in a higher-level workflow.

    Frontend should:
    - group events by stage
    - render the latest progress per stage as a status line
    - show the message verbatim as human-readable status text
    """

    type: Literal["progress"] = "progress"
    stage: str = Field(..., description="Pipeline stage name (e.g., 'search', 'matrix')")
    progress: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Progress fraction within the pipeline (0.0 - 1.0)",
    )
    message: str = Field(..., description="Human-readable status message")
    data: dict[str, Any] | None = Field(
        default=None, description="Optional structured data (counts, IDs, links)"
    )


class MessageAckEvent(BaseEvent):
    """Acknowledges a client-generated message ID and provides the canonical ID.

    When a client sends a message with a client_message_id, the backend
    emits this event to:
    1. Confirm the message was received
    2. Provide the canonical event ID that will be used for persistence
    3. Allow the frontend to deduplicate optimistic messages

    The frontend should replace any optimistic message with the same
    client_message_id using the canonical message_id from this ack.
    """

    type: Literal["message_ack"] = "message_ack"
    client_message_id: str = Field(..., description="The client's message ID")
    canonical_id: str = Field(..., description="The canonical event ID assigned by backend")
    turn_id: str = Field(..., description="The turn ID for this user request")


class AssistantDeltaEvent(BaseEvent):
    """A streaming chunk of the visible assistant message.

    This event carries the actual answer text that the user sees in the
    chat bubble. Unlike ThoughtEvent (which streams internal reasoning),
    AssistantDeltaEvent streams the final assistant response.

    The frontend should:
    - Create an assistant message entry when the first delta arrives
    - Accumulate `delta` into the message content
    - Update the message in place as more deltas arrive
    - This provides immediate feedback while the model is still generating
    """

    type: Literal["assistant_delta"] = "assistant_delta"
    delta: str = Field(..., description="Incremental token chunk for the visible assistant message")
    is_final: bool = Field(
        default=False,
        description="True for the last token, signaling the message is complete",
    )


# ---------------------------------------------------------------------------
# Union type for all events
# ---------------------------------------------------------------------------

AssistantEvent = Union[
    MessageEvent,
    TitleEvent,
    ToolEvent,
    DoneEvent,
    ErrorEvent,
    WaitEvent,
    ThoughtEvent,
    IterationEvent,
    ProgressEvent,
    MessageAckEvent,
    AssistantDeltaEvent,
]

# Type alias for event type literals
EventType = Literal[
    "message",
    "title",
    "tool",
    "done",
    "error",
    "wait",
    "thought",
    "iteration",
    "progress",
    "message_ack",
    "assistant_delta",
]
