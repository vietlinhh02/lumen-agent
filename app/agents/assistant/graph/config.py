"""Configuration for the LangGraph assistant runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_MAX_ITERATIONS = 15
DEFAULT_MAX_WALL_TIME_SECONDS = 600
DEFAULT_HEARTBEAT_SECONDS = 15

# Default checkpointer DB path (relative to project root)
DEFAULT_CHECKPOINT_DB = os.environ.get(
    "ASSISTANT_CHECKPOINT_DB",
    "data/assistant_checkpoints.db",
)


# ── Config Dataclass ────────────────────────────────────────────────────────


@dataclass
class AssistantGraphConfig:
    """Configuration for the assistant graph runtime.

    Attributes:
        max_iterations: Maximum ReAct iterations per turn.
        max_wall_time_seconds: Maximum wall time for a run.
        heartbeat_seconds: Heartbeat interval for long LLM calls.
        checkpointer: LangGraph checkpointer instance (SQLite, Memory, etc.).
        tools: List of available tools for the agent.
    """

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_wall_time_seconds: int = DEFAULT_MAX_WALL_TIME_SECONDS
    heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS
    checkpointer: "BaseCheckpointSaver | None" = None
    tools: list = field(default_factory=list)


# ── Checkpointer Factory ────────────────────────────────────────────────────


def create_sqlite_checkpointer(
    db_path: str | None = None,
) -> "BaseCheckpointSaver":
    """Create a SQLite checkpointer for assistant state persistence.

    SQLite is suitable for:
    - Single-instance deployments
    - Development/testing
    - Low-to-medium traffic applications

    For multi-instance production deployments, use PostgreSQL via
    `langgraph-checkpoint-postgres` package.

    NOTE: Requires `langgraph-checkpoint-sqlite` package:
        pip install langgraph-checkpoint-sqlite

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A SqliteSaver checkpointer instance.
    """
    import os

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        raise ImportError(
            "SQLite checkpointer requires `langgraph-checkpoint-sqlite` package. "
            "Install with: pip install langgraph-checkpoint-sqlite, "
            "or use USE_MEMORY_CHECKPOINTER=true for testing."
        )

    path = db_path or DEFAULT_CHECKPOINT_DB

    # Ensure directory exists
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    return SqliteSaver.from_conn_string(f"sqlite+aiosqlite:///{path}")


def create_memory_checkpointer() -> "BaseCheckpointSaver":
    """Create an in-memory checkpointer for testing.

    WARNING: State is NOT persisted across server restarts.
    Use only for testing or single-session ephemeral deployments.

    Returns:
        A MemorySaver checkpointer instance.
    """
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def get_checkpointer(
    use_memory: bool = False,
    db_path: str | None = None,
) -> "BaseCheckpointSaver":
    """Get the checkpointer based on environment.

    Priority:
    1. If use_memory=True or USE_MEMORY_CHECKPOINTER=true, use MemorySaver
    2. If ASSISTANT_CHECKPOINT_DB is set, use SQLite at that path
    3. Otherwise fall back to MemorySaver (SQLite requires separate package)

    For production with persistence:
        pip install langgraph-checkpoint-sqlite  # For SQLite
        pip install langgraph-checkpoint-postgres  # For PostgreSQL

    Args:
        use_memory: Force use of memory checkpointer.
        db_path: Override the database path.

    Returns:
        A checkpointer instance.
    """
    if use_memory or os.environ.get("USE_MEMORY_CHECKPOINTER") == "true":
        return create_memory_checkpointer()

    # Try SQLite if path is explicitly provided
    if db_path:
        try:
            return create_sqlite_checkpointer(db_path)
        except ImportError:
            logger.warning(
                "SQLite checkpointer not available. "
                "Install with: pip install langgraph-checkpoint-sqlite. "
                "Falling back to MemorySaver."
            )

    # Default to memory for now (no persistence across restarts)
    # TODO: When SQLite package is installed, use it by default
    return create_memory_checkpointer()
