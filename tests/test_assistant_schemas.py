from app.schemas.assistant import (
    ChatDocumentResponse,
    ChatMessageResponse,
    ChatDocumentListResponse,
)


def test_chat_document_response_fields():
    schema = ChatDocumentResponse.model_json_schema()
    assert "id" in schema["properties"]
    assert "title" in schema["properties"]
    assert "content_md" in schema["properties"]
    assert "version" in schema["properties"]


def test_chat_message_response_fields():
    schema = ChatMessageResponse.model_json_schema()
    for f in ("id", "role", "content", "created_at", "tool_name"):
        assert f in schema["properties"]


def test_chat_document_list_response():
    schema = ChatDocumentListResponse.model_json_schema()
    assert "items" in schema["properties"]
    assert "total" in schema["properties"]
