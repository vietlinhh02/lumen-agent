"""Tests for language bias service."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.language_bias import (
    LanguageBiasAudit,
    QueryVariant,
    compute_bias_audit,
    detect_and_generate_variants,
)


def test_detect_and_generate_english_query():
    async def _test():
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "detected_language": "en",
            "variants": [
                {
                    "source": "semantic_scholar",
                    "query": "machine learning for NLP",
                    "language": "en",
                },
                {
                    "source": "arxiv",
                    "query": "machine learning natural language processing",
                    "language": "en",
                },
            ],
        }
        with patch("app.services.language_bias.get_provider", return_value=mock_provider):
            variants, detected_lang = await detect_and_generate_variants(
                "machine learning for NLP", ["en"]
            )
        assert detected_lang == "en"
        assert len(variants) >= 1
        assert all(v.language == "en" for v in variants)

    asyncio.run(_test())


def test_detect_and_generate_vietnamese_query():
    async def _test():
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "detected_language": "vi",
            "variants": [
                {
                    "source": "semantic_scholar",
                    "query": "RAG medical question answering",
                    "language": "en",
                },
                {
                    "source": "arxiv",
                    "query": "retrieval augmented generation medical QA",
                    "language": "en",
                },
                {"source": "exa", "query": "RAG hỏi đáp y khoa tiếng Việt", "language": "vi"},
            ],
        }
        with patch("app.services.language_bias.get_provider", return_value=mock_provider):
            variants, detected_lang = await detect_and_generate_variants(
                "RAG hỏi đáp y khoa", ["en", "vi"]
            )
        assert detected_lang == "vi"
        assert len(variants) >= 2
        lang_set = {v.language for v in variants}
        assert "en" in lang_set
        assert "vi" in lang_set

    asyncio.run(_test())


def test_compute_bias_audit_all_english():
    variants = [
        QueryVariant(source="semantic_scholar", query="ML for NLP", language="en"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 25},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert audit.policy == "balanced"
    assert audit.candidate_counts_by_language["en"] == 25
    assert audit.english_dominance_score == 1.0


def test_compute_bias_audit_mixed():
    variants = [
        QueryVariant(source="semantic_scholar", query="RAG medical QA", language="en"),
        QueryVariant(source="arxiv", query="RAG medical QA", language="en"),
        QueryVariant(source="exa", query="RAG y khoa", language="vi"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 15},
        {"source": "arxiv", "status": "ok", "result_count": 8},
        {"source": "exa", "status": "ok", "result_count": 5},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert audit.candidate_counts_by_language["en"] == 23
    assert audit.candidate_counts_by_language["vi"] == 5
    assert 0.0 < audit.english_dominance_score < 1.0


def test_compute_bias_audit_with_failed_source():
    variants = [
        QueryVariant(source="semantic_scholar", query="test", language="en"),
        QueryVariant(source="exa", query="kiểm tra", language="vi"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 10},
        {"source": "exa", "status": "failed", "result_count": 0, "message": "timeout"},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert audit.candidate_counts_by_language["en"] == 10
    assert audit.candidate_counts_by_language.get("vi", 0) == 0
    assert audit.english_dominance_score == 1.0


def test_compute_bias_audit_adjustments():
    variants = [
        QueryVariant(source="semantic_scholar", query="test", language="en"),
        QueryVariant(source="exa", query="kiểm tra", language="vi"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 10},
        {"source": "exa", "status": "ok", "result_count": 2},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert "included_original_language_query" in audit.adjustments_applied


def test_detect_llm_failure_graceful():
    async def _test():
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        with patch("app.services.language_bias.get_provider", return_value=mock_provider):
            variants, detected_lang = await detect_and_generate_variants("test", ["en"])
        assert detected_lang == "en"
        assert len(variants) == 1
        assert variants[0].source == "semantic_scholar"

    asyncio.run(_test())
