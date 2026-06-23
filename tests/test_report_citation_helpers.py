"""Tests for report generation citation/aggregation helpers."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from app.services.report_generation import (
    _aggregate_sections,
    _build_content_markdown,
    _count_inlined_uuids,
    _strip_inlined_uuids,
)


# Standard test UUIDs (deterministic, not random)
UUID_IN_REFS = "7feb6873-4492-4a45-8158-6141f03ff4cf"
UUID_HALLUCINATED = "deadbeef-1234-5678-9abc-def012345678"


# ── _strip_inlined_uuids ──────────────────────────────────────────────────


def test_strip_uuid_present_in_ref_map():
    """UUIDs in ref_map are stripped silently (DEBUG log only)."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = f"Finding X [{UUID_IN_REFS}] is important."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 1
    assert UUID_IN_REFS not in cleaned
    # The leading space before [uuid] is also consumed
    assert cleaned == "Finding X is important."


def test_strip_uuid_hallucinated_logs_warning(caplog):
    """UUIDs NOT in ref_map are stripped AND emit a warning."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = f"Bogus claim [{UUID_HALLUCINATED}] that we should not trust."

    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 1
    assert UUID_HALLUCINATED not in cleaned
    assert cleaned == "Bogus claim that we should not trust."
    assert any(
        "deadbeef" in rec.message and "hallucinated" in rec.message
        for rec in caplog.records
    )


def test_strip_multiple_uuids_in_one_paragraph():
    """Multiple UUIDs in one text are all stripped in one pass."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = (
        f"Paper A [{UUID_IN_REFS}] and paper B "
        f"[{UUID_HALLUCINATED}] both agree."
    )

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 2
    assert "[" not in cleaned
    assert cleaned == "Paper A and paper B both agree."


def test_strip_preserves_text_without_uuids():
    """Texts without UUIDs are returned unchanged with count=0."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = "Plain prose with [1] and <sup>[2]</sup> citations."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 0
    assert cleaned == text


def test_strip_is_case_insensitive():
    """Uppercase hex digits in UUIDs are also matched."""
    ref_map = {"ABCDEF12-3456-7890-ABCD-EF1234567890": "[1]"}
    text = "Reference [ABCDEF12-3456-7890-ABCD-EF1234567890] is here."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 1
    assert cleaned == "Reference is here."


def test_strip_empty_text():
    """Empty / whitespace-only text returns empty with count=0."""
    ref_map = {UUID_IN_REFS: "[1]"}
    assert _strip_inlined_uuids("", ref_map) == ("", 0)


def test_strip_does_not_match_non_uuid_brackets():
    """Brackets with non-UUID content (e.g. citation [1]) are preserved."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = "Citation [1] and [24] are kept. Year [2024] is kept."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 0
    assert cleaned == text


# ── _count_inlined_uuids ─────────────────────────────────────────────────


def test_count_inlined_uuids_sums_across_sections():
    sections = [
        {
            "heading": "S1",
            "paragraphs": [
                {"text": f"A [{UUID_IN_REFS}] B", "citation_paper_ids": []},
                {"text": "no uuid here", "citation_paper_ids": []},
            ],
        },
        {
            "heading": "S2",
            "paragraphs": [
                {"text": f"C [{UUID_HALLUCINATED}] D", "citation_paper_ids": []},
            ],
        },
    ]
    assert _count_inlined_uuids(sections) == 2


def test_count_inlined_uuids_zero_on_clean_text():
    sections = [
        {"heading": "S1", "paragraphs": [{"text": "Clean."}]},
    ]
    assert _count_inlined_uuids(sections) == 0


# ── _build_content_markdown integration ──────────────────────────────────


def test_build_content_markdown_strips_inlined_uuids(caplog):
    """End-to-end: inlined UUIDs in section text are stripped from the
    rendered markdown, while numbered citation superscripts still appear
    via the citation_paper_ids array."""
    paper_id = UUID_IN_REFS
    sections = [
        {
            "heading": "Findings",
            "paragraphs": [
                {
                    "text": (
                        f"This is a finding [{paper_id}] supported by prior work."
                    ),
                    "citation_paper_ids": [paper_id],
                }
            ],
        }
    ]
    references = [
        {
            "project_paper_id": paper_id,
            "citation_label": "[1]",
            "title": "A paper",
            "authors": "Doe",
            "year": 2024,
            "url": "https://example.com",
        }
    ]

    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        md = _build_content_markdown(sections, references)

    # UUID must be gone
    assert paper_id not in md
    # Numbered citation must still appear (from citation_paper_ids)
    assert "<sup>[1]</sup>" in md
    # The telemetry warning should fire exactly once
    assert any(
        "Stripping 1 inlined paper UUID" in rec.message for rec in caplog.records
    )


def test_build_content_markdown_handles_hallucinated_uuids(caplog):
    """Hallucinated UUIDs (not in references) are stripped + warned."""
    sections = [
        {
            "heading": "Findings",
            "paragraphs": [
                {
                    "text": (
                        f"Claim [{UUID_HALLUCINATED}] is hallucinated."
                    ),
                    "citation_paper_ids": [],
                }
            ],
        }
    ]
    references: list[dict] = []

    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        md = _build_content_markdown(sections, references)

    assert UUID_HALLUCINATED not in md
    assert "Claim is hallucinated." in md


# ── _aggregate_sections retry ────────────────────────────────────────────


def test_aggregate_sections_succeeds_on_first_attempt():
    """Happy path: first attempt succeeds and returns the LLM's sections."""
    fake_provider = MagicMock()
    fake_provider.complete_structured = AsyncMock(
        return_value={
            "sections": [{"heading": "Improved", "paragraphs": []}],
        }
    )
    original_sections = [{"heading": "Original", "paragraphs": []}]

    result = asyncio.run(
        _aggregate_sections(
            sections=original_sections,
            safe_conflicts=[],
            safe_gaps=[],
            paper_catalog_str="catalog",
            provider=fake_provider,
        )
    )

    assert result == [{"heading": "Improved", "paragraphs": []}]
    assert fake_provider.complete_structured.await_count == 1
    # First attempt should use the bumped default 16k tokens
    assert (
        fake_provider.complete_structured.await_args.kwargs["max_tokens"] == 16000
    )


def test_aggregate_sections_retries_with_higher_max_tokens_on_failure(caplog):
    """If the first call fails (truncated JSON), retry with 24k tokens."""
    fake_provider = MagicMock()
    # First call raises truncated-JSON error, second call succeeds.
    fake_provider.complete_structured = AsyncMock(
        side_effect=[
            ValueError("Expecting ',' delimiter: line 1 column 26319 (char 26318)"),
            {"sections": [{"heading": "Improved", "paragraphs": []}]},
        ]
    )

    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        result = asyncio.run(
            _aggregate_sections(
                sections=[{"heading": "Original", "paragraphs": []}],
                safe_conflicts=[],
                safe_gaps=[],
                paper_catalog_str="catalog",
                provider=fake_provider,
            )
        )

    assert result == [{"heading": "Improved", "paragraphs": []}]
    assert fake_provider.complete_structured.await_count == 2
    # Second attempt must use the higher token budget
    assert (
        fake_provider.complete_structured.await_args_list[0].kwargs["max_tokens"]
        == 16000
    )
    assert (
        fake_provider.complete_structured.await_args_list[1].kwargs["max_tokens"]
        == 24000
    )
    # First failure should be logged
    assert any(
        "Section aggregation attempt 1 failed" in rec.message
        for rec in caplog.records
    )


def test_aggregate_sections_falls_back_after_exhausted_retries(caplog):
    """After 2 failed attempts, fall back to the original sections."""
    fake_provider = MagicMock()
    fake_provider.complete_structured = AsyncMock(
        side_effect=[
            ValueError("truncated json attempt 1"),
            ValueError("truncated json attempt 2"),
        ]
    )
    original_sections = [{"heading": "Original", "paragraphs": []}]

    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        result = asyncio.run(
            _aggregate_sections(
                sections=original_sections,
                safe_conflicts=[],
                safe_gaps=[],
                paper_catalog_str="catalog",
                provider=fake_provider,
            )
        )

    # Must return the ORIGINAL sections, not raise
    assert result is original_sections
    assert fake_provider.complete_structured.await_count == 2
    # Final fallback log
    assert any(
        "Section aggregation failed after retries" in rec.message
        for rec in caplog.records
    )


def test_aggregate_sections_returns_empty_when_sections_empty():
    """Empty sections input skips the LLM call entirely."""
    fake_provider = MagicMock()
    fake_provider.complete_structured = AsyncMock()

    result = asyncio.run(
        _aggregate_sections(
            sections=[],
            safe_conflicts=[],
            safe_gaps=[],
            paper_catalog_str="catalog",
            provider=fake_provider,
        )
    )

    assert result == []
    fake_provider.complete_structured.assert_not_called()
