"""
Tests for assistant tools context propagation.

Verifies:
- ContextVars are set per-request (not per-process)
- Concurrent users have isolated contexts
- UserContextVar context manager works correctly
- Context can be cleared
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Thread

import pytest

from app.agents.assistant.tools.context import (
    UserContext,
    UserContextVar,
    clear_user_context,
    get_project_id,
    get_user,
    get_user_context,
    get_user_id,
    set_user_context,
)


class TestSetAndGetContext:
    """Tests for basic set/get context operations."""

    def test_set_and_get_user_id(self):
        """Can set and get user_id."""
        clear_user_context()
        set_user_context(user_id="user-123")
        assert get_user_id() == "user-123"
        clear_user_context()  # cleanup

    def test_set_and_get_project_id(self):
        """Can set and get project_id."""
        clear_user_context()
        set_user_context(project_id="proj-456")
        assert get_project_id() == "proj-456"
        clear_user_context()

    def test_set_both_context_values(self):
        """Can set both user_id and project_id."""
        clear_user_context()
        set_user_context(user_id="user-123", project_id="proj-456")
        assert get_user_id() == "user-123"
        assert get_project_id() == "proj-456"
        clear_user_context()

    def test_get_user_context_returns_all(self):
        """get_user_context returns complete context."""
        clear_user_context()
        set_user_context(user_id="u1", project_id="p1")
        ctx = get_user_context()
        assert ctx.user_id == "u1"
        assert ctx.project_id == "p1"
        clear_user_context()

    def test_clear_context(self):
        """clear_user_context resets all values to None."""
        set_user_context(user_id="u1", project_id="p1")
        clear_user_context()
        assert get_user_id() is None
        assert get_project_id() is None
        assert get_user() is None

    def test_initial_context_is_none(self):
        """Initial context is None before any set_user_context call."""
        clear_user_context()
        assert get_user_id() is None
        assert get_project_id() is None


class TestUserContextVar:
    """Tests for UserContextVar context manager."""

    def test_context_var_temporarily_sets_context(self):
        """UserContextVar temporarily changes context within the block."""
        set_user_context(user_id="outer-user", project_id="outer-proj")
        try:
            with UserContextVar(user_id="inner-user", project_id="inner-proj"):
                assert get_user_id() == "inner-user"
                assert get_project_id() == "inner-proj"
            # After block, context is restored
            assert get_user_id() == "outer-user"
            assert get_project_id() == "outer-proj"
        finally:
            clear_user_context()

    def test_context_var_restores_on_exception(self):
        """Context is restored even if an exception occurs."""
        set_user_context(user_id="outer-user", project_id="outer-proj")
        try:
            with UserContextVar(user_id="inner-user"):
                assert get_user_id() == "inner-user"
                raise ValueError("Test exception")
        except ValueError:
            pass
        # Context should be restored
        assert get_user_id() == "outer-user"
        clear_user_context()

    def test_context_var_partial_context(self):
        """UserContextVar only sets provided values, leaves others unchanged."""
        set_user_context(user_id="user-only")
        try:
            with UserContextVar(project_id="proj-added"):
                assert get_user_id() == "user-only"
                assert get_project_id() == "proj-added"
        finally:
            clear_user_context()

    def test_nested_context_vars(self):
        """Nested UserContextVars work correctly."""
        set_user_context(user_id="level-0")
        try:
            with UserContextVar(user_id="level-1"):
                assert get_user_id() == "level-1"
                with UserContextVar(user_id="level-2"):
                    assert get_user_id() == "level-2"
                assert get_user_id() == "level-1"
            assert get_user_id() == "level-0"
        finally:
            clear_user_context()


class TestConcurrentIsolation:
    """Tests that context is isolated between concurrent operations."""

    def test_async_tasks_have_isolated_context(self):
        """Async tasks should maintain their own context."""
        results: dict = {}

        async def task(task_id: str, user_id: str):
            set_user_context(user_id=user_id)
            await asyncio.sleep(0.05)  # Yield to event loop
            results[task_id] = get_user_id()
            clear_user_context()

        # Create a new event loop for Python 3.14+ compatibility
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(asyncio.gather(
                task("task-1", "user-A"),
                task("task-2", "user-B"),
                task("task-3", "user-C"),
            ))
        finally:
            loop.close()

        # Each task should have its own user_id
        assert results["task-1"] == "user-A"
        assert results["task-2"] == "user-B"
        assert results["task-3"] == "user-C"

    def test_threading_isolates_context(self):
        """Each thread should see only its own context."""
        results: dict = {}

        def thread_worker(task_id: str, user_id: str):
            set_user_context(user_id=user_id)
            # Do some work
            for _ in range(100):
                pass
            results[task_id] = get_user_id()
            clear_user_context()

        threads = [
            Thread(target=thread_worker, args=(f"t{i}", f"user-{i}"))
            for i in range(3)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each thread should have its own user_id
        for i in range(3):
            assert results[f"t{i}"] == f"user-{i}"


class TestUserContext:
    """Tests for UserContext dataclass."""

    def test_user_context_creation(self):
        """Can create UserContext with all fields."""
        ctx = UserContext(user_id="u1", project_id="p1", user=None)
        assert ctx.user_id == "u1"
        assert ctx.project_id == "p1"
        assert ctx.user is None

    def test_user_context_repr(self):
        """UserContext __repr__ is informative."""
        ctx = UserContext(user_id="u1", project_id="p1")
        r = repr(ctx)
        assert "u1" in r
        assert "p1" in r


class TestContextIsolationFromMainProcess:
    """Verify context doesn't leak from/to main process."""

    def test_main_process_context_isolation(self):
        """Main process context should not affect tests."""
        # Ensure clean slate
        clear_user_context()

        # Set context in this test
        set_user_context(user_id="test-user")
        assert get_user_id() == "test-user"

        # Clear for next test
        clear_user_context()
        assert get_user_id() is None
