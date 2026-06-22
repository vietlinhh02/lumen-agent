import pytest

from app.schemas.project import ProjectResponse, ReviewProtocol
from app.services.project import _validate_project_paper_update


def test_review_protocol_defaults_are_structured():
    protocol = ReviewProtocol()

    assert protocol.research_questions == []
    assert protocol.inclusion_criteria == []
    assert protocol.exclusion_criteria == []
    assert protocol.source_list == []
    assert protocol.population is None


def test_project_response_accepts_partial_protocol(project_response_payload):
    payload = {**project_response_payload, "review_protocol": {"source_list": ["OpenAlex"]}}

    response = ProjectResponse.model_validate(payload)

    assert response.review_protocol.source_list == ["OpenAlex"]
    assert response.review_protocol.inclusion_criteria == []


def test_rejected_project_paper_requires_reason():
    with pytest.raises(ValueError, match="Rejected papers require an exclusion reason"):
        _validate_project_paper_update("rejected", None)


def test_rejected_project_paper_rejects_unknown_reason():
    with pytest.raises(ValueError, match="Invalid exclusion reason"):
        _validate_project_paper_update("rejected", "not_a_reason")


def test_rejected_project_paper_accepts_controlled_reason():
    _validate_project_paper_update("rejected", "insufficient_relevance")


@pytest.fixture
def project_response_payload():
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "00000000-0000-0000-0000-000000000002",
        "title": "Medical RAG",
        "topic": "Retrieval-augmented generation for medical QA",
        "research_question": None,
        "status": "active",
        "created_at": "2026-06-22T00:00:00",
        "updated_at": "2026-06-22T00:00:00",
        "paper_count": 0,
    }
