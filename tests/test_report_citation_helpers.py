"""Tests for report generation citation/aggregation helpers."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, MagicMock

from app.services.report_generation import (
    _aggregate_sections,
    _audit_claim_grounding,
    _audit_section_citation_density,
    _build_content_markdown,
    _cap_conclusion_to_two_paragraphs,
    _claim_in_chunks,
    _count_inlined_uuids,
    _ensure_conclusion_section,
    _extract_numeric_claims,
    _format_reference_line,
    _normalise_claim_for_matching,
    _strip_inlined_uuids,
)
from app.services.hybrid_retrieval import RetrievedChunk


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
        "deadbeef" in rec.message and "hallucinated" in rec.message for rec in caplog.records
    )


def test_strip_multiple_uuids_in_one_paragraph():
    """Multiple UUIDs in one text are all stripped in one pass."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = f"Paper A [{UUID_IN_REFS}] and paper B [{UUID_HALLUCINATED}] both agree."

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


def test_strip_parenthesised_uuid():
    """UUIDs in parentheses — the dominant leak in the (4) review."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = (
        f"Surveys of the field note this trajectory ({UUID_IN_REFS}) and "
        f"other sources ({UUID_HALLUCINATED}) both agree."
    )

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 2
    assert UUID_IN_REFS not in cleaned
    assert UUID_HALLUCINATED not in cleaned
    # The post-processor also collapses the double-space artefact.
    assert "Surveys of the field note this trajectory and other sources both agree." == cleaned
    # The trailing comma before the close paren is cleaned up.
    assert ",)" not in cleaned


def test_strip_bracket_uuid_list():
    """Conclusion's [uuid1, uuid2, ...] list pattern is stripped in one pass."""
    ref_map = {UUID_IN_REFS: "[1]"}
    uuid2 = "8f013674-2f51-4638-a8f5-bee2f4a3135e"
    text = (
        f"Exposing the limits of unit-test-only coverage "
        f"[{UUID_IN_REFS}, {uuid2}]."
    )

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    # Two UUIDs in the list — counted correctly.
    assert n == 2
    assert UUID_IN_REFS not in cleaned
    assert uuid2 not in cleaned
    assert "Exposing the limits of unit-test-only coverage." in cleaned


def test_strip_three_uuid_list_with_hallucinated():
    """Three-item list with one hallucinated UUID still strips cleanly."""
    ref_map = {UUID_IN_REFS: "[1]"}
    uuid2 = "8f013674-2f51-4638-a8f5-bee2f4a3135e"
    text = f"Triangulated result [{UUID_IN_REFS}, {uuid2}, {UUID_HALLUCINATED}]."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 3
    assert UUID_IN_REFS not in cleaned
    assert uuid2 not in cleaned
    assert UUID_HALLUCINATED not in cleaned
    assert "Triangulated result." in cleaned


def test_strip_bare_uuid():
    """Bare UUIDs (no brackets / parens) are stripped with word boundaries."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = f"Bare id {UUID_IN_REFS} is gone, embedded0e9d3a90-1234-5678-9abc-def0123456780x is not."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 1
    assert UUID_IN_REFS not in cleaned
    assert "Bare id is gone," in cleaned
    # The embedded fake is not matched because of the negative lookbehind/ahead.
    assert "0e9d3a90-1234-5678-9abc-def0123456780x" in cleaned


def test_strip_collapsed_comma_artefact():
    """Trailing-comma artefacts from stripping are collapsed."""
    ref_map = {UUID_IN_REFS: "[1]"}
    text = f"List A ({UUID_IN_REFS},) and list B (, {UUID_IN_REFS},) are gone."

    cleaned, n = _strip_inlined_uuids(text, ref_map)

    assert n == 2
    # No trailing commas inside parens.
    assert ",)" not in cleaned
    # No leading commas inside parens.
    assert "(," not in cleaned


def test_strip_preserves_hyphenated_non_uuid_text():
    """Hyphens in regular words should not be mistaken for UUIDs."""
    ref_map = {}
    text = "Self-supervised and task-aware agents see state-of-the-art results."

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
                    "text": (f"This is a finding [{paper_id}] supported by prior work."),
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
    assert any("Stripping 1 inlined paper UUID" in rec.message for rec in caplog.records)


def test_build_content_markdown_handles_hallucinated_uuids(caplog):
    """Hallucinated UUIDs (not in references) are stripped + warned."""
    sections = [
        {
            "heading": "Findings",
            "paragraphs": [
                {
                    "text": (f"Claim [{UUID_HALLUCINATED}] is hallucinated."),
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


def test_build_content_markdown_adds_methodology_section():
    """Generated reports should explain corpus and synthesis method."""
    md = _build_content_markdown(
        sections=[
            {
                "heading": "Findings",
                "paragraphs": [
                    {
                        "text": "The corpus converges on evaluation fragility.",
                        "citation_paper_ids": [UUID_IN_REFS],
                    }
                ],
            }
        ],
        references=[
            {
                "project_paper_id": UUID_IN_REFS,
                "citation_label": "[1]",
                "title": "A paper",
                "authors": ["Doe"],
                "year": 2024,
                "url": "https://arxiv.org/abs/2401.00001",
                "reference_group": "scholarly",
            }
        ],
        methodology={
            "saved_papers": 12,
            "matrix_rows": 10,
            "research_gaps": 2,
            "conflicts": 1,
        },
    )

    assert md.startswith("## Methodology\n")
    assert "12 curated sources" in md
    assert "10 structured extraction records" in md
    assert "2 research-gap records" in md
    assert "1 conflicting-finding records" in md
    # The methodology should NOT use app-internal jargon.
    assert "saved project papers" not in md
    assert "literature-matrix rows" not in md
    assert "project-paper identifiers" not in md


def test_build_content_markdown_drops_llm_methodology_when_app_injects_one():
    """The backend-owned methodology section should be the only one rendered."""
    md = _build_content_markdown(
        sections=[
            {
                "heading": "Methodology",
                "paragraphs": [
                    {
                        "text": "The model wrote a duplicate methodology section.",
                        "citation_paper_ids": [UUID_IN_REFS],
                    }
                ],
            },
            {
                "heading": "Findings",
                "paragraphs": [
                    {
                        "text": "Agent benchmarks vary across tasks.",
                        "citation_paper_ids": [UUID_IN_REFS],
                    }
                ],
            },
        ],
        references=[
            {
                "project_paper_id": UUID_IN_REFS,
                "citation_label": "[1]",
                "title": "A paper",
                "authors": ["Doe"],
                "year": 2024,
                "url": "https://arxiv.org/abs/2401.00001",
                "reference_group": "scholarly",
            }
        ],
        methodology={
            "saved_papers": 50,
            "matrix_rows": 11,
            "research_gaps": 3,
            "conflicts": 0,
        },
    )

    assert md.count("## Methodology") == 1
    assert "The model wrote a duplicate methodology section." not in md
    assert "## Findings" in md
    assert "11 of 50 corpus entries" in md


def test_build_content_markdown_splits_industry_commentary_references():
    """Blog and leaderboard sources should not sit in the scholarly reference list."""
    references = [
        {
            "project_paper_id": UUID_IN_REFS,
            "citation_label": "[1]",
            "title": "A scholarly benchmark paper",
            "authors": ["Doe"],
            "year": 2026,
            "url": "https://arxiv.org/abs/2601.00001",
            "reference_group": "scholarly",
        },
        {
            "project_paper_id": UUID_HALLUCINATED,
            "citation_label": "[2]",
            "title": "SWE-Bench Coding Agent Leaderboard",
            "authors": [],
            "year": 2026,
            "url": "https://awesomeagents.ai/leaderboards/swe-bench",
            "reference_group": "industry_commentary",
        },
    ]

    md = _build_content_markdown([], references)

    references_pos = md.index("## References")
    commentary_pos = md.index("## Industry Commentary")
    scholarly_block = md[references_pos:commentary_pos]
    commentary_block = md[commentary_pos:]

    assert "A scholarly benchmark paper" in scholarly_block
    assert "SWE-Bench Coding Agent Leaderboard" not in scholarly_block
    assert "SWE-Bench Coding Agent Leaderboard" in commentary_block


def test_build_content_markdown_strips_parenthesised_uuids_e2e(caplog):
    """End-to-end: (uuid) inlined into section text is stripped, citation
    superscript from citation_paper_ids is preserved."""
    paper_id = UUID_IN_REFS
    sections = [
        {
            "heading": "Landscape",
            "paragraphs": [
                {
                    "text": (
                        f"Surveys frame this trajectory ({paper_id}) and the "
                        "shift to repository-level work."
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
            "title": "Survey",
            "authors": ["Doe"],
            "year": 2025,
            "url": "https://arxiv.org/abs/2501.00001",
            "reference_group": "scholarly",
        }
    ]

    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        md = _build_content_markdown(sections, references)

    assert paper_id not in md
    assert "<sup>[1]</sup>" in md
    # Trailing space + closing paren is collapsed.
    assert "trajectory and" in md
    assert "trajectory  and" not in md
    # Telemetry: the strip should have logged exactly one UUID stripped.
    assert any("Stripping 1 inlined paper UUID" in rec.message for rec in caplog.records)


def test_build_content_markdown_strips_uuid_list_e2e():
    """End-to-end: the Conclusion-style [uuid1, uuid2] list is stripped and
    the corresponding citation_paper_ids still render as two superscripts."""
    paper_a = UUID_IN_REFS
    paper_b = "8f013674-2f51-4638-a8f5-bee2f4a3135e"
    sections = [
        {
            "heading": "Conclusion",
            "paragraphs": [
                {
                    "text": (
                        f"Exposing the limits of unit-test-only coverage "
                        f"[{paper_a}, {paper_b}]."
                    ),
                    "citation_paper_ids": [paper_a, paper_b],
                }
            ],
        }
    ]
    references = [
        {
            "project_paper_id": paper_a,
            "citation_label": "[1]",
            "title": "RigorBench",
            "authors": ["A"],
            "year": 2026,
            "url": "https://arxiv.org/abs/2601.00001",
            "reference_group": "scholarly",
        },
        {
            "project_paper_id": paper_b,
            "citation_label": "[2]",
            "title": "SWE-ABS",
            "authors": ["B"],
            "year": 2026,
            "url": "https://arxiv.org/abs/2602.00002",
            "reference_group": "scholarly",
        },
    ]

    md = _build_content_markdown(sections, references)

    # No raw UUIDs in the rendered output.
    assert paper_a not in md
    assert paper_b not in md
    # Bracketed inline list must be gone.
    assert f"[{paper_a}, {paper_b}]" not in md
    # Citation superscripts for both refs should appear from the
    # citation_paper_ids array.
    assert "<sup>[1]</sup>" in md
    assert "<sup>[2]</sup>" in md


def test_format_reference_line_never_renders_empty_author():
    """Missing metadata should be explicit instead of blank author + n.d."""
    line = _format_reference_line(
        {
            "citation_label": "[1]",
            "authors": [],
            "year": None,
            "title": "RigorBench",
            "url": "https://arxiv.org/html/2606.22678",
        }
    )

    assert line.startswith("[1] Unknown author (n.d.).")
    assert "[1]  (n.d.)." not in line


def test_ensure_conclusion_section_appends_when_missing():
    """Reports should close with an evidence-backed conclusion."""
    paper_id = UUID(UUID_IN_REFS)
    sections = [
        {
            "heading": "Findings",
            "paragraphs": [
                {
                    "text": "Agentic systems extend repository-level workflows.",
                    "citation_paper_ids": [paper_id],
                }
            ],
        },
        {
            "heading": "Research Gaps",
            "paragraphs": [
                {
                    "text": "Efficiency-correctness reporting remains underdeveloped.",
                    "citation_paper_ids": [paper_id],
                }
            ],
        },
    ]

    result = _ensure_conclusion_section(
        sections,
        topic="autonomous coding agents",
        research_question="how agents differ from traditional code generation",
    )

    assert result[-1]["heading"] == "Conclusion"
    assert (
        "how agents differ from traditional code generation" in result[-1]["paragraphs"][0]["text"]
    )
    assert "unresolved gaps identified above" in result[-1]["paragraphs"][1]["text"]
    assert result[-1]["paragraphs"][0]["citation_paper_ids"] == [paper_id]


def test_ensure_conclusion_section_does_not_duplicate_existing_conclusion():
    """LLM-authored conclusion sections should be preserved once."""
    sections = [
        {
            "heading": "Conclusion",
            "paragraphs": [
                {
                    "text": "Existing conclusion.",
                    "citation_paper_ids": [UUID(UUID_IN_REFS)],
                }
            ],
        }
    ]

    result = _ensure_conclusion_section(
        sections,
        topic="autonomous coding agents",
        research_question=None,
    )

    # Identity is allowed to change because the function defensively
    # rewrites every section to enforce the 2-paragraph cap, but the
    # section count and the conclusion's existence must be preserved.
    assert len(result) == 1
    assert result[-1]["heading"] == "Conclusion"
    assert result[-1]["paragraphs"][0]["text"] == "Existing conclusion."


# ── _build_references renumbering ────────────────────────────────────────


def test_build_references_renumbers_scholarly_continuously():
    """Scholarly refs get [1], [2], [3] ... with no gaps from reclassified papers."""
    from app.services.report_generation import _build_references

    scholarly_id_1 = UUID(UUID_IN_REFS)
    scholarly_id_2 = UUID("11111111-2222-3333-4444-555555555555")
    industry_id = UUID(UUID_HALLUCINATED)

    pp_1 = MagicMock()
    pp_1.id = scholarly_id_1
    pp_1.paper_id = uuid4()
    paper_1 = MagicMock()
    paper_1.id = pp_1.paper_id
    paper_1.title = "Scholarly A"
    paper_1.authors = ["A"]
    paper_1.year = 2024
    paper_1.url = "https://arxiv.org/abs/2401.00001"
    paper_1.doi = "10.0000/aaa"
    paper_1.arxiv_id = None
    paper_1.semantic_scholar_id = None
    paper_1.openalex_id = None

    pp_2 = MagicMock()
    pp_2.id = scholarly_id_2
    pp_2.paper_id = uuid4()
    paper_2 = MagicMock()
    paper_2.id = pp_2.paper_id
    paper_2.title = "Scholarly B"
    paper_2.authors = ["B"]
    paper_2.year = 2024
    paper_2.url = "https://arxiv.org/abs/2401.00002"
    paper_2.doi = "10.0000/bbb"
    paper_2.arxiv_id = None
    paper_2.semantic_scholar_id = None
    paper_2.openalex_id = None

    pp_3 = MagicMock()
    pp_3.id = industry_id
    pp_3.paper_id = uuid4()
    paper_3 = MagicMock()
    paper_3.id = pp_3.paper_id
    paper_3.title = "Industry commentary"
    paper_3.authors = ["C"]
    paper_3.year = 2024
    paper_3.url = "https://lunexcoding.com/some-post"
    paper_3.doi = None
    paper_3.arxiv_id = None
    paper_3.semantic_scholar_id = None
    paper_3.openalex_id = None

    # AsyncMock's execute attribute must itself be awaitable; we sequence
    # the two execute() calls (project_papers, then papers) by counting.
    call_count = {"n": 0}

    async def execute(_stmt):
        call_count["n"] += 1
        result = MagicMock()
        if call_count["n"] == 1:
            result.scalars.return_value.all.return_value = [pp_1, pp_2, pp_3]
        else:
            result.scalars.return_value.all.return_value = [paper_1, paper_2, paper_3]
        return result

    db = MagicMock()
    db.execute = execute

    refs = asyncio.run(
        _build_references(
            db,
            {scholarly_id_1, scholarly_id_2, industry_id},
        )
    )

    labels = [r["citation_label"] for r in refs]
    groups = [r["reference_group"] for r in refs]
    # Two scholarly refs are numbered [1] and [2] (continuous, no gap)
    # The industry ref is numbered separately as [I-1].
    assert labels == ["[1]", "[2]", "[I-1]"]
    assert groups == ["scholarly", "scholarly", "industry_commentary"]


def test_classify_reference_group_routes_lunexcoding_to_industry():
    """lunexcoding.com / easycoding.tools / appxlab.io blogs are industry."""
    from app.services.report_generation import _classify_reference_group

    for url in (
        "https://lunexcoding.com/devin-vs-github-copilot",
        "https://easycoding.tools/blog/en/ranked",
        "https://blog.appxlab.io/2026/03/devin-vs-claude-code",
        "https://pith.science/paper/2602.08915",
        "https://particula.tech/blog/swe-bench-pro",
    ):
        paper = MagicMock()
        paper.url = url
        paper.title = "Some blog post"
        paper.doi = None
        paper.arxiv_id = None
        paper.semantic_scholar_id = None
        paper.openalex_id = None
        assert _classify_reference_group(paper) == "industry_commentary", url


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
    await_args = fake_provider.complete_structured.await_args
    assert await_args is not None
    # First attempt should use the bumped default 16k tokens
    assert await_args.kwargs["max_tokens"] == 16000


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
    assert fake_provider.complete_structured.await_args_list[0].kwargs["max_tokens"] == 16000
    assert fake_provider.complete_structured.await_args_list[1].kwargs["max_tokens"] == 24000
    # First failure should be logged
    assert any("Section aggregation attempt 1 failed" in rec.message for rec in caplog.records)


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
    assert any("Section aggregation failed after retries" in rec.message for rec in caplog.records)


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


# ── _cap_conclusion_to_two_paragraphs ──────────────────────────────────────


def test_cap_conclusion_to_two_paragraphs_trims_excess():
    """An LLM that emits 4 conclusion paragraphs is trimmed to 2."""
    p1 = {"text": "First paragraph.", "citation_paper_ids": [UUID(UUID_IN_REFS)]}
    p2 = {"text": "Second paragraph.", "citation_paper_ids": []}
    p3 = {"text": "Third paragraph.", "citation_paper_ids": [UUID(UUID_HALLUCINATED)]}
    p4 = {"text": "Fourth paragraph.", "citation_paper_ids": [UUID(UUID_HALLUCINATED)]}

    capped = _cap_conclusion_to_two_paragraphs(
        {"heading": "Conclusion", "paragraphs": [p1, p2, p3, p4]}
    )

    # Only the first two paragraphs are kept (verbatim).
    assert len(capped["paragraphs"]) == 2
    assert capped["paragraphs"][0]["text"] == "First paragraph."
    assert capped["paragraphs"][1]["text"] == "Second paragraph."
    # The dropped paragraphs' citations are unioned onto the LAST kept
    # paragraph so the references are not lost when the prose is trimmed.
    last = capped["paragraphs"][-1]
    assert UUID(UUID_HALLUCINATED) in last["citation_paper_ids"]
    # No duplicates of the same UUID.
    assert len(last["citation_paper_ids"]) == len(set(last["citation_paper_ids"]))
    # The kept paragraph 1's citations are preserved verbatim.
    assert UUID(UUID_IN_REFS) in capped["paragraphs"][0]["citation_paper_ids"]


def test_cap_conclusion_to_two_paragraphs_no_op_when_already_short():
    """A 1- or 2-paragraph conclusion is left untouched."""
    short = {"heading": "Conclusion", "paragraphs": [
        {"text": "Only one paragraph.", "citation_paper_ids": [UUID(UUID_IN_REFS)]}
    ]}
    assert _cap_conclusion_to_two_paragraphs(short) is short

    two = {"heading": "Conclusion", "paragraphs": [
        {"text": "First.", "citation_paper_ids": []},
        {"text": "Second.", "citation_paper_ids": [UUID(UUID_IN_REFS)]},
    ]}
    assert _cap_conclusion_to_two_paragraphs(two) is two


# ── _audit_section_citation_density ────────────────────────────────────────


def test_audit_section_citation_density_warns_for_thin_sections(caplog):
    """Sections with < 3 unique citations emit a warning."""
    sections = [
        {
            "heading": "Background",
            "paragraphs": [
                {"text": "Only one citation here.", "citation_paper_ids": [UUID(UUID_IN_REFS)]},
            ],
        },
        {
            "heading": "Healthy Section",
            "paragraphs": [
                {"text": "Cites three papers.", "citation_paper_ids": [
                    UUID(UUID_IN_REFS),
                    UUID(UUID_HALLUCINATED),
                    UUID("11111111-2222-3333-4444-555555555555"),
                ]},
            ],
        },
    ]
    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        result = _audit_section_citation_density(sections)

    # Sections are returned unchanged.
    assert result is sections
    # The thin section triggered a warning.
    assert any(
        "Background" in rec.message and "cites only 1" in rec.message
        for rec in caplog.records
    )
    # The healthy section did NOT trigger a warning.
    assert not any(
        "Healthy Section" in rec.message for rec in caplog.records
    )


def test_audit_section_citation_density_ignores_conclusion(caplog):
    """The Conclusion section is exempt from the 3-paper minimum."""
    sections = [
        {
            "heading": "Conclusion",
            "paragraphs": [
                {"text": "Short conclusion with 1 citation.",
                 "citation_paper_ids": [UUID(UUID_IN_REFS)]},
            ],
        }
    ]
    with caplog.at_level(logging.WARNING, logger="app.services.report_generation"):
        _audit_section_citation_density(sections)
    assert not any("Conclusion" in rec.message for rec in caplog.records)


# -----------------------------------------------------------------------------
# Claim grounding audit
# -----------------------------------------------------------------------------


def _make_chunk(paper_id: UUID, text: str) -> RetrievedChunk:
    """Build a minimal RetrievedChunk for unit tests."""
    return RetrievedChunk(
        project_paper_id=paper_id,
        paper_id=paper_id,
        chunk_id=uuid4(),
        title="",
        chunk_text=text,
        section_label=None,
        section_path=None,
        chunk_index=0,
        content_type=None,
        page_start=None,
        page_end=None,
        content_hash=None,
        score=0.0,
        keyword_score=0.0,
        vector_score=0.0,
    )


def test_extract_numeric_claims_finds_percentages_and_counts():
    text = (
        "RSTD reduced retry cost to 51.7% and 73.2% across workloads. "
        "OmniCode has 1,794 manually validated tasks. "
        "AIDev analyzed 456,535 PRs across 9 task categories."
    )
    claims = _extract_numeric_claims(text)
    # 51.7% and 73.2% (percent) plus 1,794 and 456,535 (large numbers)
    assert "51.7%" in claims
    assert "73.2%" in claims
    assert "1,794" in claims
    assert "456,535" in claims
    # 9 is too short to count as a claim
    assert "9" not in claims


def test_extract_numeric_claims_finds_ratios_and_token_counts():
    text = "170 of 500 issues remained unresolved, costing 436 tokens per retry."
    claims = _extract_numeric_claims(text)
    assert any("170 of 500" in c for c in claims)
    assert any("436 tokens" in c.lower() for c in claims)


def test_extract_numeric_claims_ignores_short_numbers():
    text = "We tested 5 agents on 3 benchmarks with 2 reviewers."
    claims = _extract_numeric_claims(text)
    # None of 5, 3, 2 has 3+ digits so they are skipped.
    assert claims == []


def test_normalise_claim_strips_commas():
    forms = _normalise_claim_for_matching("1,794")
    assert "1,794" in forms
    assert "1794" in forms


def test_normalise_claim_strips_percent_and_latex_escape():
    forms = _normalise_claim_for_matching("51.7%")
    # Should include at least the bare "51.7" form for LaTeX/raw matching
    assert any("51.7" in f for f in forms)


def test_claim_in_chunks_matches_with_and_without_commas():
    chunks = ["The dataset contains 1794 tasks in total."]
    assert _claim_in_chunks("1,794", chunks)


def test_claim_in_chunks_false_when_absent():
    chunks = ["The dataset contains 500 tasks in total."]
    assert not _claim_in_chunks("1,794", chunks)


def test_audit_claim_grounding_all_grounded():
    pid = UUID(UUID_IN_REFS)
    sections = [
        {
            "heading": "Results",
            "paragraphs": [
                {
                    "text": "RSTD reduced retry cost to 51.7% of baseline.",
                    "citation_paper_ids": [pid],
                }
            ],
        }
    ]
    chunks_by_paper = {
        pid: [_make_chunk(pid, "RSTD achieves 51.7% retry cost reduction.")]
    }
    audit = _audit_claim_grounding(sections, chunks_by_paper)
    # 51.7% (percent regex) and 51.7 (bare large number) are both extracted.
    # Both are grounded in the chunk text.
    assert audit["total_claims"] == 2
    assert audit["grounded_claims"] == 2
    assert audit["ungrounded_claims"] == 0
    assert audit["grounding_rate"] == 1.0
    assert audit["ungrounded_examples"] == []


def test_audit_claim_grounding_detects_cross_attribution():
    """The classic 'dâu ông nọ cắm căm bà kia' pattern:
    paper X is cited but the number is from paper Y.
    """
    paper_x = UUID(UUID_IN_REFS)
    paper_y = UUID(UUID_HALLUCINATED)
    sections = [
        {
            "heading": "Results",
            "paragraphs": [
                {
                    # Cites paper_x but quotes a number that lives only in paper_y.
                    "text": "According to [1], OmniCode contains 1,794 tasks.",
                    "citation_paper_ids": [paper_x],
                }
            ],
        }
    ]
    chunks_by_paper = {
        paper_x: [_make_chunk(paper_x, "We study runtime decomposition on RCA workloads.")],
        paper_y: [_make_chunk(paper_y, "OmniCode's benchmark contains 1,794 tasks.")],
    }
    audit = _audit_claim_grounding(sections, chunks_by_paper)
    assert audit["total_claims"] == 1
    assert audit["grounded_claims"] == 0
    assert audit["ungrounded_claims"] == 1
    assert audit["grounding_rate"] == 0.0
    assert audit["ungrounded_examples"][0]["claim"] == "1,794"
    assert audit["ungrounded_examples"][0]["section"] == "Results"
    # The cross-attribution is captured with the wrong paper in cited_papers.
    assert paper_x in [
        UUID(p) for p in audit["ungrounded_examples"][0]["cited_papers"]
    ]


def test_audit_claim_grounding_handles_multi_citation_paragraphs():
    """If any of the cited papers' chunks contains the number, the
    claim is considered grounded (the LLM is allowed to attribute a
    number to a paper only if *one* of the cited papers mentions it).
    """
    paper_x = UUID(UUID_IN_REFS)
    paper_y = UUID(UUID_HALLUCINATED)
    sections = [
        {
            "heading": "Results",
            "paragraphs": [
                {
                    "text": "OmniCode has 1,794 tasks [1][2].",
                    "citation_paper_ids": [paper_x, paper_y],
                }
            ],
        }
    ]
    chunks_by_paper = {
        paper_x: [_make_chunk(paper_x, "We propose a new orchestration pattern.")],
        paper_y: [_make_chunk(paper_y, "OmniCode's benchmark contains 1794 tasks.")],
    }
    audit = _audit_claim_grounding(sections, chunks_by_paper)
    assert audit["grounded_claims"] == 1
    assert audit["ungrounded_claims"] == 0


def test_audit_claim_grounding_ignores_paragraphs_without_numeric_claims():
    pid = UUID(UUID_IN_REFS)
    sections = [
        {
            "heading": "Discussion",
            "paragraphs": [
                {
                    "text": "We discuss qualitative themes and open questions.",
                    "citation_paper_ids": [pid],
                }
            ],
        }
    ]
    chunks_by_paper = {pid: [_make_chunk(pid, "Some text.")]}
    audit = _audit_claim_grounding(sections, chunks_by_paper)
    assert audit["total_claims"] == 0
    assert audit["grounding_rate"] == 1.0  # no claims, vacuously perfect


def test_audit_claim_grounding_handles_empty_inputs():
    audit = _audit_claim_grounding([], {})
    assert audit["total_claims"] == 0
    assert audit["grounding_rate"] == 1.0
    assert audit["ungrounded_examples"] == []


def test_audit_claim_grounding_records_at_most_five_examples():
    pid = UUID(UUID_IN_REFS)
    # Generate a paragraph with many fabricated large numbers.
    fake_numbers = " ".join(f"value{i}" for i in range(20))  # 20 placeholders
    text = " ".join(f"fabricated{n} {1000 + n}" for n in range(20))
    sections = [
        {
            "heading": "Fabricated",
            "paragraphs": [{"text": text, "citation_paper_ids": [pid]}],
        }
    ]
    chunks_by_paper = {pid: [_make_chunk(pid, "Nothing relevant here.")]}
    audit = _audit_claim_grounding(sections, chunks_by_paper)
    assert audit["ungrounded_claims"] >= 10
    assert len(audit["ungrounded_examples"]) <= 5
