"""REST tests for AI assistant endpoints (replaces the old WS tests)."""


import pytest
from fastapi.testclient import TestClient

from app.main import app


def _fake_token(user_id):
    from app.services.auth import create_access_token

    return create_access_token(user_id=user_id, email="test@example.com")


@pytest.fixture
def client():
    return TestClient(app)


def test_sse_message_route_is_registered():
    """The /api/assistant/message SSE route should be in the app routes."""
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/assistant/message" in routes


def test_sse_stop_route_is_registered():
    """The /api/assistant/stop route should be in the app routes."""
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/assistant/stop" in routes


def test_rest_list_documents_route_is_registered():
    """The /api/assistant/documents REST route should be in the app routes."""
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/assistant/documents" in routes


def test_rest_create_document_route_is_registered():
    """POST /api/assistant/documents should create a persisted chat session."""
    routes = [
        r
        for r in app.routes
        if hasattr(r, "path") and r.path == "/api/assistant/documents"
    ]
    assert any("POST" in getattr(route, "methods", set()) for route in routes)


def test_rest_get_document_route_is_registered():
    """The parameterized /api/assistant/documents/{doc_id} should be registered."""
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/assistant/documents/{doc_id}" in paths
