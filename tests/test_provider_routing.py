"""Tests for AI provider model-name routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _patch_settings(**overrides):
    """Return a context manager that overrides get_settings() fields.

    Patches BOTH ``app.core.config.get_settings`` (the canonical location)
    AND the local binding inside ``app.ai.provider`` — the provider module
    does ``from app.core.config import get_settings`` which creates a local
    binding that ``patch.object(config, ...)`` alone can't reach.
    """
    from contextlib import ExitStack
    from app.core import config
    from app.ai import provider as provider_module

    real_settings = config.get_settings()

    class _FakeSettings:
        def __init__(self):
            for k, v in real_settings.__dict__.items():
                setattr(self, k, v)
            for k, v in overrides.items():
                setattr(self, k, v)

    fake_factory = lambda: _FakeSettings()  # noqa: E731

    stack = ExitStack()
    stack.enter_context(patch.object(config, "get_settings", fake_factory))
    stack.enter_context(
        patch.object(provider_module, "get_settings", fake_factory)
    )
    return stack


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    """Clear the @lru_cache on get_provider so each test sees fresh routing."""
    from app.ai import provider as p

    p.get_provider.cache_clear()
    p.get_provider_for_model.cache_clear()
    p.get_matrix_verifier_provider.cache_clear()
    yield
    p.get_provider.cache_clear()
    p.get_provider_for_model.cache_clear()
    p.get_matrix_verifier_provider.cache_clear()


def test_minimax_routes_to_openai_compatible():
    """MiniMax-* models route through the OpenAI-compatible adapter
    using DEEPSEEK_BASE_URL (operator points it at api.minimax.io/v1)."""
    from app.ai.provider import _build_provider_for_model
    from app.ai.provider import OpenAICompatibleAdapter

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("MiniMax-M2.7")

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter._model == "MiniMax-M2.7"
    assert str(adapter._client.base_url).startswith("https://api.minimax.io/v1")


def test_minimax_routing_is_case_insensitive():
    """Mixed/lowercase 'minimax' prefix also routes correctly."""
    from app.ai.provider import _build_provider_for_model
    from app.ai.provider import OpenAICompatibleAdapter

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("minimax-m3")

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter._model == "minimax-m3"


def test_get_provider_reads_minimax_default_model():
    """``get_provider()`` honors DEFAULT_MODEL=MiniMax-* via the cache."""
    from app.ai import provider as p
    from app.ai.provider import OpenAICompatibleAdapter

    with _patch_settings(
        default_model="MiniMax-M2.7",
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = p.get_provider()

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter._model == "MiniMax-M2.7"


def test_matrix_verifier_supports_minimax():
    """``get_matrix_verifier_provider()`` works for MiniMax-* as well."""
    from app.ai import provider as p
    from app.ai.provider import OpenAICompatibleAdapter

    with _patch_settings(
        matrix_verifier_model="MiniMax-M3",
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = p.get_matrix_verifier_provider()

    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert adapter._model == "MiniMax-M3"


def test_unknown_model_still_raises():
    """Truly unknown models still raise the descriptive ValueError."""
    from app.ai.provider import _build_provider_for_model

    with pytest.raises(ValueError, match="Unsupported model"):
        _build_provider_for_model("totally-unknown-xyz")


def test_claude_still_routes_to_anthropic():
    """Regression: claude-* prefix must still go through AnthropicAdapter."""
    from app.ai.provider import _build_provider_for_model
    from app.ai.provider import AnthropicAdapter

    with _patch_settings(anthropic_api_key="sk-ant-test"):
        adapter = _build_provider_for_model("claude-sonnet-4-20250514")

    assert isinstance(adapter, AnthropicAdapter)


# ── MiniMax thinking / reasoning_split ──────────────────────────────────────


def test_minimax_m3_disables_thinking_via_extra_body():
    """MiniMax-M3 supports `thinking: {"type": "disabled"}` and the adapter
    must inject it into extra_body so the API actually turns thinking off."""
    from app.ai.provider import _build_provider_for_model

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("MiniMax-M3")

    assert adapter._extra_body.get("thinking") == {"type": "disabled"}
    # reasoning_split is also enabled to keep `content` clean even when
    # the model still emits some reasoning.
    assert adapter._extra_body.get("reasoning_split") is True


def test_minimax_m2x_does_not_set_thinking_disabled():
    """MiniMax M2.x models (M2.7, M2.5, M2.1, M2) cannot disable thinking
    per the MiniMax docs. The adapter must NOT send
    `thinking: {"type": "disabled"}` for those models — only
    `reasoning_split` so the answer stays clean."""
    from app.ai.provider import _build_provider_for_model

    for m2_model in ("MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2"):
        with _patch_settings(
            deepseek_api_key="sk-cp-test",
            deepseek_base_url="https://api.minimax.io/v1",
        ):
            adapter = _build_provider_for_model(m2_model)

        assert "thinking" not in adapter._extra_body, (
            f"{m2_model} must not have `thinking` injected "
            "(M2.x always emit reasoning per MiniMax docs)"
        )
        assert adapter._extra_body.get("reasoning_split") is True, (
            f"{m2_model} must keep reasoning_split=True so content is clean"
        )


def test_minimax_extra_body_is_passed_to_request():
    """Verify the merged extra_body dict actually shows up in the kwargs
    sent to the chat.completions.create call."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.ai.provider import _build_provider_for_model

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("MiniMax-M3")

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="hello"))]

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    with patch.object(adapter, "_client", fake_client):
        asyncio.run(
            adapter.complete(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            )
        )

    call_kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert call_kwargs.get("extra_body") == {
        "thinking": {"type": "disabled"},
        "reasoning_split": True,
    }


def test_stream_skips_reasoning_content():
    """``stream()`` must never yield reasoning_content chunks so internal
    thinking cannot leak into the user-visible token stream."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.ai.provider import _build_provider_for_model

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("MiniMax-M3")

    # Build a fake streaming response that emits both content and
    # reasoning_content deltas. reasoning_content must be discarded.
    def _make_chunk(content=None, reasoning=None):
        delta = MagicMock()
        delta.content = content
        delta.reasoning_content = reasoning
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        return chunk

    async def _fake_stream():
        yield _make_chunk(content="hello ", reasoning="I should greet the user.")
        yield _make_chunk(content="world", reasoning=None)
        yield _make_chunk(content=None, reasoning="some more thinking")

    fake_client = MagicMock()

    async def _fake_create(**kwargs):
        async def _gen():
            async for c in _fake_stream():
                yield c
        return _gen()

    fake_client.chat.completions.create = AsyncMock(side_effect=_fake_create)

    with patch.object(adapter, "_client", fake_client):

        async def _collect():
            chunks = []
            async for tok in adapter.stream(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            ):
                chunks.append(tok)
            return chunks

        result = asyncio.run(_collect())

    assert result == ["hello ", "world"]


def test_stream_with_tools_skips_reasoning_content():
    """``stream_with_tools()`` must not yield reasoning_content as
    TextChunk — otherwise the model's chain-of-thought would be rendered
    to the user."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.ai.provider import _build_provider_for_model, TextChunk

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("MiniMax-M3")

    def _make_chunk(content=None, reasoning=None):
        delta = MagicMock()
        delta.content = content
        delta.reasoning_content = reasoning
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        return chunk

    async def _fake_stream():
        yield _make_chunk(content="Answer: ", reasoning="Let me think...")
        yield _make_chunk(content="42", reasoning="Almost done thinking")

    fake_client = MagicMock()

    async def _fake_create(**kwargs):
        async def _gen():
            async for c in _fake_stream():
                yield c
        return _gen()

    fake_client.chat.completions.create = AsyncMock(side_effect=_fake_create)

    with patch.object(adapter, "_client", fake_client):

        async def _collect():
            text_chunks = []
            async for chunk in adapter.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=128,
            ):
                if isinstance(chunk, TextChunk):
                    text_chunks.append(chunk.delta)
            return text_chunks

        result = asyncio.run(_collect())

    assert result == ["Answer: ", "42"]


def test_extra_body_omitted_when_not_set():
    """Non-MiniMax models (e.g. deepseek) should not get extra_body in
    requests — backwards compatible with the original behaviour."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.ai.provider import _build_provider_for_model

    with _patch_settings(
        deepseek_api_key="sk-cp-test",
        deepseek_base_url="https://api.minimax.io/v1",
    ):
        adapter = _build_provider_for_model("deepseek-v4-flash")

    assert adapter._extra_body == {}

    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="ok"))]

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)

    with patch.object(adapter, "_client", fake_client):
        asyncio.run(
            adapter.complete(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=64,
            )
        )

    call_kwargs = fake_client.chat.completions.create.await_args.kwargs
    assert "extra_body" not in call_kwargs
