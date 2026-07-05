from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The user's message to the assistant.",
    )
    client_message_id: str | None = Field(
        default=None,
    )
    action: str | None = Field(
        default=None,
        description="Optional action command (e.g. 'start_deep_research')"
    )
