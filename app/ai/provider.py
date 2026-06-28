"""AIProvider abstraction — all LLM calls go through this interface.

Supports:
- Anthropic Claude (via anthropic SDK)
- DeepSeek V4 Flash (via OpenAI-compatible endpoint)
- OpenAI (via openai SDK)

Task 8: Native tool call support.
The stream_with_tools() method yields structured tool calls instead of
relying on text parsing of Action: patterns.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, TypeVar, Union, cast

import anthropic
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.core.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── Tool Call Types for Native Tool Calling (Task 8) ────────────────────────


class ChunkType(Enum):
    """Type of chunk yielded by stream_with_tools()."""
    TEXT = "text"           # Text delta
    TOOL_CALL_START = "tool_call_start"   # Start of a tool call
    TOOL_CALL_ARGS_DELTA = "tool_call_args_delta"  # Partial tool arguments
    TOOL_CALL_DONE = "tool_call_done"     # Tool call complete
    DONE = "done"           # Stream finished


@dataclass
class TextChunk:
    """A text token chunk."""
    delta: str


@dataclass
class ToolCallStart:
    """Marks the start of a tool call."""
    call_id: str
    name: str


@dataclass
class ToolCallArgsDelta:
    """Partial arguments for a tool call."""
    call_id: str
    delta: str


@dataclass
class ToolCallDone:
    """Marks a tool call as complete with final arguments."""
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class StreamDone:
    """Marks the end of the stream."""
    content: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMUsage:
    """Token usage returned by complete_with_usage()."""
    input_tokens: int
    output_tokens: int
    model: str


StreamChunk = Union[TextChunk, ToolCallStart, ToolCallArgsDelta, ToolCallDone, StreamDone]


class AIProvider(ABC):
    """Common interface for LLM providers used by services and agents."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        """Return raw text completion."""

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str]:
        """Yield text tokens as they are produced by the model.

        Implementations MUST emit tokens incrementally so the consumer can
        forward them to a streaming response (e.g., SSE) without buffering
        the full response first.
        """
        raise NotImplementedError
        yield ""  # pragma: no cover - makes this a generator for type checkers

    @abstractmethod
    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Return structured JSON dict matching *schema* (JSON Schema format)."""

    async def complete_structured_with_usage(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> tuple[dict[str, Any], LLMUsage]:
        """Return (structured_data, LLMUsage). Default implementation returns 0 usage."""
        data = await self.complete_structured(messages, schema, tool_name, system, max_tokens)
        return data, LLMUsage(input_tokens=0, output_tokens=0, model="unknown")

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return embedding vector for *text*."""

    async def complete_with_usage(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> tuple[str, LLMUsage]:
        """Return (text, LLMUsage) with real token counts.

        Default implementation calls complete() and returns zero-count usage.
        Subclasses override to capture actual provider-reported token counts.
        This does NOT replace complete() so existing callers are unaffected.
        """
        text = await self.complete(messages, system=system, max_tokens=max_tokens)
        return text, LLMUsage(input_tokens=0, output_tokens=0, model="unknown")

    @abstractmethod
    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream response with structured tool call support (Task 8).

        Yields structured chunks instead of raw text:
        - TextChunk: text deltas for thought/answer streaming
        - ToolCallStart: when a tool call begins
        - ToolCallArgsDelta: partial arguments as they arrive
        - ToolCallDone: tool call complete with final arguments
        - StreamDone: stream finished, contains final content and all tool calls

        This replaces the fragile Action: text parsing approach.

        Args:
            messages: Chat messages (can include tool results as tool role).
            system: Optional system prompt.
            max_tokens: Max tokens to generate.
            tools: Tool definitions in provider-specific format.

        Yields:
            StreamChunk subclasses with structured data.
        """
        raise NotImplementedError


# ── Anthropic Adapter ─────────────────────────────────────────────────────────


class AnthropicAdapter(AIProvider):
    """Anthropic Claude adapter.

    Uses the tool_use trick to force structured JSON output because the
    Anthropic API does not support a native response_format parameter.
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        return response.content[0].text  # type: ignore[union-attr]

    async def complete_with_usage(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> tuple[str, LLMUsage]:
        """Anthropic implementation — reads .usage.input_tokens / output_tokens."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        text = response.content[0].text  # type: ignore[union-attr]
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self._model,
        )
        return text, usage

    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str]:
        """Stream text tokens from Anthropic.

        Uses the Anthropic streaming API and yields incremental text
        deltas from text content blocks. Tool use blocks are ignored here
        because the ReAct agent uses text-based tool parsing.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text

    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Force JSON output via tool_use."""
        data, _ = await self.complete_structured_with_usage(
            messages, schema, tool_name, system, max_tokens
        )
        return data

    async def complete_structured_with_usage(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> tuple[dict[str, Any], LLMUsage]:
        """Force JSON output via tool_use and return token usage."""
        tool: dict[str, Any] = {
            "name": tool_name,
            "description": f"Return structured data matching the {tool_name} schema.",
            "input_schema": schema,
        }
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if system:
            kwargs["system"] = system
        response = await self._client.messages.create(**kwargs)
        
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self._model,
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input, usage  # type: ignore[return-value]
        raise ValueError(f"Model did not call tool '{tool_name}'")

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "AnthropicAdapter does not support embed(). Use OpenAIEmbedder for pgvector embeddings."
        )

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream with structured tool calls for Anthropic (Task 8).

        Anthropic uses tool_use content blocks. We parse these to emit
        structured ToolCallStart/ToolCallDone events.
        """
        
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        accumulated_text = ""
        tool_calls: dict[str, dict[str, Any]] = {}  # call_id -> {name, args_str}

        async with self._client.messages.stream(**kwargs) as stream:
            # Handle content blocks
            async for block in stream.content_block_delta:
                if block.type == "text":
                    delta = block.text
                    accumulated_text += delta
                    yield TextChunk(delta=delta)
                elif block.type == "tool_use":
                    call_id = block.id
                    name = block.name
                    # Start of tool call
                    if call_id not in tool_calls:
                        tool_calls[call_id] = {"name": name, "args_str": ""}
                        yield ToolCallStart(call_id=call_id, name=name)
            
            # Handle message end for final tool calls
            message = await stream.get_final_message()
            final_tool_calls = []
            for block in message.content:
                if block.type == "tool_use":
                    call_id = block.id
                    name = block.name
                    args = block.input
                    final_tool_calls.append({
                        "id": call_id,
                        "name": name,
                        "arguments": args,
                    })
                    # Emit done if not already emitted
                    if call_id in tool_calls:
                        yield ToolCallDone(
                            call_id=call_id,
                            name=name,
                            arguments=args,
                        )
            
            yield StreamDone(content=accumulated_text, tool_calls=final_tool_calls)


# ── OpenAI-Compatible Adapter (DeepSeek, OpenAI, any /v1/chat/completions) ─────


class OpenAICompatibleAdapter(AIProvider):
    """Generic adapter for any provider exposing an OpenAI-compatible chat API.

    Used for DeepSeek (via opencode.ai), standard OpenAI, MiniMax
    (api.minimax.io/v1), and local models like vLLM / Ollama.

    Supports an ``extra_body`` dict that is merged into every chat
    completions request — useful for provider-specific switches such as
    MiniMax's ``thinking`` and ``reasoning_split`` parameters, which the
    OpenAI SDK does not expose as first-class args.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._model = model
        # extra_body is merged into every chat.completions.create request.
        # Provider-specific switches like MiniMax's `thinking` /
        # `reasoning_split` live here because the OpenAI SDK has no
        # typed field for them.
        self._extra_body: dict[str, Any] = dict(extra_body or {})
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)

    def _base_kwargs(
        self,
        messages: list[dict[str, str]],
        system: str | None,
        max_tokens: int,
        *,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build common request kwargs, merging extra_body if set."""
        msgs = _build_openai_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        if stream:
            kwargs["stream"] = True
        if tools:
            kwargs["tools"] = tools
        if self._extra_body:
            # OpenAI SDK forwards extra_body into the JSON request body.
            kwargs["extra_body"] = dict(self._extra_body)
        return kwargs

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        kwargs = self._base_kwargs(messages, system, max_tokens)
        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        # Only return actual content, never reasoning_content
        # to prevent leaking the model's internal thinking into the response.
        if msg.content:
            return msg.content

        return ""

    async def complete_with_usage(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> tuple[str, LLMUsage]:
        """OpenAI-compatible implementation — reads .usage.prompt_tokens / completion_tokens."""
        kwargs = self._base_kwargs(messages, system, max_tokens)
        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        text = msg.content or ""
        usage_obj = response.usage
        usage = LLMUsage(
            input_tokens=usage_obj.prompt_tokens if usage_obj else 0,
            output_tokens=usage_obj.completion_tokens if usage_obj else 0,
            model=self._model,
        )
        return text, usage

    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str]:
        """Stream text tokens from any OpenAI-compatible endpoint.

        Uses the chat completions streaming API. When *tools* are provided
        the caller should be ready to handle tool-call chunks; for the
        ReAct text-based flow we ignore tool_calls and only forward the
        text deltas.

        Always discards ``reasoning_content`` (DeepSeek, MiniMax with
        ``reasoning_split=True``) so internal thinking never leaks into
        the user-visible token stream.
        """
        kwargs = self._base_kwargs(
            messages, system, max_tokens, stream=True, tools=tools
        )

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # Prefer text content only - do NOT yield reasoning_content
                # to prevent leaking the model's internal thinking into
                # the visible response.
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except Exception:
            # Re-raise so the caller can decide whether to fall back.
            raise

    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        data, _ = await self.complete_structured_with_usage(
            messages, schema, tool_name, system, max_tokens
        )
        return data

    async def complete_structured_with_usage(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> tuple[dict[str, Any], LLMUsage]:
        """Return structured JSON output with usage."""
        import json
        schema_str = json.dumps(schema)

        # Strategy 1: JSON format
        try:
            return await self._structured_via_json_format_with_usage(
                messages, schema, schema_str, system, max_tokens, use_response_format=True
            )
        except Exception:
            pass

        # Strategy 2: tool_choice
        try:
            return await self._structured_via_tool_choice_with_usage(
                messages, schema, tool_name, system, max_tokens
            )
        except Exception:
            pass
            
        # Strategy 3: raw text fallback
        return await self._structured_via_json_format_with_usage(
            messages, schema, schema_str, system, max_tokens, use_response_format=False
        )

    async def _structured_via_json_format_with_usage(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        schema_str: str,
        system: str | None,
        max_tokens: int,
        use_response_format: bool = True,
    ) -> tuple[dict[str, Any], LLMUsage]:
        import json

        json_system = (
            f"You are a helpful assistant that ALWAYS responds with a single JSON object. "
            f"The JSON object MUST conform to this schema:\n{schema_str}\n"
            f"Do NOT include any text outside the JSON. Do NOT use markdown fences. "
            f"Output raw JSON only."
        )
        msgs: list[dict[str, str]] = [{"role": "system", "content": json_system}]
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        kwargs = {
            "model": self._model,
            "messages": cast(list[ChatCompletionMessageParam], msgs),
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        if use_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        if self._extra_body:
            kwargs["extra_body"] = dict(self._extra_body)

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        
        usage_obj = response.usage
        usage = LLMUsage(
            input_tokens=usage_obj.prompt_tokens if usage_obj else 0,
            output_tokens=usage_obj.completion_tokens if usage_obj else 0,
            model=self._model,
        )

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("\n```", 1)[0]

        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            content = content[start_idx:end_idx+1]

        return json.loads(content), usage

    async def _structured_via_tool_choice_with_usage(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None,
        max_tokens: int,
    ) -> tuple[dict[str, Any], LLMUsage]:
        import json

        tool_def: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": f"Return structured data matching the {tool_name} schema.",
                "parameters": schema,
            },
        }
        msgs = _build_openai_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "tools": [tool_def],
            "tool_choice": "auto" if self._model.startswith("mimo") else {"type": "function", "function": {"name": tool_name}},
        }
        if self._extra_body:
            kwargs["extra_body"] = dict(self._extra_body)
        response = await self._client.chat.completions.create(**kwargs)
        
        usage_obj = response.usage
        usage = LLMUsage(
            input_tokens=usage_obj.prompt_tokens if usage_obj else 0,
            output_tokens=usage_obj.completion_tokens if usage_obj else 0,
            model=self._model,
        )
        
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise ValueError(f"Model '{self._model}' did not call tool '{tool_name}'")
        return json.loads(tool_calls[0].function.arguments), usage

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "OpenAICompatibleAdapter does not support embed(). Use a dedicated embedding model."
        )

    async def stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 2048,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[StreamChunk]:
        """Stream with structured tool calls for OpenAI-compatible endpoints (Task 8).

        OpenAI and compatible APIs emit tool_call chunks during streaming.
        We parse these to emit structured ToolCallStart/ToolCallArgsDelta/ToolCallDone events.
        """
        import json

        kwargs = self._base_kwargs(
            messages, system, max_tokens, stream=True, tools=tools
        )

        accumulated_text = ""
        tool_calls: dict[str, dict[str, Any]] = {}  # call_id -> {name, args_str}

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Handle text content (visible tokens)
                content = getattr(delta, "content", None)
                if content:
                    accumulated_text += content
                    yield TextChunk(delta=content)

                # Handle reasoning content (DeepSeek / MiniMax with reasoning_split).
                # IMPORTANT: do NOT yield this as TextChunk — that would leak
                # the model's chain of thought into the user-visible message.
                # The reasoning is intentionally discarded so the UI only ever
                # sees the final answer.
                _reasoning = getattr(delta, "reasoning_content", None)
                # (kept as a no-op assignment so the variable is read and
                #  static analyzers see the explicit intent)

                # Handle tool_call chunks
                tool_calls_delta = getattr(delta, "tool_calls", None)
                if tool_calls_delta:
                    for tc_delta in tool_calls_delta:
                        call_id = getattr(tc_delta, "id", None)

                        func_delta = getattr(tc_delta, "function", None)
                        name = getattr(func_delta, "name", None) if func_delta else None
                        args_delta = getattr(func_delta, "arguments", None) if func_delta else None

                        # In OpenAI streaming, the first chunk for a tool call has the ID and name
                        # Subsequent chunks have the same index but ID/name might be None, with arguments string

                        # Use index to track the current tool call since call_id is only present in the first chunk
                        tc_index = getattr(tc_delta, "index", 0)

                        # We use a string key based on index to track tool calls across chunks
                        # if we don't have the call_id yet
                        idx_key = str(tc_index)

                        if idx_key not in tool_calls:
                            tool_calls[idx_key] = {"id": call_id or f"call_{tc_index}", "name": name or "", "args_str": ""}
                            if name:
                                yield ToolCallStart(call_id=tool_calls[idx_key]["id"], name=name)
                        else:
                            # Update ID if it arrives late
                            if call_id and tool_calls[idx_key]["id"].startswith("call_"):
                                tool_calls[idx_key]["id"] = call_id

                        # Arguments delta
                        if args_delta:
                            tool_calls[idx_key]["args_str"] += args_delta
                            yield ToolCallArgsDelta(call_id=tool_calls[idx_key]["id"], delta=args_delta)

            # Emit final tool call completion
            final_tool_calls = []
            for call_id, call_data in tool_calls.items():
                try:
                    args = json.loads(call_data["args_str"]) if call_data["args_str"] else {}
                except json.JSONDecodeError:
                    args = {}
                final_tool_calls.append({
                    "id": call_data["id"],
                    "name": call_data["name"],
                    "arguments": args,
                })
                yield ToolCallDone(
                    call_id=call_data["id"],
                    name=call_data["name"],
                    arguments=args,
                )

            yield StreamDone(content=accumulated_text, tool_calls=final_tool_calls)
            
        except Exception as exc:
            logger.error("stream_with_tools failed: %s", exc)
            raise


# ── OpenAI Embedder ───────────────────────────────────────────────────────────


class OpenAIEmbedder:
    """Thin wrapper around OpenAI text-embedding-3-small for pgvector storage.

    Kept separate from AIProvider because embedding is not a chat task and
    is only used by the embeddings service.
    """

    DIMENSION = 1536  # text-embedding-3-small output dimension

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_openai_messages(
    messages: list[dict[str, str]],
    system: str | None = None,
) -> list[dict[str, str]]:
    """Prepend a system message if provided."""
    msgs: list[dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    return msgs


# ── Factory ───────────────────────────────────────────────────────────────────


def _build_provider_for_model(model: str) -> AIProvider:
    """Build an AI provider for a specific model name."""
    settings = get_settings()

    # Normalize for prefix matching (some provider names use mixed case,
    # e.g. "MiniMax-M2.7" or "minimax-m3").
    model_lower = model.lower()

    if model_lower.startswith("claude"):
        return AnthropicAdapter(model=model)

    # MiniMax is served from the same OpenAI-compatible endpoint as DeepSeek
    # / MiMo (the operator points DEEPSEEK_BASE_URL at api.minimax.io/v1 in
    # the deployment env), so we route through the OpenAI-compatible
    # adapter using those credentials.
    #
    # Per MiniMax docs (https://platform.minimax.io/docs/llms.txt):
    #   - `reasoning_split=True` separates thinking tokens from the answer
    #     into the `reasoning_details` field, keeping `content` clean.
    #   - `thinking: {"type": "disabled"}` actually disables thinking on
    #     MiniMax-M3, but M2.x models (M2.7, M2.5, M2.1, M2) always emit
    #     reasoning regardless of the flag. For M2.x we still set
    #     `reasoning_split=True` so the visible content is clean even when
    #     the chain-of-thought can't be turned off.
    if model_lower.startswith("minimax"):
        extra_body: dict[str, Any] = {"reasoning_split": True}
        if "m3" in model_lower or "m-3" in model_lower:
            extra_body["thinking"] = {"type": "disabled"}
        return OpenAICompatibleAdapter(
            model=model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            extra_body=extra_body,
        )

    if model_lower.startswith(("deepseek", "mimo")):
        return OpenAICompatibleAdapter(
            model=model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    if model_lower.startswith(("gpt", "o1", "o3")):
        return OpenAICompatibleAdapter(
            model=model,
            api_key=settings.openai_api_key,
        )

    raise ValueError(
        f"Unsupported model '{model}'. "
        "Supported prefixes: claude-*, deepseek-*, mimo-*, MiniMax-*, gpt-*, o1, o3."
    )


@lru_cache
def get_provider_for_model(model: str) -> AIProvider:
    """Return a cached AIProvider singleton for a specific model."""
    return _build_provider_for_model(model)


@lru_cache
def get_provider() -> AIProvider:
    """Return the configured AIProvider singleton.

    Reads DEFAULT_MODEL from settings to select the adapter.

    Current routing:
    - ``claude-*``      → AnthropicAdapter
    - ``deepseek-*``    → OpenAICompatibleAdapter (via deepseek_base_url)
    - ``mimo-*``        → OpenAICompatibleAdapter (via deepseek_base_url)
    - ``MiniMax-*``     → OpenAICompatibleAdapter (via deepseek_base_url —
                          operator points the base URL at api.minimax.io/v1)
    - ``gpt-*``         → OpenAICompatibleAdapter (via standard OpenAI)
    - ``o1`` / ``o3``   → OpenAICompatibleAdapter
    """
    settings = get_settings()
    return get_provider_for_model(settings.default_model)


@lru_cache
def get_matrix_verifier_provider() -> AIProvider | None:
    """Return the optional verifier provider for collaborative extraction."""
    settings = get_settings()
    model = settings.matrix_verifier_model.strip()
    if not model:
        return None
    return get_provider_for_model(model)


@lru_cache
def get_embedder() -> OpenAIEmbedder:
    """Return the OpenAI embedder singleton used by the embeddings service."""
    return OpenAIEmbedder()
