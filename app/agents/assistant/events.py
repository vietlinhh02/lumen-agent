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
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


def generate_event_id() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())


def now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------


class BaseEvent(BaseModel):
    """Base class for all assistant events."""

    id: str = Field(default_factory=generate_event_id)
    timestamp: datetime = Field(default_factory=now)
    type: str = ""

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Concrete events
# ---------------------------------------------------------------------------


class MessageEvent(BaseEvent):
    """A text message event (user or assistant)."""

    type: Literal["message"] = "message"
    role: Literal["user", "assistant"] = Field(..., description="Message author role")
    content: str = Field(..., description="Message text content")
    attachments: Optional[List[Dict[str, Any]]] = Field(
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
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: Optional[Any] = Field(
        default=None, description="Tool execution result (if completed)"
    )
    error: Optional[str] = Field(
        default=None, description="Error message (if failed)"
    )


class DoneEvent(BaseEvent):
    """Signals that the session has completed."""

    type: Literal["done"] = "done"
    summary: Optional[str] = Field(
        default=None, description="Optional session summary"
    )


class ErrorEvent(BaseEvent):
    """Signals an error condition."""

    type: Literal["error"] = "error"
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional error details"
    )


class WaitEvent(BaseEvent):
    """Signals that the assistant is waiting for user input."""

    type: Literal["wait"] = "wait"
    question: str = Field(..., description="Question to ask the user")
    options: Optional[List[str]] = Field(
        default=None, description="Optional multiple choice options"
    )
    placeholder: Optional[str] = Field(
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
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional structured data (counts, IDs, links)"
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
]
