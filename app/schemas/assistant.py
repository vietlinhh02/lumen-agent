"""
Pydantic schemas for the Assistant API endpoints.

Defines request/response models for:
- Session CRUD operations
- Chat request/response
- SSE event formats
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ── Session Schemas ────────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    """Request body for creating a new session."""

    project_id: UUID | None = Field(
        default=None,
        description="Optional project ID to pin the session to.",
    )
    title: str | None = Field(
        default=None,
        max_length=255,
        description="Optional session title.",
    )


class SessionTitleUpdate(BaseModel):
    """Payload for renaming a session."""

    title: str = Field(
        ...,
        max_length=255,
        description="New session title (1-255 chars, will be trimmed).",
    )


class SessionSummary(BaseModel):
    """Lightweight session summary for list display."""

    id: UUID
    title: str | None = None
    project_id: UUID | None = None
    project_title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    event_count: int = 0

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    sessions: list[SessionSummary]
    total: int


class SessionEvent(BaseModel):
    """A single event in a session."""

    id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionDetail(BaseModel):
    """Full session detail with events."""

    id: UUID
    title: str | None = None
    project_id: UUID | None = None
    project_title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    events: list[SessionEvent] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    """Response for session creation."""

    id: UUID
    title: str | None = None
    project_id: UUID | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Chat Schemas ───────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The user's message to the assistant.",
    )


class ChatResponse(BaseModel):
    """Response for chat endpoint (non-SSE fallback)."""

    message: str = Field(..., description="Assistant's response message.")
    session_id: UUID

    model_config = {"from_attributes": True}


# ── Error Schemas ──────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Error message.")
    code: str | None = Field(default=None, description="Error code.")
