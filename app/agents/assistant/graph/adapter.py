"""Adapter to make AssistantGraph a drop-in replacement for ReActAgent.

This module provides the integration layer between the LangGraph-based
AssistantGraph and the existing SSE router in session_service.py.

Usage:
    # Instead of ReActAgent:
    # agent = ReActAgent(provider=provider, tools=tools, project_context=ctx)
    # async for event in agent.run(message):
    #     yield event

    # Use AssistantGraph:
    from app.agents.assistant.graph.adapter import create_graph_runner
    
    runner = create_graph_runner(
        session_id=session_id,
        user_id=user_id,
        project_context=project_context,
        tools=tools,
        provider=provider,
    )
    async for event in runner.run(message, resume=resume, cancel_event=cancel_event):
        yield event
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

from app.agents.assistant.events import (
    AssistantDeltaEvent,
    BaseEvent,
    DoneEvent,
    ErrorEvent,
    IterationEvent,
    MessageEvent,
    ThoughtEvent,
    ToolEvent,
    WaitEvent,
)
from app.agents.assistant.graph.config import AssistantGraphConfig, get_checkpointer
from app.agents.assistant.graph.graph import get_assistant_graph, AssistantGraph
from app.agents.assistant.graph.nodes import (
    _get_tool_definitions,
    _message_to_dict,
)
from app.agents.assistant.graph.state import AssistantGraphState

if TYPE_CHECKING:
    from app.ai.provider import AIProvider
    from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


# ── Feature Flag ──────────────────────────────────────────────────────────────

# LangGraph is now the DEFAULT runner for the assistant.
# Set USE_REACT_AGENT=true to fall back to the legacy ReActAgent.
USE_LANGGRAPH = os.environ.get("USE_REACT_AGENT", "false").lower() != "true"


# ── Adapter Classes ──────────────────────────────────────────────────────────


class GraphRunner:
    """Adapter that makes AssistantGraph compatible with ReActAgent interface.

    This class wraps the LangGraph-based AssistantGraph and provides the same
    async generator interface as ReActAgent.run(), making it a drop-in replacement.

    Key differences from ReActAgent:
    - Checkpointing: scratchpad is persisted in LangGraph state
    - No need to restore scratchpad from SQL events on resume
    - Native tool calls via LangGraph's structured output

    Args:
        session_id: The assistant session UUID (used as thread_id for checkpointing).
        user_id: The user UUID.
        project_context: Optional project context dict.
        tools: List of available tools.
        provider: AI provider instance.
        config: Optional graph configuration.
    """

    def __init__(
        self,
        session_id: UUID,
        user_id: UUID,
        project_context: Dict[str, Any] | None,
        tools: List["BaseTool"],
        provider: "AIProvider",
        config: AssistantGraphConfig | None = None,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.project_context = project_context or {}
        self.tools = tools
        self.provider = provider
        self.config = config or AssistantGraphConfig()

        # Initialize the compiled graph
        self._graph = get_assistant_graph(self.config, force_rebuild=USE_LANGGRAPH)

        # Build checkpoint config
        self.checkpoint_config: Dict[str, Any] = {
            "configurable": {
                "thread_id": str(session_id),
                "checkpoint_ns": "main",
            }
        }

    async def run(
        self,
        message: str,
        resume: bool = False,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Run the assistant graph for a user message.

        This method:
        1. Loads checkpoint if resuming (scratchpad preserved)
        2. Creates initial state with tools and context
        3. Streams through the graph
        4. Yields SSE-compatible BaseEvent objects

        Args:
            message: The user's message.
            resume: If True, continue from existing checkpoint.
            cancel_event: Optional event to check for cancellation.

        Yields:
            BaseEvent subclasses from events.py.
        """
        import asyncio
        import json

        # Check for cancellation
        if cancel_event and cancel_event.is_set():
            yield ErrorEvent(code="CANCELLED", message="Session was cancelled before starting")
            yield DoneEvent(summary="Session cancelled.")
            return

        # Create initial state
        initial_state = self._create_initial_state(message)

        # Track cancellation in a task-safe way
        cancelled = False

        try:
            # Use both "updates" (node outputs) and "custom" (get_stream_writer)
            # modes so nodes can stream events in real time via the writer.
            # Without "custom", all events from a long-running node (e.g.
            # research pipeline) would be buffered until the node finishes.
            async for chunk in self._graph.astream(
                initial_state,
                config=self.checkpoint_config,
                stream_mode=["updates", "custom"],
            ):
                # Check for cancellation periodically
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break

                # With multiple stream modes, astream yields (mode, data) tuples
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, data = chunk
                else:
                    # Backwards compat: single mode yielded chunks directly
                    mode, data = "updates", chunk

                if mode == "custom":
                    # Custom event from get_stream_writer() in a node
                    event = self._custom_chunk_to_event(data)
                    if event is not None:
                        yield event
                else:
                    # Standard node output — extract pending_events
                    for event in self._extract_events(data):
                        if not hasattr(event, "turn_id") or event.turn_id is None:
                            event.turn_id = None
                        yield event
                        if isinstance(event, DoneEvent):
                            return

        except asyncio.CancelledError:
            logger.info("Graph run cancelled for session %s", self.session_id)
            yield ErrorEvent(code="CANCELLED", message="Session was cancelled")
            yield DoneEvent(summary="Session cancelled.")
            raise

        except Exception as exc:
            logger.exception("Graph run failed: %s", exc)
            yield ErrorEvent(code="GRAPH_ERROR", message=f"Graph failed: {exc}")
            yield DoneEvent(summary="Graph execution failed.")

    def _create_initial_state(self, message: str) -> AssistantGraphState:
        """Create initial graph state for a new run.

        Args:
            message: The user's message.

        Returns:
            A new AssistantGraphState instance.
        """
        from datetime import datetime, timezone

        return AssistantGraphState(
            session_id=self.session_id,
            user_id=self.user_id,
            project_context=self.project_context,
            messages=[{"role": "user", "content": message}],
            max_iterations=self.config.max_iterations,
            max_wall_time_seconds=self.config.max_wall_time_seconds,
            start_time=datetime.now(timezone.utc),
        )

    def _extract_events(self, chunk: Any) -> List[BaseEvent]:
        """Extract SSE-compatible events from graph output chunk.

        Args:
            chunk: The output from a graph node.

        Returns:
            List of BaseEvent objects.
        """
        events: List[BaseEvent] = []

        # Handle different chunk formats from LangGraph astream
        # Format 1: {'node_name': {'pending_events': [...], ...}}
        # Format 2: {'pending_events': [...], ...} (direct dict)
        if isinstance(chunk, dict):
            # Check if this is a node_name -> node_output mapping
            first_value = next((v for v in chunk.values() if isinstance(v, dict)), None)
            if first_value is not None and "pending_events" not in chunk:
                # This is a node_name mapping, extract from each node's output
                for value in chunk.values():
                    if isinstance(value, dict):
                        self._extract_from_dict(value, events)
            else:
                # Direct dict with pending_events
                self._extract_from_dict(chunk, events)

        return events

    def _extract_from_dict(self, data: Dict[str, Any], events: List[BaseEvent]) -> None:
        """Extract events from a node output dict.

        Args:
            data: Node output dict.
            events: List to append events to.
        """
        from app.agents.assistant.events import (
            AssistantDeltaEvent,
            DoneEvent,
            ErrorEvent,
            IterationEvent,
            MessageEvent,
            ThoughtEvent,
            TitleEvent,
            ToolEvent,
            WaitEvent,
        )

        if "pending_events" not in data:
            return

        for raw_event in data["pending_events"]:
            # raw_event might be a dict or already a BaseEvent
            if isinstance(raw_event, BaseEvent):
                events.append(raw_event)
            elif isinstance(raw_event, dict):
                try:
                    event = self._dict_to_event(raw_event)
                    if event:
                        events.append(event)
                except Exception as exc:
                    logger.warning("Failed to convert event dict: %s", exc)

    def _custom_chunk_to_event(self, data: Any) -> BaseEvent | None:
        """Convert a custom stream chunk (from ``get_stream_writer()``) to a BaseEvent.

        Long-running nodes (e.g. ``research_pipeline_node``) call
        ``get_stream_writer().write(event.model_dump())`` so the FE sees
        events in real time instead of waiting for the whole node to
        finish. The dict written by the node has the same shape as a
        Pydantic-serialized BaseEvent, so we reuse ``_dict_to_event``.

        Args:
            data: The dict that was passed to the stream writer.

        Returns:
            A BaseEvent instance, or None if the chunk can't be converted.
        """
        from app.agents.assistant.events import BaseEvent
        if isinstance(data, BaseEvent):
            return data
        if not isinstance(data, dict):
            return None
        if "type" not in data:
            return None
        return self._dict_to_event(data)

    def _dict_to_event(self, data: Dict[str, Any]) -> BaseEvent | None:
        """Convert a dict to the appropriate BaseEvent subclass.

        Args:
            data: Event data dict.

        Returns:
            A BaseEvent subclass instance, or None if conversion fails.
        """
        from app.agents.assistant.events import (
            AssistantDeltaEvent,
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

        event_type = data.get("type", "")

        try:
            if event_type == "message":
                return MessageEvent(**data)
            elif event_type == "assistant_delta":
                return AssistantDeltaEvent(**data)
            elif event_type == "progress":
                return ProgressEvent(**data)
            elif event_type == "tool":
                return ToolEvent(**data)
            elif event_type == "done":
                return DoneEvent(**data)
            elif event_type == "error":
                return ErrorEvent(**data)
            elif event_type == "wait":
                return WaitEvent(**data)
            elif event_type == "iteration":
                return IterationEvent(**data)
            elif event_type == "thought":
                return ThoughtEvent(**data)
            elif event_type == "title":
                return TitleEvent(**data)
            else:
                logger.debug("Unknown event type: %s", event_type)
                return None
        except Exception as exc:
            logger.warning("Failed to create event %s: %s", event_type, exc)
            return None


# ── Factory Function ──────────────────────────────────────────────────────────


def create_graph_runner(
    session_id: UUID,
    user_id: UUID,
    project_context: Dict[str, Any] | None,
    tools: List["BaseTool"],
    provider: "AIProvider",
    config: AssistantGraphConfig | None = None,
) -> GraphRunner:
    """Create a GraphRunner instance for the assistant.

    This is the main entry point for creating a graph-based runner.
    It configures the graph with the user's tools and context.

    Args:
        session_id: The assistant session UUID.
        user_id: The user UUID.
        project_context: Optional project context dict.
        tools: List of available tools.
        provider: AI provider instance.
        config: Optional graph configuration.

    Returns:
        A GraphRunner instance ready to run.
    """
    # Update config with tools if provided
    if config is None:
        config = AssistantGraphConfig()
    if tools and not config.tools:
        config.tools = tools  # type: ignore

    return GraphRunner(
        session_id=session_id,
        user_id=user_id,
        project_context=project_context,
        tools=tools,
        provider=provider,
        config=config,
    )


# ── Convenience Functions ─────────────────────────────────────────────────────


def is_graph_enabled() -> bool:
    """Check if the graph-based runner is enabled (default: True).

    Returns:
        True if LangGraph runner should be used (default).
        Set USE_REACT_AGENT=true to disable and use legacy ReActAgent.
    """
    return USE_LANGGRAPH


def get_runner_class():
    """Get the appropriate runner class based on feature flag.

    Returns:
        GraphRunner if enabled, None if using ReActAgent.
    """
    if USE_LANGGRAPH:
        return GraphRunner
    return None
