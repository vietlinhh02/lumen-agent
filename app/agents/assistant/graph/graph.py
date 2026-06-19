"""LangGraph compilation for the assistant agent.

This module compiles the assistant graph with checkpointing support.
The graph replaces the custom ReAct loop in react/agent.py.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import UTC
from typing import Any, Literal
from uuid import UUID

from langgraph.graph import END, StateGraph

from app.agents.assistant.events import BaseEvent
from app.agents.assistant.graph.config import (
    AssistantGraphConfig,
    get_checkpointer,
)
from app.agents.assistant.graph.deep_search import deep_search_node
from app.agents.assistant.graph.nodes import (
    classification_node,
    direct_tool_node,
    final_answer_node,
    react_loop_node,
    research_pipeline_node,
    should_continue_react,
    simple_chat_node,
)
from app.agents.assistant.graph.state import AssistantGraphState

logger = logging.getLogger(__name__)


# ── Graph Builder ────────────────────────────────────────────────────────────


def build_assistant_graph(
    config: AssistantGraphConfig | None = None,
) -> Any:  # Returns CompiledStateGraph
    """Build and compile the assistant LangGraph.

    Graph topology::

        start → classification
                    │
                    ├── chitchat ──→ simple_chat ──→ END
                    ├── list_* ──────→ direct_tool ──→ END
                    ├── research_pipeline ──→ research_pipeline_node ──→ END
                    └── other ───────→ react_loop ──┬─→ react_loop (more iterations)
                                                   └─→ final_answer → END

    Args:
        config: Optional graph configuration.

    Returns:
        A compiled LangGraph instance.
    """
    config = config or AssistantGraphConfig()
    graph = StateGraph(AssistantGraphState)

    # ── Add all nodes ─────────────────────────────────────────────────────
    graph.add_node("classification", classification_node)
    graph.add_node("simple_chat", simple_chat_node)
    graph.add_node("deep_search", deep_search_node)
    graph.add_node("direct_tool", direct_tool_node)
    graph.add_node("research_pipeline", research_pipeline_node)
    graph.add_node("react_loop", react_loop_node)
    graph.add_node("final_answer", final_answer_node)

    # ── Set entry point ────────────────────────────────────────────────────
    graph.set_entry_point("classification")

    # ── Classification routing ──────────────────────────────────────────────
    def route_from_classification(state: AssistantGraphState) -> str:
        intent = state.current_intent or "chitchat"

        if intent in ("chitchat", "greeting", "ambiguous"):
            return "simple_chat"
        elif intent == "search":
            return "deep_search"
        elif intent.startswith("list_"):
            return "direct_tool"
        elif intent == "research_pipeline":
            return "research_pipeline"
        else:
            return "react_loop"

    graph.add_conditional_edges(
        "classification",
        route_from_classification,
        {
            "simple_chat": "simple_chat",
            "deep_search": "deep_search",
            "direct_tool": "direct_tool",
            "research_pipeline": "research_pipeline",
            "react_loop": "react_loop",
        },
    )

    # ── Connect to END ─────────────────────────────────────────────────────
    graph.add_edge("simple_chat", END)
    graph.add_edge("deep_search", END)
    graph.add_edge("direct_tool", END)
    graph.add_edge("research_pipeline", END)

    # ── ReAct loop with conditional continuation ────────────────────────────
    def route_from_react_loop(state: AssistantGraphState) -> Literal["react_loop", "final_answer"]:
        return should_continue_react(state)

    graph.add_conditional_edges(
        "react_loop",
        route_from_react_loop,
        {
            "react_loop": "react_loop",
            "final_answer": "final_answer",
        },
    )

    graph.add_edge("final_answer", END)

    # ── Compile with checkpointer ───────────────────────────────────────────
    checkpointer = config.checkpointer or get_checkpointer()

    compiled = graph.compile(checkpointer=checkpointer)

    # Add configuration to the compiled graph for reference
    compiled.graph_config = config

    return compiled


# ── Module-level compiled graph (lazy initialization) ────────────────────────

_assistant_graph: Any | None = None
_graph_config: AssistantGraphConfig | None = None


def get_assistant_graph(
    config: AssistantGraphConfig | None = None,
    force_rebuild: bool = False,
) -> Any:
    """Get the singleton compiled assistant graph.

    Args:
        config: Optional configuration override.
        force_rebuild: Force rebuild even if cached.

    Returns:
        The compiled LangGraph instance.
    """
    global _assistant_graph, _graph_config

    if _assistant_graph is None or force_rebuild or config is not None:
        _assistant_graph = build_assistant_graph(config)
        _graph_config = config or _graph_config

    return _assistant_graph


def get_graph_config() -> AssistantGraphConfig | None:
    """Get the current graph configuration.

    Returns:
        The current AssistantGraphConfig, or None if not initialized.
    """
    return _graph_config


# ── Async Runner with SSE-compatible Events ─────────────────────────────────


class AssistantGraph:
    """High-level runner for the assistant graph with SSE-compatible event emission.

    This class wraps the compiled LangGraph and provides an async generator
    interface compatible with the existing SSE router.

    Usage:
        graph = get_assistant_graph()

        runner = AssistantGraph(graph)
        async for event in runner.run(session_id, user_id, message):
            yield event
    """

    def __init__(
        self,
        graph: Any,
        config: AssistantGraphConfig | None = None,
    ) -> None:
        """Initialize the runner.

        Args:
            graph: A compiled LangGraph instance.
            config: Optional graph configuration.
        """
        self.graph = graph
        self.config = config or AssistantGraphConfig()

    async def run(
        self,
        session_id: UUID,
        user_id: UUID,
        message: str,
        resume: bool = False,
    ) -> AsyncGenerator[BaseEvent]:
        """Run the assistant graph for a user message.

        This method:
        1. Loads checkpoint if resuming
        2. Creates initial state
        3. Streams through the graph
        4. Yields SSE-compatible events

        Args:
            session_id: The assistant session UUID.
            user_id: The user UUID.
            message: The user's message.
            resume: If True, continue from existing checkpoint.

        Yields:
            BaseEvent subclasses from events.py.
        """
        import asyncio

        from app.agents.assistant.graph.state import AssistantGraphState

        # Build checkpoint config
        checkpoint_config: dict[str, Any] = {
            "configurable": {
                "thread_id": str(session_id),
                "checkpoint_ns": "main",
            }
        }

        # Helper to convert messages to dicts
        def _to_dict(msg: Any) -> dict:
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                result = {"role": msg.type, "content": msg.content}
                if hasattr(msg, 'tool_call_id'):
                    result["tool_call_id"] = msg.tool_call_id
                if hasattr(msg, 'name'):
                    result["name"] = msg.name
                return result
            return msg if isinstance(msg, dict) else {"role": "user", "content": str(msg)}

        # Initial state
        if resume:
            # Load existing checkpoint
            try:
                existing = await self.graph.aget_state(checkpoint_config)
                if existing is not None:
                    # Add new user message to existing state
                    current_messages = list(existing.values.get("messages", []))
                    # Convert any LangChain messages to dicts
                    current_messages = [_to_dict(m) for m in current_messages]
                    current_messages.append({"role": "user", "content": message})

                    initial_state = AssistantGraphState(
                        session_id=session_id,
                        user_id=user_id,
                        messages=current_messages,
                        scratchpad_entries=existing.values.get("scratchpad_entries", []),
                        iteration=existing.values.get("iteration", 0),
                        is_waiting=False,  # Reset waiting on resume
                        max_iterations=self.config.max_iterations,
                        max_wall_time_seconds=self.config.max_wall_time_seconds,
                    )
                else:
                    initial_state = self._create_initial_state(session_id, user_id, message)
            except Exception as exc:
                logger.warning("Failed to load checkpoint, starting fresh: %s", exc)
                initial_state = self._create_initial_state(session_id, user_id, message)
        else:
            initial_state = self._create_initial_state(session_id, user_id, message)

        # Run the graph
        try:
            async for chunk in self.graph.astream(
                initial_state,
                config=checkpoint_config,
                stream_mode=["custom", "updates"],
            ):
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    mode, payload = chunk
                    if mode == "custom":
                        yield payload
                    elif mode == "updates" and isinstance(payload, dict):
                        for _node_name, node_output in payload.items():
                            if isinstance(node_output, dict) and "pending_events" in node_output:
                                for event in node_output["pending_events"]:
                                    yield event

        except asyncio.CancelledError:
            logger.info("Graph run cancelled")
            yield BaseEvent()  # Placeholder for cancellation
            raise

        except Exception as exc:
            logger.exception("Graph run failed: %s", exc)
            from app.agents.assistant.events import DoneEvent, ErrorEvent

            yield ErrorEvent(code="GRAPH_ERROR", message=f"Graph failed: {exc}")
            yield DoneEvent()

    def _create_initial_state(
        self,
        session_id: UUID,
        user_id: UUID,
        message: str,
    ) -> AssistantGraphState:
        """Create initial graph state for a new run.

        Args:
            session_id: The assistant session UUID.
            user_id: The user UUID.
            message: The user's message.

        Returns:
            A new AssistantGraphState instance.
        """
        from datetime import datetime

        return AssistantGraphState(
            session_id=session_id,
            user_id=user_id,
            messages=[{"role": "user", "content": message}],
            max_iterations=self.config.max_iterations,
            max_wall_time_seconds=self.config.max_wall_time_seconds,
            start_time=datetime.now(UTC),
        )


# ── Convenience Functions ───────────────────────────────────────────────────


def create_graph_runner(
    config: AssistantGraphConfig | None = None,
) -> AssistantGraph:
    """Create an AssistantGraph runner instance.

    Args:
        config: Optional graph configuration.

    Returns:
        An AssistantGraph instance ready to run.
    """
    graph = get_assistant_graph(config)
    return AssistantGraph(graph, config)


async def run_with_checkpointing(
    session_id: UUID,
    user_id: UUID,
    message: str,
    config: AssistantGraphConfig | None = None,
    resume: bool = False,
) -> AsyncGenerator[BaseEvent]:
    """Convenience function to run the assistant with checkpointing.

    Args:
        session_id: The assistant session UUID.
        user_id: The user UUID.
        message: The user's message.
        config: Optional graph configuration.
        resume: If True, continue from existing checkpoint.

    Yields:
        BaseEvent subclasses from events.py.
    """
    runner = create_graph_runner(config)
    async for event in runner.run(session_id, user_id, message, resume=resume):
        yield event
