"""Verify ChatDocument and ChatMessage models import and have correct columns."""

from uuid import uuid4

from app.db.models import ChatDocument, ChatMessage


def test_chat_document_columns():
    cols = {c.name for c in ChatDocument.__table__.columns}
    assert {
        "id",
        "project_id",
        "user_id",
        "title",
        "content_md",
        "version",
        "created_at",
        "updated_at",
    } <= cols


def test_chat_message_columns():
    cols = {c.name for c in ChatMessage.__table__.columns}
    assert {"id", "document_id", "project_id", "role", "content", "tool_name", "created_at"} <= cols
    # role has CHECK constraint
    role_check = next(c for c in ChatMessage.__table__.constraints if "role" in str(c.sqltext))
    assert role_check is not None
