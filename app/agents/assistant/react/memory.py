"""Scratchpad + tool-result cache for the ReAct agent.

Provides:
- Scratchpad: maintains conversation context, RAG chunks, and tool execution trace
- Tool cache: memoizes tool results by (tool_name, stable_hash(args))
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

_MAX_OBSERVATION_TOKENS = 500
_MAX_MESSAGES_TOKENS = 8_000
_ESTIMATED_TOKENS_PER_CHAR = 4  # Conservative estimate for truncation


# ── Tool Cache ─────────────────────────────────────────────────────────────────


def _stable_hash(args: dict[str, Any]) -> str:
    """Create a stable hash of a dict for cache keys.
    
    Sorts keys recursively to ensure same args always produce same hash.
    """
    serialized = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


class ToolCache:
    """Memoizing cache for tool results.
    
    Key = f"{tool_name}:{stable_hash(args)}"
    Value = tool result (any JSON-serializable type)
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def make_key(self, tool_name: str, args: dict[str, Any]) -> str:
        """Generate a cache key for a tool call."""
        return f"{tool_name}:{_stable_hash(args)}"

    def get(self, tool_name: str, args: dict[str, Any]) -> Any | None:
        """Get cached result, or None if not cached."""
        key = self.make_key(tool_name, args)
        return self._cache.get(key)

    def set(self, tool_name: str, args: dict[str, Any], result: Any) -> None:
        """Store a tool result in the cache."""
        key = self.make_key(tool_name, args)
        self._cache[key] = result

    def has(self, tool_name: str, args: dict[str, Any]) -> bool:
        """Check if a tool call is cached."""
        key = self.make_key(tool_name, args)
        return key in self._cache

    def clear(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# ── Scratchpad ─────────────────────────────────────────────────────────────────


class Scratchpad:
    """Maintains context for the ReAct agent across iterations.
    
    Stores:
    - RAG context chunks (auto-injected from knowledge base)
    - Tool execution trace (thought → action → observation)
    - Cached tool results for memoization
    
    Usage:
        scratchpad = Scratchpad()
        scratchpad.add_context(["chunk1", "chunk2"])
        scratchpad.add_observation("search_papers", {"query": "AI"}, result)
        cached = scratchpad.get_cached("search_papers", {"query": "AI"})
    """

    def __init__(self) -> None:
        self._cache = ToolCache()
        self._rag_chunks: list[str] = []
        self._trace: list[dict[str, Any]] = []
        self._total_tokens = 0

    # ── Cache operations ─────────────────────────────────────────────────────

    def get_cached(self, tool_name: str, args: dict[str, Any]) -> Any | None:
        """Get cached tool result if available.
        
        Returns:
            Cached result or None.
        """
        return self._cache.get(tool_name, args)

    def add_to_cache(self, tool_name: str, args: dict[str, Any], result: Any) -> None:
        """Cache a tool result for future reuse."""
        self._cache.set(tool_name, args, result)

    # ── RAG context ──────────────────────────────────────────────────────────

    def add_context(self, chunks: list[str]) -> None:
        """Store auto-RAG output chunks.
        
        Args:
            chunks: List of text chunks retrieved from the knowledge base.
        """
        self._rag_chunks = list(chunks)

    @property
    def rag_chunks(self) -> list[str]:
        """Get the stored RAG context chunks."""
        return list(self._rag_chunks)

    # ── Trace operations ───────────────────────────────────────────────────────

    def add_observation(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
    ) -> None:
        """Record a tool execution as an observation.
        
        Also caches the result for memoization.
        
        Args:
            tool_name: Name of the tool that was called.
            args: Arguments passed to the tool.
            result: The result returned by the tool.
        """
        # Cache the result
        self.add_to_cache(tool_name, args, result)

        # Format observation for trace
        truncated_result = self._truncate(result, _MAX_OBSERVATION_TOKENS)

        observation = {
            "type": "observation",
            "tool": tool_name,
            "args": args,
            "result": truncated_result,
        }
        self._trace.append(observation)
        self._total_tokens += self._estimate_tokens(truncated_result)

    def add_thought(self, thought: str) -> None:
        """Record a thought/reasoning step.
        
        Args:
            thought: The reasoning text.
        """
        thought_entry = {
            "type": "thought",
            "content": thought,
        }
        self._trace.append(thought_entry)
        self._total_tokens += self._estimate_tokens(thought)

    @property
    def trace(self) -> list[dict[str, Any]]:
        """Get the full execution trace."""
        return list(self._trace)

    # ── Message rendering ───────────────────────────────────────────────────────

    def to_messages(self) -> list[dict[str, Any]]:
        """Render the scratchpad as ChatML messages for the LLM.
        
        Returns:
            List of message dicts in ChatML format.
        """
        messages: list[dict[str, Any]] = []

        # RAG context
        if self._rag_chunks:
            context_text = "\n\n".join(
                f"[Context {i+1}]\n{chunk}"
                for i, chunk in enumerate(self._rag_chunks)
            )
            messages.append({
                "role": "system",
                "content": f"**Project Context** (from knowledge base):\n\n{context_text}\n\nUse this context to answer the user's question if relevant.",
            })

        # Tool execution trace
        if self._trace:
            trace_text = self._format_trace()
            messages.append({
                "role": "system",
                "content": f"**Previous Actions**:\n\n{trace_text}",
            })

        # Truncate if over limit
        messages = self._truncate_messages(messages, _MAX_MESSAGES_TOKENS)

        return messages

    def _format_trace(self) -> str:
        """Format the execution trace as readable text."""
        lines = []
        for entry in self._trace:
            if entry["type"] == "thought":
                lines.append(f"Thought: {entry['content']}")
            elif entry["type"] == "observation":
                tool = entry["tool"]
                args = entry.get("args", {})
                result = entry.get("result", "")

                args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                lines.append(
                    f"Action: {tool}\n"
                    f"  Args: {args_str}\n"
                    f"  Result: {result}"
                )
        return "\n".join(lines)

    # ── Truncation helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        """Estimate token count from a value."""
        if value is None:
            return 0
        text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
        return len(text) // _ESTIMATED_TOKENS_PER_CHAR

    @staticmethod
    def _truncate(value: Any, max_tokens: int) -> Any:
        """Truncate a value to fit within max_tokens.
        
        Args:
            value: The value to truncate (str, dict, list, or other).
            max_tokens: Maximum tokens allowed.
            
        Returns:
            Truncated string or repr of the value.
        """
        if isinstance(value, str):
            max_chars = max_tokens * _ESTIMATED_TOKENS_PER_CHAR
            if len(value) > max_chars:
                return value[:max_chars] + "\n...[truncated]"
            return value

        # For non-string values, convert to repr and truncate
        text = repr(value)
        max_chars = max_tokens * _ESTIMATED_TOKENS_PER_CHAR
        if len(text) > max_chars:
            return text[:max_chars] + "...[truncated]"
        return value

    def _truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        """Truncate messages list to fit within token budget.
        
        Truncates from the end (oldest messages) if needed.
        """
        total = sum(self._estimate_tokens(m.get("content", "")) for m in messages)

        if total <= max_tokens:
            return messages

        # Truncate starting from the last message (least important)
        result = []
        running_tokens = 0

        for msg in reversed(messages):
            content = msg.get("content", "")
            tokens = self._estimate_tokens(content)
            if running_tokens + tokens <= max_tokens:
                result.insert(0, msg)
                running_tokens += tokens
            else:
                # Truncate this message
                remaining_tokens = max_tokens - running_tokens
                if remaining_tokens > 50:  # Only if worth keeping
                    truncated_content = self._truncate(content, remaining_tokens)
                    result.insert(0, {**msg, "content": truncated_content})
                break

        return result

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def cache_size(self) -> int:
        """Number of cached tool results."""
        return len(self._cache)

    @property
    def trace_length(self) -> int:
        """Number of trace entries."""
        return len(self._trace)

    @property
    def estimated_tokens(self) -> int:
        """Estimated total tokens in the scratchpad."""
        return self._total_tokens

    def reset(self) -> None:
        """Reset the scratchpad to initial state."""
        self._cache.clear()
        self._rag_chunks.clear()
        self._trace.clear()
        self._total_tokens = 0
