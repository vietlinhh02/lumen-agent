"""Tests for assistant graph nodes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.assistant.graph.nodes import classification_node
from app.agents.assistant.graph.state import AssistantGraphState
from app.agents.assistant.react.router import Intent


@pytest.mark.asyncio
async def test_classification_node_bypasses_when_already_set() -> None:
    """Should skip classification if current_intent is already set and valid."""
    state = AssistantGraphState(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        messages=[{"role": "user", "content": "hello"}],
        current_intent="chitchat",
    )
    
    result = await classification_node(state)
    assert result["current_intent"] == "chitchat"
    assert result["pending_events"] == []


@pytest.mark.asyncio
async def test_classification_node_runs_classification_when_none() -> None:
    """Should run classification if current_intent is None."""
    state = AssistantGraphState(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        messages=[{"role": "user", "content": "hello"}],
        current_intent=None,
    )
    
    with patch("app.agents.assistant.graph.nodes.FastRouter") as mock_router_class:
        mock_router = MagicMock()
        mock_router.classify = AsyncMock(return_value=Intent.RAG_QA)
        mock_router_class.return_value = mock_router
        
        result = await classification_node(state)
        assert result["current_intent"] == "rag_qa"
        assert len(result["pending_events"]) == 1
        assert result["pending_events"][0].phase == "reasoning"


@pytest.mark.asyncio
async def test_classification_node_runs_classification_when_unknown() -> None:
    """Should run classification if current_intent is 'unknown'."""
    state = AssistantGraphState(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        messages=[{"role": "user", "content": "hello"}],
        current_intent="unknown",
    )
    
    with patch("app.agents.assistant.graph.nodes.FastRouter") as mock_router_class:
        mock_router = MagicMock()
        mock_router.classify = AsyncMock(return_value=Intent.RAG_QA)
        mock_router_class.return_value = mock_router
        
        result = await classification_node(state)
        assert result["current_intent"] == "rag_qa"
