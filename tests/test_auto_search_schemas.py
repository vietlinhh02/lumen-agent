"""Schemas for the auto search endpoint."""

from app.schemas.paper import AutoSearchRequest, AutoSearchResponse


def test_auto_search_request_validates_target_count():
    """Only 5, 15, 25 are accepted. Others raise validation error."""
    for n in (5, 15, 25):
        r = AutoSearchRequest(query="RAG medical QA", target_count=n)
        assert r.target_count == n

    # Out-of-range values are rejected
    import pytest
    from pydantic import ValidationError

    for n in (10, 50, 75, 150, 200):
        with pytest.raises(ValidationError):
            AutoSearchRequest(query="RAG medical QA", target_count=n)


def test_auto_search_request_validates_query_length():
    """Empty / short queries are now allowed — backend will auto-generate
    one from the project topic. Max length still applies."""
    from pydantic import ValidationError
    import pytest

    # Empty / short queries are allowed
    AutoSearchRequest(query="", target_count=25)
    AutoSearchRequest(query="x", target_count=25)

    # Too long queries are still rejected
    with pytest.raises(ValidationError):
        AutoSearchRequest(query="x" * 501, target_count=25)  # too long


def test_auto_search_response_defaults():
    r = AutoSearchResponse(job_id="j", session_id="s", target_count=25, status="running")
    assert r.status == "running"
