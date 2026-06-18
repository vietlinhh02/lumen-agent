"""
Event mapper for converting AssistantEvent to SSE format.

Maps internal AgentEvent objects to SSE-compatible dicts with
{event: str, data: dict} shape ready for sse_starlette.
"""

from __future__ import annotations

from typing import Any

from app.agents.assistant.events import (
    AssistantEvent,
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    IterationEvent,
    MessageEvent,
    ProgressEvent,
    ThoughtEvent,
    TitleEvent,
    ToolEvent,
    WaitEvent,
)


class EventMapper:
    """
    Maps AssistantEvent to SSE-compatible format.

    The SSE format is: {event: str, data: dict}
    - event: the event type string (e.g., "message", "tool", "done")
    - data: the event data as a dict ready for JSON serialization
    """

    # Mapping from event type to its data class
    _TYPE_MAPPING: dict[str, type[BaseEvent]] = {
        "message": MessageEvent,
        "title": TitleEvent,
        "tool": ToolEvent,
        "done": DoneEvent,
        "error": ErrorEvent,
        "wait": WaitEvent,
        "thought": ThoughtEvent,
        "iteration": IterationEvent,
        "progress": ProgressEvent,
    }

    @classmethod
    def _serialize_value(cls, value: Any) -> Any:
        """Serialize a value for JSON, handling datetime and special types."""
        if hasattr(value, "model_dump"):
            # Pydantic model
            return value.model_dump(mode="json")
        elif hasattr(value, "dict"):
            # Legacy Pydantic
            return value.dict()
        elif hasattr(value, "isoformat"):
            # datetime
            return value.isoformat()
        elif isinstance(value, list):
            return [cls._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: cls._serialize_value(v) for k, v in value.items()}
        else:
            return value

    @classmethod
    def event_to_sse_event(cls, event: AssistantEvent) -> dict[str, Any]:
        """
        Convert an AssistantEvent to SSE format.

        Returns:
            Dict with keys:
                - event: str (the event type)
                - data: dict (the event data)
        """
        if not isinstance(event, BaseEvent):
            raise TypeError(f"Expected BaseEvent, got {type(event)}")

        event_type = event.type
        data = event.model_dump(mode="json")

        return {
            "event": event_type,
            "data": data,
        }

    @classmethod
    def events_to_sse_events(
        cls, events: list[AssistantEvent]
    ) -> list[dict[str, Any]]:
        """
        Convert a list of AssistantEvents to SSE format.

        Returns:
            List of dicts with {event: str, data: dict} shape.
        """
        return [cls.event_to_sse_event(event) for event in events]

    @classmethod
    def get_event_type(cls, event: AssistantEvent) -> str:
        """Get the event type string from an event."""
        return event.type

    @classmethod
    def parse_event(cls, event_type: str, data: dict[str, Any]) -> AssistantEvent:
        """
        Parse an SSE event back to an AssistantEvent.

        Args:
            event_type: The event type string (e.g., "message", "tool")
            data: The event data dict

        Returns:
            The corresponding AssistantEvent instance

        Raises:
            ValueError: If event_type is unknown
        """
        event_class = cls._TYPE_MAPPING.get(event_type)
        if event_class is None:
            raise ValueError(f"Unknown event type: {event_type}")

        return event_class(**data)

    @classmethod
    def validate_event(cls, event: AssistantEvent) -> bool:
        """
        Validate that an event is well-formed.

        Returns:
            True if valid
        Raises:
            ValueError: If validation fails
        """
        if not isinstance(event, BaseEvent):
            raise ValueError(f"Event must be a BaseEvent instance, got {type(event)}")

        if not event.type:
            raise ValueError("Event type cannot be empty")

        if event.type not in cls._TYPE_MAPPING:
            raise ValueError(f"Unknown event type: {event.type}")

        return True
