"""
Event schemas for the Assistant SSE stream.

Defines the full event model used by the SSE stream, adapted from ai-manus
but tailored to Lumen's needs (no sandbox, no shell, no VNC).

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


class PlanEvent(BaseEvent):
    """A plan event containing the current plan steps."""

    type: Literal["plan"] = "plan"
    plan_id: str = Field(..., description="Unique plan identifier")
    title: str = Field(..., description="Plan title")
    language: str = Field(default="en", description="Plan language code")
    steps: List["PlanStep"] = Field(default_factory=list, description="Plan steps")

    @classmethod
    def from_steps(
        cls,
        plan_id: str,
        title: str,
        language: str,
        steps: List["PlanStep"],
    ) -> "PlanEvent":
        """Create a PlanEvent from steps."""
        return cls(plan_id=plan_id, title=title, language=language, steps=steps)


class PlanStep(BaseModel):
    """A single step within a plan."""

    id: str = Field(..., description="Unique step identifier")
    description: str = Field(..., description="Human-readable step description")
    expected_tool: str = Field(..., description="Tool name this step expects to call")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        default="pending", description="Step execution status"
    )


class StepEvent(BaseEvent):
    """A step status change event."""

    type: Literal["step"] = "step"
    step_id: str = Field(..., description="Step identifier")
    description: str = Field(..., description="Step description")
    status: Literal["pending", "running", "completed", "failed"] = Field(
        ..., description="Step execution status"
    )


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


# ---------------------------------------------------------------------------
# Union type for all events
# ---------------------------------------------------------------------------

AssistantEvent = Union[
    MessageEvent,
    TitleEvent,
    PlanEvent,
    StepEvent,
    ToolEvent,
    DoneEvent,
    ErrorEvent,
    WaitEvent,
]

# Type alias for event type literals
EventType = Literal[
    "message",
    "title",
    "plan",
    "step",
    "tool",
    "done",
    "error",
    "wait",
]
