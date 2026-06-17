"""Tests for the Assistant metrics module."""

from __future__ import annotations

import time
from collections import Counter
from uuid import uuid4

import pytest

from app.services.assistant.metrics import (
    AssistantMetrics,
    SessionMetrics,
    metrics,
)


class TestSessionMetrics:
    """Tests for SessionMetrics dataclass."""

    def test_session_metrics_creation(self):
        """Test that SessionMetrics can be created with required fields."""
        session_id = uuid4()
        user_id = uuid4()
        start_time = time.time()

        metrics = SessionMetrics(
            session_id=session_id,
            user_id=user_id,
            start_time=start_time,
        )

        assert metrics.session_id == session_id
        assert metrics.user_id == user_id
        assert metrics.start_time == start_time
        assert metrics.end_time is None
        assert metrics.status == "running"
        assert metrics.step_count == 0
        assert metrics.tokens_used == 0
        assert metrics.tool_calls == Counter()
        assert metrics.steps_by_status == Counter()

    def test_session_metrics_to_dict(self):
        """Test SessionMetrics.to_dict() serialization."""
        session_id = uuid4()
        user_id = uuid4()
        start_time = time.time()

        session_metrics = SessionMetrics(
            session_id=session_id,
            user_id=user_id,
            start_time=start_time,
            end_time=start_time + 60,
            status="completed",
            step_count=5,
            tokens_used=1000,
            tool_calls=Counter({"search_papers": 2, "save_paper": 3}),
            steps_by_status=Counter({"completed": 5}),
        )

        result = session_metrics.to_dict()

        assert result["session_id"] == str(session_id)
        assert result["user_id"] == str(user_id)
        assert result["start_time"] == start_time
        assert result["end_time"] == start_time + 60
        assert result["status"] == "completed"
        assert result["steps_count"] == 5
        assert result["tokens_used"] == 1000
        assert result["tool_calls"] == {"search_papers": 2, "save_paper": 3}
        assert result["wall_time"] == 60


class TestAssistantMetrics:
    """Tests for AssistantMetrics singleton."""

    def setup_method(self):
        """Reset metrics before each test."""
        metrics.reset()

    def test_singleton_pattern(self):
        """Test that AssistantMetrics is a singleton."""
        from app.services.assistant.metrics import AssistantMetrics

        m1 = AssistantMetrics()
        m2 = AssistantMetrics()
        assert m1 is m2

    def test_record_session_created(self):
        """Test recording a new session."""
        session_id = uuid4()
        user_id = uuid4()

        session_metrics = metrics.record_session_created(session_id, user_id)

        assert session_metrics.session_id == session_id
        assert session_metrics.user_id == user_id
        assert metrics.sessions_created == 1

    def test_record_tool_call(self):
        """Test recording tool calls."""
        metrics.record_tool_call("search_papers")
        metrics.record_tool_call("search_papers")
        metrics.record_tool_call("save_paper")

        assert metrics._tool_calls["search_papers"] == 2
        assert metrics._tool_calls["save_paper"] == 1

    def test_record_tokens(self):
        """Test recording token usage."""
        metrics.record_tokens("system", 500)
        metrics.record_tokens("user", 100)
        metrics.record_tokens("assistant", 200)

        assert metrics._tokens_by_role["system"] == 500
        assert metrics._tokens_by_role["user"] == 100
        assert metrics._tokens_by_role["assistant"] == 200

    def test_record_step(self):
        """Test recording step completion."""
        metrics.record_step("completed")
        metrics.record_step("completed")
        metrics.record_step("failed")

        assert metrics._steps_by_status["completed"] == 2
        assert metrics._steps_by_status["failed"] == 1

    def test_active_sessions_tracking(self):
        """Test tracking active sessions per user."""
        user_id = uuid4()

        # Start 3 sessions
        metrics.record_session_created(uuid4(), user_id)
        metrics.record_session_created(uuid4(), user_id)
        metrics.record_session_created(uuid4(), user_id)

        assert metrics.get_active_sessions_count(user_id) == 3

    def test_decrement_active_sessions(self):
        """Test decrementing active sessions."""
        user_id = uuid4()

        # Start sessions
        metrics.record_session_created(uuid4(), user_id)
        metrics.record_session_created(uuid4(), user_id)

        assert metrics.get_active_sessions_count(user_id) == 2

        # Decrement
        metrics.decrement_active_sessions(user_id)
        assert metrics.get_active_sessions_count(user_id) == 1

        # Decrement again
        metrics.decrement_active_sessions(user_id)
        assert metrics.get_active_sessions_count(user_id) == 0

        # Should not go below 0
        metrics.decrement_active_sessions(user_id)
        assert metrics.get_active_sessions_count(user_id) == 0

    def test_record_session_ended(self):
        """Test recording session end with full metrics."""
        session_id = uuid4()
        user_id = uuid4()

        # Record session created
        metrics.record_session_created(session_id, user_id)

        # Simulate session ending
        time.sleep(0.01)  # Small delay to ensure different timestamps
        metrics.record_session_ended(
            session_id=session_id,
            status="completed",
            step_count=5,
            tool_calls=Counter({"search_papers": 2, "save_paper": 3}),
            tokens_used=1500,
        )

        # Check session metrics updated
        session_metrics = metrics.get_session_metrics(session_id)
        assert session_metrics is not None
        assert session_metrics.status == "completed"
        assert session_metrics.step_count == 5
        assert session_metrics.tool_calls == Counter({"search_papers": 2, "save_paper": 3})
        assert session_metrics.tokens_used == 1500
        assert session_metrics.end_time is not None

    def test_get_session_metrics_not_found(self):
        """Test getting metrics for non-existent session."""
        non_existent_id = uuid4()
        result = metrics.get_session_metrics(non_existent_id)
        assert result is None

    def test_get_summary(self):
        """Test getting metrics summary."""
        user_id = uuid4()

        # Create sessions and record metrics
        for i in range(3):
            metrics.record_session_created(uuid4(), user_id)

        metrics.record_tool_call("search_papers")
        metrics.record_tool_call("search_papers")
        metrics.record_tool_call("save_paper")
        metrics.record_tokens("system", 1000)
        metrics.record_step("completed")

        summary = metrics.get_summary()

        assert summary["sessions_created"] == 3
        assert summary["tool_calls_total"] == {"search_papers": 2, "save_paper": 1}
        assert summary["llm_tokens_total"] == {"system": 1000}
        assert "completed" in summary["steps_total"]
