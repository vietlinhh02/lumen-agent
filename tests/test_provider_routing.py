"""Tests for AI provider model-name routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def _patch_settings(**overrides):
    """Return a context manager that overrides get_settings() fields."""
    from app.core import config

    real_settings = config.get_settings()

    class _FakeSettings:
        def __init__(self):
            for k, v in real_settings.__dict__.items():
                setattr(self, k, v)
            for k, v in overrides.items():
                setattr(self, k, v)

    return patch.object(config, "get_settings", lambda: _FakeSettings())


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
