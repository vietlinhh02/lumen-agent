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

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, TypeVar, Union, cast

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
    arguments: Dict[str, Any]


@dataclass
class StreamDone:
    """Marks the end of the stream."""
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


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
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
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

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return embedding vector for *text*."""

    @abstractmethod
    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
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

    async def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
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
        """Force JSON output via tool_use.

        Defines a single tool whose input_schema is *schema*, then forces the
        model to call it. The returned tool_input is a validated JSON dict.
        """
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
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input  # type: ignore[return-value]
        raise ValueError(f"Model did not call tool '{tool_name}'")

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "AnthropicAdapter does not support embed(). Use OpenAIEmbedder for pgvector embeddings."
        )

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream with structured tool calls for Anthropic (Task 8).

        Anthropic uses tool_use content blocks. We parse these to emit
        structured ToolCallStart/ToolCallDone events.
        """
        import json
        
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
        tool_calls: Dict[str, Dict[str, Any]] = {}  # call_id -> {name, args_str}

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

    Used for DeepSeek (via opencode.ai), standard OpenAI, and local models
    like vLLM / Ollama.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str,
        base_url: str | None = None,
    ) -> None:
        self._model = model
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        msgs = _build_openai_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": 0.0,
        }
        if self._model.startswith(("deepseek", "mimo")):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        # Only return actual content, never reasoning_content
        # to prevent leaking the model's internal thinking into the response.
        if msg.content:
            return msg.content

        return ""

    async def stream(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream text tokens from any OpenAI-compatible endpoint.

        Uses the chat completions streaming API. When *tools* are provided
        the caller should be ready to handle tool-call chunks; for the
        ReAct text-based flow we ignore tool_calls and only forward the
        text deltas.
        """
        msgs = _build_openai_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if self._model.startswith(("deepseek", "mimo")):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")

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
        """Force JSON output via two strategies.

        1) **response_format json_object** — works with DeepSeek V4 Flash
           (thinking model) which rejects forced tool_choice.
        2) **forced tool_choice** — works with standard OpenAI / GPT models.

        The schema is injected into the system prompt so the model knows the
        expected shape when using strategy (1).
        """
        import json

        schema_str = json.dumps(schema, indent=2)

        # Strategy 1: response_format json_object (DeepSeek‑compatible)
        try:
            return await self._structured_via_json_format(
                messages, schema, schema_str, system, max_tokens
            )
        except Exception:
            pass

        # Strategy 2: forced tool_choice (standard OpenAI‑compatible)
        return await self._structured_via_tool_choice(
            messages, schema, tool_name, system, max_tokens
        )

    async def _structured_via_json_format(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        schema_str: str,
        system: str | None,
        max_tokens: int,
    ) -> dict[str, Any]:
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
            "response_format": {"type": "json_object"},
        }
        if self._model.startswith(("deepseek", "mimo")):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        # Strip markdown fences if the model ignores the instruction
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("\n```", 1)[0]
        return json.loads(content)

    async def _structured_via_tool_choice(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        tool_name: str,
        system: str | None,
        max_tokens: int,
    ) -> dict[str, Any]:
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
        if self._model.startswith(("deepseek", "mimo")):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
        response = await self._client.chat.completions.create(**kwargs)
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise ValueError(f"Model '{self._model}' did not call tool '{tool_name}'")
        return json.loads(tool_calls[0].function.arguments)

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "OpenAICompatibleAdapter does not support embed(). Use a dedicated embedding model."
        )

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_tokens: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream with structured tool calls for OpenAI-compatible endpoints (Task 8).

        OpenAI and compatible APIs emit tool_call chunks during streaming.
        We parse these to emit structured ToolCallStart/ToolCallArgsDelta/ToolCallDone events.
        """
        import json
        
        msgs = _build_openai_messages(messages, system)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if self._model.startswith(("deepseek", "mimo")):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")

        accumulated_text = ""
        tool_calls: Dict[str, Dict[str, Any]] = {}  # call_id -> {name, args_str}

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                # Handle text content
                content = getattr(delta, "content", None)
                if content:
                    accumulated_text += content
                    yield TextChunk(delta=content)
                
                # Handle reasoning content (DeepSeek)
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    accumulated_text += reasoning
                    yield TextChunk(delta=reasoning)
                
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

    if model.startswith("claude"):
        return AnthropicAdapter(model=model)

    if model.startswith(("deepseek", "mimo")):
        return OpenAICompatibleAdapter(
            model=model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    if model.startswith(("gpt", "o1", "o3")):
        return OpenAICompatibleAdapter(
            model=model,
            api_key=settings.openai_api_key,
        )

    raise ValueError(
        f"Unsupported model '{model}'. "
        "Supported prefixes: claude-*, deepseek-*, mimo-*, gpt-*, o1, o3."
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
