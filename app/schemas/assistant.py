"""Pydantic models for AI assistant REST endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessageResponse(BaseModel):
    id: str
    document_id: str
    project_id: str
    role: str
    content: str
    tool_name: str | None = None
    tool_args: dict = Field(default_factory=dict)
    tool_result: dict = Field(default_factory=dict)
    created_at: str


class ChatDocumentResponse(BaseModel):
    id: str
    project_id: str
    title: str
    content_md: str
    version: int
    created_at: str
    updated_at: str


class ChatDocumentDetailResponse(ChatDocumentResponse):
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class ChatDocumentListResponse(BaseModel):
    items: list[ChatDocumentResponse]
    total: int
