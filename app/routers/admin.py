"""REST endpoints for admin user management."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.admin import UserAdminResponse, UserListResponse, UserUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


def _require_admin(user: User) -> None:
    """Raise 403 if user is not admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserListResponse:
    """List all users. Admin only."""
    _require_admin(user)

    stmt = select(User).order_by(User.created_at.desc())
    users = (await db.execute(stmt)).scalars().all()

    items = [
        UserAdminResponse(
            id=str(u.id),
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
            created_at=str(u.created_at),
        )
        for u in users
    ]
    return UserListResponse(items=items, total=len(items))


@router.patch("/users/{user_id}", response_model=UserAdminResponse)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserAdminResponse:
    """Update a user's active status or role. Admin only."""
    _require_admin(user)

    uid = uuid.UUID(user_id)
    target = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.is_active is not None:
        target.is_active = body.is_active
    if body.role is not None:
        if body.role not in ("researcher", "admin"):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Role must be 'researcher' or 'admin'",
            )
        target.role = body.role

    await db.commit()
    await db.refresh(target)

    return UserAdminResponse(
        id=str(target.id),
        email=target.email,
        display_name=target.display_name,
        role=target.role,
        is_active=target.is_active,
        created_at=str(target.created_at),
    )
