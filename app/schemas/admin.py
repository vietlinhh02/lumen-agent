"""Pydantic models for admin API endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class UserAdminResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: str


class UserListResponse(BaseModel):
    items: list[UserAdminResponse]
    total: int


class UserUpdateRequest(BaseModel):
    is_active: bool | None = None
    role: str | None = None
