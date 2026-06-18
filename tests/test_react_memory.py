"""Tests for the Scratchpad and ToolCache modules."""

import pytest

from app.agents.assistant.react.memory import (
    Scratchpad,
    ToolCache,
    _stable_hash,
)


class TestToolCache:
    """Test the ToolCache class."""

    @pytest.fixture
    def cache(self) -> ToolCache:
        return ToolCache()

    def test_make_key_same_args_same_hash(self, cache: ToolCache) -> None:
        """Same tool + same args → same key."""
        key1 = cache.make_key("search_papers", {"query": "AI", "max": 10})
        key2 = cache.make_key("search_papers", {"query": "AI", "max": 10})
        assert key1 == key2

    def test_make_key_different_args_different_hash(self, cache: ToolCache) -> None:
        """Different args → different key."""
        key1 = cache.make_key("search_papers", {"query": "AI"})
        key2 = cache.make_key("search_papers", {"query": "ML"})
        assert key1 != key2

    def test_make_key_different_tool_different_hash(self, cache: ToolCache) -> None:
        """Different tool → different key."""
        key1 = cache.make_key("search_papers", {"query": "AI"})
        key2 = cache.make_key("list_projects", {"query": "AI"})
        assert key1 != key2

    def test_make_key_arg_order_independent(self, cache: ToolCache) -> None:
        """Arg order doesn't matter for hashing."""
        key1 = cache.make_key("search_papers", {"a": 1, "b": 2})
        key2 = cache.make_key("search_papers", {"b": 2, "a": 1})
        assert key1 == key2

    def test_set_and_get(self, cache: ToolCache) -> None:
        """Basic set/get works."""
        cache.set("search_papers", {"query": "AI"}, [{"title": "Paper 1"}])
        result = cache.get("search_papers", {"query": "AI"})
        assert result == [{"title": "Paper 1"}]

    def test_get_nonexistent(self, cache: ToolCache) -> None:
        """Get non-existent key returns None."""
        result = cache.get("unknown_tool", {})
        assert result is None

    def test_has(self, cache: ToolCache) -> None:
        """has() correctly checks existence."""
        cache.set("search_papers", {"query": "AI"}, [{"title": "Paper"}])
        assert cache.has("search_papers", {"query": "AI"}) is True
        assert cache.has("search_papers", {"query": "ML"}) is False
        assert cache.has("list_projects", {}) is False

    def test_clear(self, cache: ToolCache) -> None:
        """clear() removes all entries."""
        cache.set("tool1", {}, "result1")
        cache.set("tool2", {}, "result2")
        assert len(cache) == 2

        cache.clear()
        assert len(cache) == 0

    def test_len(self, cache: ToolCache) -> None:
        """len() returns correct count."""
        assert len(cache) == 0
        cache.set("tool1", {}, "r1")
        assert len(cache) == 1
        cache.set("tool2", {}, "r2")
        assert len(cache) == 2

    def test_overwrite_caches_new_value(self, cache: ToolCache) -> None:
        """Setting same key overwrites with new value."""
        cache.set("search_papers", {"query": "AI"}, [{"title": "Old"}])
        cache.set("search_papers", {"query": "AI"}, [{"title": "New"}])
        result = cache.get("search_papers", {"query": "AI"})
        assert result == [{"title": "New"}]

    def test_nested_dict_hashing(self, cache: ToolCache) -> None:
        """Nested dicts are hashed consistently."""
        key1 = cache.make_key("tool", {"nested": {"a": 1, "b": [1, 2]}})
        key2 = cache.make_key("tool", {"nested": {"b": [1, 2], "a": 1}})
        assert key1 == key2


class TestStableHash:
    """Test the _stable_hash function."""

    def test_same_input_same_hash(self) -> None:
        """Same dict → same hash."""
        h1 = _stable_hash({"a": 1, "b": 2})
        h2 = _stable_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_different_input_different_hash(self) -> None:
        """Different dict → different hash."""
        h1 = _stable_hash({"a": 1})
        h2 = _stable_hash({"b": 1})
        assert h1 != h2

    def test_order_independent(self) -> None:
        """Key order doesn't affect hash."""
        h1 = _stable_hash({"x": 1, "y": 2, "z": 3})
        h2 = _stable_hash({"z": 3, "x": 1, "y": 2})
        assert h1 == h2

    def test_hash_length(self) -> None:
        """Hash is 16 characters (truncated SHA256)."""
        h = _stable_hash({"test": "data"})
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestScratchpad:
    """Test the Scratchpad class."""

    @pytest.fixture
    def scratchpad(self) -> Scratchpad:
        return Scratchpad()

    # ── Cache operations ───────────────────────────────────────────────────────

    def test_get_cached_returns_cached_result(
        self, scratchpad: Scratchpad
    ) -> None:
        """add_to_cache + get_cached roundtrip works."""
        scratchpad.add_to_cache(
            "search_papers",
            {"query": "AI"},
            [{"title": "Paper 1"}],
        )
        result = scratchpad.get_cached("search_papers", {"query": "AI"})
        assert result == [{"title": "Paper 1"}]

    def test_get_cached_returns_none_for_missing(
        self, scratchpad: Scratchpad
    ) -> None:
        """get_cached returns None for non-existent key."""
        result = scratchpad.get_cached("unknown_tool", {})
        assert result is None

    def test_same_tool_same_args_returns_cached(
        self, scratchpad: Scratchpad
    ) -> None:
        """Identical (tool, args) returns cached result - this is the key feature!"""
        scratchpad.add_observation(
            "search_papers",
            {"query": "AI", "max_results": 10},
            [{"title": "Cached Paper"}],
        )

        # Second call with same args should return cached
        cached = scratchpad.get_cached(
            "search_papers",
            {"query": "AI", "max_results": 10},
        )
        assert cached == [{"title": "Cached Paper"}]

    def test_different_args_returns_none(
        self, scratchpad: Scratchpad
    ) -> None:
        """Different args → fresh execution (not cached)."""
        scratchpad.add_observation(
            "search_papers",
            {"query": "AI"},
            [{"title": "AI Papers"}],
        )

        # Different query → should NOT be cached
        cached = scratchpad.get_cached("search_papers", {"query": "ML"})
        assert cached is None

    # ── RAG context ────────────────────────────────────────────────────────────

    def test_add_context(self, scratchpad: Scratchpad) -> None:
        """add_context stores chunks."""
        chunks = ["chunk 1 content", "chunk 2 content"]
        scratchpad.add_context(chunks)
        assert scratchpad.rag_chunks == chunks

    def test_add_context_replaces_previous(self, scratchpad: Scratchpad) -> None:
        """add_context replaces previous chunks."""
        scratchpad.add_context(["old chunk"])
        scratchpad.add_context(["new chunk"])
        assert scratchpad.rag_chunks == ["new chunk"]

    def test_to_messages_includes_rag_context(
        self, scratchpad: Scratchpad
    ) -> None:
        """to_messages() includes RAG chunks when present."""
        scratchpad.add_context(["[Context 1]\nSome relevant content"])
        messages = scratchpad.to_messages()

        assert len(messages) == 1
        assert "Context 1" in messages[0]["content"]
        assert "Some relevant content" in messages[0]["content"]

    # ── Trace operations ─────────────────────────────────────────────────────

    def test_add_thought(self, scratchpad: Scratchpad) -> None:
        """add_thought adds to trace."""
        scratchpad.add_thought("I should search for papers")
        assert scratchpad.trace_length == 1
        assert scratchpad.trace[0]["type"] == "thought"
        assert scratchpad.trace[0]["content"] == "I should search for papers"

    def test_add_observation(self, scratchpad: Scratchpad) -> None:
        """add_observation adds to trace and caches."""
        scratchpad.add_observation(
            "search_papers",
            {"query": "AI"},
            [{"title": "Paper 1"}],
        )

        assert scratchpad.trace_length == 1
        assert scratchpad.trace[0]["type"] == "observation"
        assert scratchpad.trace[0]["tool"] == "search_papers"
        assert scratchpad.trace[0]["result"] == [{"title": "Paper 1"}]

        # Also cached
        assert scratchpad.get_cached("search_papers", {"query": "AI"}) == [
            {"title": "Paper 1"}
        ]

    def test_trace_maintains_order(self, scratchpad: Scratchpad) -> None:
        """Trace entries are in chronological order."""
        scratchpad.add_thought("Step 1")
        scratchpad.add_observation("tool1", {}, "result1")
        scratchpad.add_thought("Step 2")
        scratchpad.add_observation("tool2", {}, "result2")

        trace = scratchpad.trace
        assert trace[0]["type"] == "thought"
        assert trace[0]["content"] == "Step 1"
        assert trace[1]["type"] == "observation"
        assert trace[2]["type"] == "thought"
        assert trace[2]["content"] == "Step 2"
        assert trace[3]["type"] == "observation"

    # ── Message rendering ──────────────────────────────────────────────────────

    def test_to_messages_empty_scratchpad(self, scratchpad: Scratchpad) -> None:
        """Empty scratchpad returns empty messages."""
        messages = scratchpad.to_messages()
        assert messages == []

    def test_to_messages_includes_trace(self, scratchpad: Scratchpad) -> None:
        """to_messages() includes formatted trace."""
        scratchpad.add_observation(
            "list_projects",
            {},
            [{"id": "p1", "name": "My Project"}],
        )
        messages = scratchpad.to_messages()

        assert len(messages) == 1
        assert "list_projects" in messages[0]["content"]
        assert "My Project" in messages[0]["content"]

    def test_to_messages_combines_context_and_trace(
        self, scratchpad: Scratchpad
    ) -> None:
        """Both RAG context and trace appear in messages."""
        scratchpad.add_context(["Context chunk"])
        scratchpad.add_observation("tool", {}, "result")

        messages = scratchpad.to_messages()
        assert len(messages) == 2  # One for context, one for trace
        assert "Context chunk" in messages[0]["content"]
        assert "tool" in messages[1]["content"]

    def test_to_messages_respects_token_limit(self, scratchpad: Scratchpad) -> None:
        """to_messages() truncates if over 8k tokens."""
        # Add many large observations
        large_result = "x" * 100_000  # ~25k tokens
        scratchpad.add_observation("tool", {}, large_result)
        scratchpad.add_observation("tool", {}, large_result)
        scratchpad.add_observation("tool", {}, large_result)

        messages = scratchpad.to_messages()
        total_content = "\n".join(m.get("content", "") for m in messages)

        # Should be truncated (well under 100k chars)
        assert len(total_content) < 50_000

    # ── Truncation ────────────────────────────────────────────────────────────

    def test_truncate_long_string(self, scratchpad: Scratchpad) -> None:
        """Long strings are truncated with marker."""
        long_text = "x" * 10_000
        truncated = scratchpad._truncate(long_text, max_tokens=500)

        assert len(truncated) < 5_000  # Should be much shorter
        assert "...[truncated]" in truncated

    def test_truncate_dict(self, scratchpad: Scratchpad) -> None:
        """Dicts are truncated via repr."""
        large_dict = {"key": "x" * 10_000}
        truncated = scratchpad._truncate(large_dict, max_tokens=500)

        assert isinstance(truncated, str)
        assert "...[truncated]" in truncated

    def test_observation_truncated_at_500_tokens(
        self, scratchpad: Scratchpad
    ) -> None:
        """Observations over 500 tokens are truncated."""
        large_result = [{"content": "x" * 100_000}]
        scratchpad.add_observation("tool", {}, large_result)

        observation = scratchpad.trace[0]
        result_str = str(observation["result"])
        assert "...[truncated]" in result_str

    # ── Properties ────────────────────────────────────────────────────────────

    def test_cache_size_property(self, scratchpad: Scratchpad) -> None:
        """cache_size returns number of cached items."""
        assert scratchpad.cache_size == 0
        scratchpad.add_to_cache("tool1", {}, "r1")
        assert scratchpad.cache_size == 1
        scratchpad.add_to_cache("tool2", {}, "r2")
        assert scratchpad.cache_size == 2

    def test_trace_length_property(self, scratchpad: Scratchpad) -> None:
        """trace_length returns number of trace entries."""
        assert scratchpad.trace_length == 0
        scratchpad.add_thought("think")
        assert scratchpad.trace_length == 1
        scratchpad.add_observation("tool", {}, "result")
        assert scratchpad.trace_length == 2

    def test_reset(self, scratchpad: Scratchpad) -> None:
        """reset() clears everything."""
        scratchpad.add_context(["chunk"])
        scratchpad.add_observation("tool", {}, "result")
        scratchpad.add_thought("think")

        assert scratchpad.cache_size > 0
        assert scratchpad.trace_length > 0

        scratchpad.reset()

        assert scratchpad.cache_size == 0
        assert scratchpad.trace_length == 0
        assert scratchpad.rag_chunks == []
        assert scratchpad.estimated_tokens == 0

    def test_estimated_tokens_accumulates(
        self, scratchpad: Scratchpad
    ) -> None:
        """estimated_tokens increases as content is added."""
        initial = scratchpad.estimated_tokens
        scratchpad.add_thought("Short thought")
        assert scratchpad.estimated_tokens > initial

    # ── Edge cases ─────────────────────────────────────────────────────────────

    def test_add_observation_with_none_result(
        self, scratchpad: Scratchpad
    ) -> None:
        """None results are handled correctly."""
        scratchpad.add_observation("tool", {}, None)
        assert scratchpad.trace[0]["result"] is None

    def test_add_observation_with_error_result(
        self, scratchpad: Scratchpad
    ) -> None:
        """Error results (strings starting with Error) are stored."""
        scratchpad.add_observation(
            "tool",
            {},
            "Error: Something went wrong",
        )
        # Error results should still be cached and stored
        assert scratchpad.get_cached("tool", {}) == "Error: Something went wrong"

    def test_empty_context_to_messages(self, scratchpad: Scratchpad) -> None:
        """Empty scratchpad with no trace returns empty list."""
        messages = scratchpad.to_messages()
        assert messages == []

    def test_format_trace_readable(self, scratchpad: Scratchpad) -> None:
        """_format_trace produces readable output."""
        scratchpad.add_thought("I should search")
        scratchpad.add_observation(
            "search_papers",
            {"query": "AI"},
            [{"title": "Test"}],
        )

        trace_text = scratchpad._format_trace()

        assert "Thought: I should search" in trace_text
        assert "Action: search_papers" in trace_text
        assert "query" in trace_text
        assert "Test" in trace_text
