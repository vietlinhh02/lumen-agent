"""Tests for AI provider factory helpers."""

from __future__ import annotations

from types import SimpleNamespace

from app.ai.provider import (
    OpenAICompatibleAdapter,
    get_matrix_verifier_provider,
    get_provider_for_model,
)


def _clear_provider_caches() -> None:
    get_provider_for_model.cache_clear()
    get_matrix_verifier_provider.cache_clear()


def test_get_provider_for_model_builds_deepseek_adapter(monkeypatch):
    monkeypatch.setattr(
        "app.ai.provider.get_settings",
        lambda: SimpleNamespace(
            deepseek_api_key="deepseek-key",
            deepseek_base_url="https://example.test/v1",
            openai_api_key="openai-key",
            matrix_verifier_model="",
            default_model="deepseek-v4-flash",
        ),
    )
    _clear_provider_caches()

    provider = get_provider_for_model("deepseek-v4-flash")

    assert isinstance(provider, OpenAICompatibleAdapter)
    assert provider._model == "deepseek-v4-flash"

    _clear_provider_caches()


def test_get_matrix_verifier_provider_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.setattr(
        "app.ai.provider.get_settings",
        lambda: SimpleNamespace(
            deepseek_api_key="deepseek-key",
            deepseek_base_url="https://example.test/v1",
            openai_api_key="openai-key",
            matrix_verifier_model="",
            default_model="deepseek-v4-flash",
        ),
    )
    _clear_provider_caches()

    provider = get_matrix_verifier_provider()

    assert provider is None

    _clear_provider_caches()


def test_get_matrix_verifier_provider_uses_configured_model(monkeypatch):
    monkeypatch.setattr(
        "app.ai.provider.get_settings",
        lambda: SimpleNamespace(
            deepseek_api_key="deepseek-key",
            deepseek_base_url="https://example.test/v1",
            openai_api_key="openai-key",
            matrix_verifier_model="gpt-4o-mini",
            default_model="deepseek-v4-flash",
        ),
    )
    _clear_provider_caches()

    provider = get_matrix_verifier_provider()

    assert isinstance(provider, OpenAICompatibleAdapter)
    assert provider is get_provider_for_model("gpt-4o-mini")

    _clear_provider_caches()
