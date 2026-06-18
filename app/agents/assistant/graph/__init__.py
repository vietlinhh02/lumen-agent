"""LangGraph-based assistant runtime with checkpointing.

This module provides a LangGraph-based agent runtime for the assistant,
with checkpointing support for reliable wait/resume and interruption recovery.

Enable via: USE_LANGGRAPH_ASSISTANT=true environment variable.

Usage:
    from app.agents.assistant.graph import get_assistant_graph, GraphRunner

    graph = get_assistant_graph()
    
    runner = create_graph_runner(session_id, user_id, project_context, tools, provider)
    async for event in runner.run(message, resume=resume):
        yield event
"""

from app.agents.assistant.graph.adapter import (
    create_graph_runner,
    GraphRunner,
    is_graph_enabled,
)
from app.agents.assistant.graph.config import AssistantGraphConfig, get_checkpointer
from app.agents.assistant.graph.graph import get_assistant_graph, AssistantGraph
from app.agents.assistant.graph.state import AssistantGraphState, ScratchpadEntry

__all__ = [
    # Adapter
    "create_graph_runner",
    "GraphRunner",
    "is_graph_enabled",
    # Config
    "AssistantGraphConfig",
    "get_checkpointer",
    # Graph
    "AssistantGraph",
    "get_assistant_graph",
    # State
    "AssistantGraphState",
    "ScratchpadEntry",
]
