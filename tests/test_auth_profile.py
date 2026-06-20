from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.db.models import User
from app.routers.auth import update_profile
from app.schemas.auth import ProfileUpdateRequest


class DummySession:
    def __init__(self) -> None:
        self.committed = False
        self.refreshed = False

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _obj: object) -> None:
        self.refreshed = True


@pytest.mark.asyncio
async def test_update_profile_normalizes_and_persists_display_name() -> None:
    """Updating profile stores a trimmed display name and returns it."""
    db = DummySession()
    user = User(
        id=uuid.uuid4(),
        email="linh@example.com",
        display_name="linh",
        password_hash="hash",
        role="researcher",
        is_active=True,
    )

    response = await update_profile(
        ProfileUpdateRequest(display_name="  Nguyen   Viet Linh  "),
        db,  # type: ignore[arg-type]
        user,
    )

    assert response.display_name == "Nguyen Viet Linh"
    assert user.display_name == "Nguyen Viet Linh"
    assert db.committed is True
    assert db.refreshed is True


@pytest.mark.asyncio
async def test_update_profile_rejects_blank_display_name() -> None:
    """Whitespace-only names are rejected after normalization."""
    db = DummySession()
    user = User(
        id=uuid.uuid4(),
        email="linh@example.com",
        password_hash="hash",
        role="researcher",
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_profile(
            ProfileUpdateRequest(display_name="   "),
            db,  # type: ignore[arg-type]
            user,
        )

    assert exc_info.value.status_code == 400
    assert db.committed is False
