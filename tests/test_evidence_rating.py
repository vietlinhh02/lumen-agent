"""Tests for the T3 Phase 3 evidence-rating endpoints (private per-user)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.routers import evidence_ratings as ratings_router
from app.schemas.evidence import EvidenceRatingCreate


def _result(value=None, *, all_rows=None):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    if all_rows is not None:
        r.all.return_value = all_rows
        r.scalars.return_value.all.return_value = all_rows
    return r


def _body():
    return EvidenceRatingCreate(
        source_kind="matrix_row",
        source_id=uuid4(),
        project_paper_id=uuid4(),
        chunk_id=uuid4(),
        rating="weak",
        note="Quote is about a different dataset.",
    )


# ── Upsert: insert path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_creates_rating_when_absent():
    project = SimpleNamespace(id=uuid4())
    body = _body()
    db = MagicMock()
    # owner check returns project, existing-rating lookup returns None.
    db.execute = AsyncMock(side_effect=[_result(project), _result(None)])
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(obj):
        obj.id = uuid4()
        obj.updated_at = datetime.now(UTC)

    db.refresh = AsyncMock(side_effect=_refresh)

    resp = await ratings_router.upsert_evidence_rating(
        project_id=project.id, body=body, db=db, user=SimpleNamespace(id=uuid4())
    )

    # A new row was inserted with the posted values.
    db.add.assert_called_once()
    created = db.add.call_args.args[0]
    assert created.rating == "weak"
    assert created.note == body.note
    assert created.source_kind == "matrix_row"
    assert resp.rating == "weak"
    assert resp.chunk_id == body.chunk_id


# ── Upsert: update path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_updates_existing_rating():
    project = SimpleNamespace(id=uuid4())
    body = _body()
    existing = SimpleNamespace(
        id=uuid4(),
        source_kind="matrix_row",
        source_id=body.source_id,
        project_paper_id=uuid4(),
        chunk_id=body.chunk_id,
        rating="accepted",
        note=None,
        updated_at=datetime.now(UTC),
    )
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(project), _result(existing)])
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    resp = await ratings_router.upsert_evidence_rating(
        project_id=project.id, body=body, db=db, user=SimpleNamespace(id=uuid4())
    )

    # Existing row mutated in place — no insert.
    db.add.assert_not_called()
    assert existing.rating == "weak"
    assert existing.note == body.note
    assert existing.project_paper_id == body.project_paper_id
    assert resp.rating == "weak"


# ── List ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_user_ratings_for_source():
    project = SimpleNamespace(id=uuid4())
    source_id = uuid4()
    rows = [
        SimpleNamespace(
            id=uuid4(),
            source_kind="matrix_row",
            source_id=source_id,
            project_paper_id=uuid4(),
            chunk_id=uuid4(),
            rating="accepted",
            note=None,
            updated_at=datetime.now(UTC),
        ),
        SimpleNamespace(
            id=uuid4(),
            source_kind="matrix_row",
            source_id=source_id,
            project_paper_id=uuid4(),
            chunk_id=uuid4(),
            rating="wrong",
            note="off-topic",
            updated_at=datetime.now(UTC),
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(project), _result(all_rows=rows)])

    resp = await ratings_router.list_evidence_ratings(
        project_id=project.id,
        source_kind="matrix_row",
        source_id=source_id,
        db=db,
        user=SimpleNamespace(id=uuid4()),
    )

    assert len(resp.items) == 2
    assert {i.rating for i in resp.items} == {"accepted", "wrong"}


# ── Summary ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summary_tallies_by_rating():
    project = SimpleNamespace(id=uuid4())
    # group_by(rating) result rows: (rating, count)
    rows = [("accepted", 3), ("weak", 2)]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_result(project), _result(all_rows=rows)])

    resp = await ratings_router.evidence_rating_summary(
        project_id=project.id, db=db, user=SimpleNamespace(id=uuid4())
    )

    assert resp.accepted == 3
    assert resp.weak == 2
    assert resp.wrong == 0


# ── Ownership guard ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_404_when_project_not_owned():
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=_result(None))  # owner check fails

    with pytest.raises(HTTPException) as exc:
        await ratings_router.upsert_evidence_rating(
            project_id=uuid4(),
            body=_body(),
            db=db,
            user=SimpleNamespace(id=uuid4()),
        )
    assert exc.value.status_code == 404
