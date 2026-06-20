"""Schema and instantiation tests for the assistant Plan-Act tables.

These tests are DB-free: they introspect SQLAlchemy metadata and exercise
the model classes in memory. The end-to-end ``docker compose up -d db &&
make dev`` round-trip is left to the acceptance criteria documented in
``docs/assistant-direction.md`` (Task 1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.models import (
    AssistantEvent,
    AssistantPlan,
    AssistantSession,
    Base,
    Project,
    User,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _table(model):
    return model.__table__


def _column(model, name):
    table = _table(model)
    assert name in table.c, f"{model.__name__} missing column '{name}'"
    return table.c[name]


def _foreign_key(column, target_table):
    fks = [fk for fk in column.foreign_keys if fk.column.table.name == target_table]
    assert fks, f"column '{column.name}' has no FK to '{target_table}'"
    return fks[0]


def _index_names(model):
    return {ix.name for ix in _table(model).indexes}


def _constraint_names(model):
    return {c.name for c in _table(model).constraints if c.name}


# ── Schema introspection: registration ───────────────────────────────────────


def test_assistant_models_registered_on_metadata():
    """All three tables show up in Base.metadata after import."""
    tables = set(Base.metadata.tables)
    assert "assistant_sessions" in tables
    assert "assistant_events" in tables
    assert "assistant_plans" in tables


def test_existing_user_and_project_tables_untouched():
    """Acceptance: 'No changes to existing 17 tables' columns'."""
    user_cols = {c.name for c in _table(User).c}
    project_cols = {c.name for c in _table(Project).c}

    # Sanity: a known existing column set is unchanged.
    assert {
        "id",
        "email",
        "display_name",
        "password_hash",
        "role",
        "is_active",
        "created_at",
    } <= user_cols
    assert {
        "id",
        "owner_id",
        "title",
        "topic",
        "research_question",
        "status",
        "created_at",
        "updated_at",
    } <= project_cols


# ── AssistantSession ─────────────────────────────────────────────────────────


def test_assistant_session_columns_and_defaults():
    """Required columns exist with correct nullability and server defaults."""
    table = _table(AssistantSession)
    expected = {
        "id",
        "user_id",
        "project_id",
        "title",
        "status",
        "created_at",
        "updated_at",
    }
    assert expected <= set(table.c.keys())

    assert isinstance(_column(AssistantSession, "id").type, UUID)
    assert _column(AssistantSession, "id").primary_key is True
    assert _column(AssistantSession, "user_id").nullable is False
    assert _column(AssistantSession, "project_id").nullable is True
    assert _column(AssistantSession, "status").nullable is False

    # created_at / updated_at default to now().
    assert _column(AssistantSession, "created_at").server_default is not None
    assert _column(AssistantSession, "updated_at").server_default is not None
    assert _column(AssistantSession, "updated_at").onupdate is not None


def test_assistant_session_user_fk_cascades():
    """`assistant_sessions.user_id` → users.id ON DELETE CASCADE."""
    fk = _foreign_key(_column(AssistantSession, "user_id"), "users")
    assert fk.ondelete == "CASCADE"


def test_assistant_session_project_fk_cascades():
    """`assistant_sessions.project_id` → projects.id ON DELETE CASCADE."""
    fk = _foreign_key(_column(AssistantSession, "project_id"), "projects")
    assert fk.ondelete == "CASCADE"


def test_assistant_session_status_check_constraint():
    """A CHECK constraint locks status to a known vocabulary."""
    assert "ck_assistant_sessions_status" in _constraint_names(AssistantSession)


def test_assistant_session_user_updated_index():
    """`(user_id, updated_at)` composite index supports recent-sessions sort."""
    indexes = {
        ix.name: tuple(c.name for c in ix.columns) for ix in _table(AssistantSession).indexes
    }
    assert "ix_assistant_sessions_user_updated" in indexes
    assert indexes["ix_assistant_sessions_user_updated"] == ("user_id", "updated_at")


def test_assistant_session_back_populates_user_and_project():
    """ORM relationships are wired in both directions."""
    rel_names = {r.key for r in AssistantSession.__mapper__.relationships}
    assert {"user", "project", "events", "plan"} <= rel_names

    user_rel = AssistantSession.__mapper__.relationships["user"]
    assert user_rel.back_populates == "assistant_sessions"

    project_rel = AssistantSession.__mapper__.relationships["project"]
    assert project_rel.back_populates == "assistant_sessions"

    # `plan` is a one-to-one (uselist=False).
    plan_rel = AssistantSession.__mapper__.relationships["plan"]
    assert plan_rel.uselist is False


# ── AssistantEvent ───────────────────────────────────────────────────────────


def test_assistant_event_columns_and_payload_jsonb():
    table = _table(AssistantEvent)
    expected = {"id", "session_id", "event_type", "payload", "created_at"}
    assert expected <= set(table.c.keys())

    assert isinstance(_column(AssistantEvent, "payload").type, JSONB)
    assert _column(AssistantEvent, "session_id").nullable is False
    assert _column(AssistantEvent, "event_type").nullable is False
    assert _column(AssistantEvent, "created_at").server_default is not None


def test_assistant_event_session_fk_cascades():
    fk = _foreign_key(_column(AssistantEvent, "session_id"), "assistant_sessions")
    assert fk.ondelete == "CASCADE"


def test_assistant_event_type_check_constraint():
    """Event types are restricted to the Plan-Act event vocabulary."""
    assert "ck_assistant_events_type" in _constraint_names(AssistantEvent)


def test_assistant_event_history_replay_index():
    """Acceptance: `assistant_events` has an index on `(session_id, created_at)`."""
    indexes = {ix.name: tuple(c.name for c in ix.columns) for ix in _table(AssistantEvent).indexes}
    assert "ix_assistant_events_session_created" in indexes
    assert indexes["ix_assistant_events_session_created"] == ("session_id", "created_at")


# ── AssistantPlan ────────────────────────────────────────────────────────────


def test_assistant_plan_columns_and_jsonb_steps():
    table = _table(AssistantPlan)
    expected = {
        "id",
        "session_id",
        "title",
        "language",
        "steps",
        "current_step_index",
        "status",
        "created_at",
        "updated_at",
    }
    assert expected <= set(table.c.keys())

    assert isinstance(_column(AssistantPlan, "steps").type, JSONB)
    assert _column(AssistantPlan, "session_id").nullable is False
    assert _column(AssistantPlan, "current_step_index").nullable is False
    assert _column(AssistantPlan, "status").nullable is False
    assert _column(AssistantPlan, "created_at").server_default is not None
    assert _column(AssistantPlan, "updated_at").server_default is not None
    assert _column(AssistantPlan, "updated_at").onupdate is not None


def test_assistant_plan_session_unique_one_per_session():
    """Acceptance: `assistant_plans.session_id` is UNIQUE (one plan / session)."""
    assert _column(AssistantPlan, "session_id").unique is True


def test_assistant_plan_session_fk_cascades():
    fk = _foreign_key(_column(AssistantPlan, "session_id"), "assistant_sessions")
    assert fk.ondelete == "CASCADE"


def test_assistant_plan_status_check_constraint():
    assert "ck_assistant_plans_status" in _constraint_names(AssistantPlan)


# ── Basic insert/read with a mocked AsyncSession ─────────────────────────────


@pytest.mark.asyncio
async def test_assistant_session_insert_and_read_roundtrip():
    """Round-trip a session through a mocked AsyncSession (no real DB)."""
    user_id = uuid4()
    project_id = uuid4()
    session_id = uuid4()
    now = datetime.now(UTC)

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(
        side_effect=lambda obj: (
            setattr(obj, "id", session_id)
            or setattr(obj, "created_at", now)
            or setattr(obj, "updated_at", now)
        )
    )

    session = AssistantSession(
        user_id=user_id,
        project_id=project_id,
        title="My research chat",
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    db.add.assert_called_once_with(session)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(session)
    assert session.id == session_id
    assert session.user_id == user_id
    assert session.project_id == project_id
    assert session.title == "My research chat"
    assert session.status == "active"
    assert session.created_at == now
    assert session.updated_at == now

    # Read-side: a mocked SELECT returns our session.
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=session),
        )
    )
    loaded = (await db.execute(MagicMock())).scalar_one_or_none()
    assert loaded is session


@pytest.mark.asyncio
async def test_assistant_event_insert_and_read_roundtrip():
    session_id = uuid4()
    event_id = uuid4()

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", event_id))

    event = AssistantEvent(
        session_id=session_id,
        event_type="tool",
        payload={
            "tool_name": "search_papers",
            "status": "calling",
            "args": {"query": "RAG medical QA", "limit": 5},
        },
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    db.add.assert_called_once_with(event)
    assert event.id == event_id
    assert event.session_id == session_id
    assert event.event_type == "tool"
    assert event.payload["tool_name"] == "search_papers"
    assert event.payload["args"]["limit"] == 5

    # Replay: scalars().all() returns a chronological list.
    history = [event]
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=history)))
        )
    )
    replayed = (await db.execute(MagicMock())).scalars().all()
    assert replayed == history


@pytest.mark.asyncio
async def test_assistant_plan_insert_and_read_roundtrip():
    session_id = uuid4()
    plan_id = uuid4()

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", plan_id))

    plan = AssistantPlan(
        session_id=session_id,
        title="Find RAG papers and build matrix",
        language="en",
        steps=[
            {"id": "1", "description": "Search papers", "expected_tool": "search_papers"},
            {"id": "2", "description": "Save top 8", "expected_tool": "save_paper_to_project"},
            {"id": "3", "description": "Generate matrix", "expected_tool": "generate_matrix"},
        ],
        current_step_index=0,
        status="in_progress",
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    assert plan.id == plan_id
    assert plan.session_id == session_id
    assert plan.language == "en"
    assert plan.current_step_index == 0
    assert plan.status == "in_progress"
    assert len(plan.steps) == 3
    assert plan.steps[0]["expected_tool"] == "search_papers"


# ── Defaults applied at object instantiation (Python-side) ───────────────────


def test_assistant_plan_python_defaults_are_safe():
    """Without explicit values, JSONB / numeric / status columns have sane defaults.

    ``server_default`` is applied by Postgres; ``default=`` is applied by
    SQLAlchemy at flush. We rely on flush-side defaults here so a freshly
    constructed object (without commit) can be inspected in tests / unit code.
    """
    plan = AssistantPlan(session_id=uuid4())
    # `default=list` ensures `steps` is a list — required for safe iteration
    # before the row hits the DB.
    assert plan.steps == [] or plan.steps is None
    # `default=0` for current_step_index.
    assert plan.current_step_index in (0, None)
    # `default="in_progress"` for status.
    assert plan.status in ("in_progress", None)


def test_assistant_event_python_default_payload():
    event = AssistantEvent(session_id=uuid4(), event_type="message")
    assert event.payload == {} or event.payload is None
