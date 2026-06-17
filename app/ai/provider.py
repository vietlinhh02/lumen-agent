"""AIProvider abstraction — all LLM calls go through this interface.

Supports:
- Anthropic Claude (via anthropic SDK)
- DeepSeek V4 Flash (via OpenAI-compatible endpoint)
- OpenAI (via openai SDK)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, TypeVar, cast

import anthropic
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from app.core.config import get_settings

T = TypeVar("T")


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
        if self._model.startswith("deepseek"):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = await self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if msg.content:
            return msg.content

        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            return reasoning

        return ""

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

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=cast(list[ChatCompletionMessageParam], msgs),
            max_tokens=max_tokens,
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
        )
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
            "tool_choice": {"type": "function", "function": {"name": tool_name}},
        }
        if self._model.startswith("deepseek"):
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = await self._client.chat.completions.create(**kwargs)
        tool_calls = response.choices[0].message.tool_calls
        if not tool_calls:
            raise ValueError(f"Model '{self._model}' did not call tool '{tool_name}'")
        return json.loads(tool_calls[0].function.arguments)

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "OpenAICompatibleAdapter does not support embed(). Use a dedicated embedding model."
        )


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
    model = settings.default_model

    # Anthropic
    if model.startswith("claude"):
        return AnthropicAdapter(model=model)

    # DeepSeek / MiMo (via OpenAI-compatible endpoint)
    if model.startswith(("deepseek", "mimo")):
        return OpenAICompatibleAdapter(
            model=model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    # OpenAI / GPT
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
def get_embedder() -> OpenAIEmbedder:
    """Return the OpenAI embedder singleton used by the embeddings service."""
    return OpenAIEmbedder()
