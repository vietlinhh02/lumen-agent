"""
Assistant agent package.

Contains the ReActAgent that implements the ReAct (Reasoning + Acting)
loop for the Lumen Assistant.

Usage:
    from app.agents.assistant import ReActAgent
"""

from __future__ import annotations

from app.agents.assistant.react.agent import ReActAgent, ProjectContext

__all__ = [
    "ReActAgent",
    "ProjectContext",
]
