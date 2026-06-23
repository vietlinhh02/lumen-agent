"""Tests for the bulk delete-low-confidence matrix endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.matrix import bulk_delete_low_confidence, low_confidence_count
from app.services.literature_matrix import bulk_delete_by_confidence, count_by_confidence


def _user():
    return SimpleNamespace(id=uuid4())


def _project():
    return SimpleNamespace(id=uuid4(), owner_id=uuid4())


def _mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_bulk_delete_low_service_returns_count():
    """Service returns rowcount from the DELETE statement."""
    db = _mock_db()
    mock_result = MagicMock()
    mock_result.rowcount = 7
    db.execute.return_value = mock_result

    count = await bulk_delete_by_confidence(db, uuid4(), "low")

    assert count == 7


@pytest.mark.asyncio
async def test_bulk_delete_low_service_handles_zero():
    """Service returns 0 (not None) when nothing was deleted."""
    db = _mock_db()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    db.execute.return_value = mock_result

    count = await bulk_delete_by_confidence(db, uuid4(), "low")

    assert count == 0
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_count_by_confidence_service():
    db = _mock_db()
    db.execute.return_value = MagicMock(scalar_one=MagicMock(return_value=12))

    n = await count_by_confidence(db, uuid4(), "low")

    assert n == 12


@pytest.mark.asyncio
async def test_low_count_endpoint_returns_count():
    db = _mock_db()
    project = _project()
    user = _user()

    with patch(
        "app.routers.matrix._verify_project_owner",
        new=AsyncMock(return_value=project),
    ), patch(
        "app.routers.matrix.count_by_confidence",
        new=AsyncMock(return_value=5),
    ):
        result = await low_confidence_count(uuid4(), db, user)

    assert result == {"count": 5}


@pytest.mark.asyncio
async def test_low_count_endpoint_404_for_missing_project():
    db = _mock_db()
    user = _user()

    with patch(
        "app.routers.matrix._verify_project_owner",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Project not found")),
    ):
        with pytest.raises(HTTPException) as exc:
            await low_confidence_count(uuid4(), db, user)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_bulk_delete_low_endpoint_deletes():
    db = _mock_db()
    project = _project()
    user = _user()

    with patch(
        "app.routers.matrix._verify_project_owner",
        new=AsyncMock(return_value=project),
    ), patch(
        "app.routers.matrix.bulk_delete_by_confidence",
        new=AsyncMock(return_value=9),
    ) as mock_delete:
        result = await bulk_delete_low_confidence(uuid4(), db, user)

    assert result == {"deleted_count": 9}
    mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_bulk_delete_low_endpoint_zero_is_ok():
    """Endpoint must not 404 when there are no low rows."""
    db = _mock_db()
    project = _project()
    user = _user()

    with patch(
        "app.routers.matrix._verify_project_owner",
        new=AsyncMock(return_value=project),
    ), patch(
        "app.routers.matrix.bulk_delete_by_confidence",
        new=AsyncMock(return_value=0),
    ):
        result = await bulk_delete_low_confidence(uuid4(), db, user)

    assert result == {"deleted_count": 0}
