"""Smoke tests for the one-shot pdf_fulltext service."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import pdf_fulltext
from app.services.pdf_extraction import router as extraction_router
from app.services.pdf_extraction.quality import score_quality
from app.services.pdf_fulltext import chunk_text, extract_text


class _FakeOxideEngine:
    """Stand-in for PdfOxideEngine that returns a fixed markdown string."""

    name = "pdf_oxide_fake"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def extract(self, _pdf_path: Path) -> str | None:
        self.calls += 1
        # Real engines normalise (strip null bytes / whitespace). The fake
        # mirrors that contract so the router sees a clean string.
        cleaned = self._text.replace("\x00", "").strip() if self._text else ""
        return cleaned or None

    def quality_score(self, text: str) -> float:
        return score_quality(text).score


class _FakePyPdfEngine:
    """Stand-in for PyPdfEngine that returns a fixed plain-text string."""

    name = "pypdf_fake"

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    def extract(self, _pdf_path: Path) -> str | None:
        self.calls += 1
        cleaned = self._text.replace("\x00", "").strip() if self._text else ""
        return cleaned or None


class _EmptyEngine:
    """Engine that fails to extract anything (e.g. image-only PDF)."""

    name = "empty"

    def extract(self, _pdf_path: Path) -> str | None:
        return None


def test_extract_text_returns_none_when_no_engine_produces_text(tmp_path: Path) -> None:
    """The router returns ``None`` only when every engine fails."""
    bad = tmp_path / "nope.pdf"
    bad.write_bytes(b"not a pdf")
    with patch.object(
        extraction_router,
        "_DEFAULT_ENGINES",
        [_EmptyEngine()],
    ):
        assert extract_text(bad) is None


def test_extract_text_strips_null_bytes_and_empty_output(tmp_path: Path) -> None:
    """Engines normalise raw output; the router only scores.

    Mirrors the real PdfOxideEngine's contract: a payload that strips
    down to empty text returns ``None``, not a whitespace string.
    """
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")

    class _NullOnlyEngine:
        name = "null_only"

        def extract(self, _pdf_path: Path) -> str | None:
            raw = "\x00   \n"
            cleaned = raw.replace("\x00", "").strip() if raw else ""
            return cleaned or None

    with patch.object(extraction_router, "_DEFAULT_ENGINES", [_NullOnlyEngine()]):
        assert extract_text(pdf) is None


def test_extract_text_returns_cleaned_markdown(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    fake_oxide = _FakeOxideEngine("## Abstract\n\nSome text\x00 with junk.")
    with patch.object(extraction_router, "_DEFAULT_ENGINES", [fake_oxide]):
        text = extract_text(pdf)
        assert text is not None
        assert "\x00" not in text
        assert "## Abstract" in text


def test_extract_text_picks_highest_quality_engine(tmp_path: Path) -> None:
    """The router picks the highest-scoring engine, not just the first one.

    Regression test for the previous oxide-vs-pypdf tie-breaker. Here we
    give pdf_oxide a structurally weak result (no paragraphs, no periods)
    and pypdf a strong one (clear paragraphs + sentences + alpha text).
    """
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")

    weak = (
        "Research Article\n"
        "Correspondence author\n"
        "This body has no real section heading and gets treated as full text."
    )
    strong = (
        "## Abstract\n\n"
        "We present a new framework for routing PDF extraction across\n"
        "heterogeneous backends and evaluate it on a corpus of 200 papers.\n\n"
        "## Introduction\n\n"
        "PDF extraction is hard. Layout, fonts, and encoding all conspire\n"
        "to defeat naive regex pipelines. In this paper we propose a\n"
        "5-signal quality audit that drives a self-healing routing layer."
    )

    oxide = _FakeOxideEngine(weak)
    pypdf = _FakePyPdfEngine(strong)
    with patch.object(extraction_router, "_DEFAULT_ENGINES", [oxide, pypdf]):
        result = extract_text(pdf)
    assert result == strong
    assert oxide.calls == 1
    assert pypdf.calls == 1


def test_chunk_text_handles_short_input() -> None:
    assert chunk_text("") == []
    # No section headers => wrapped in a single "Full Text" chunk.
    short = chunk_text("single short line")
    assert len(short) == 1
    assert short[0].section_label == "Full Text"


def test_chunk_text_splits_on_section_headers() -> None:
    body = (
        "## Abstract\n\nA short abstract that has enough words to be kept. " * 5
        + "\n\n## Introduction\n\nThe intro paragraph that is also long enough. " * 5
    )
    chunks = chunk_text(body)
    assert len(chunks) >= 1
    assert all(c.text for c in chunks)


def test_normalize_text_strips_bold_markdown() -> None:
    text = "**bold** word and *italic* word and `code` word"
    assert pdf_fulltext._normalize_text(text) == "bold word and italic word and code word"


def test_normalize_text_strips_arxiv_watermark() -> None:
    text = "# arXiv:2403.05530v1 [cs.CL] 8 Mar 2024\n\nBody text here."
    out = pdf_fulltext._normalize_text(text)
    assert "arXiv:" not in out
    assert "Body text here." in out


def test_normalize_text_strips_toc_entry_lines() -> None:
    text = (
        "I. Introduction 1\n"
        "A. Background 3\n"
        "B. Methods 5\n"
        "II. Related work 7\n"
    )
    out = pdf_fulltext._normalize_text(text)
    # All TOC entries (uppercase letter + dot + Title + page) should be gone
    assert "A. Background" not in out
    assert "B. Methods" not in out
    assert "II. Related work" not in out


def test_normalize_text_strips_inline_email() -> None:
    text = "Author Name Tel.: +32 123 E-mail: a@b.c affiliation"
    out = pdf_fulltext._normalize_text(text)
    assert "@" not in out
    assert "E-mail" not in out


def test_normalize_text_strips_publisher_footer() -> None:
    text = "© 2024 IEEE\n\nThe actual content paragraph here."
    out = pdf_fulltext._normalize_text(text)
    assert "©" not in out
    assert "The actual content paragraph here." in out


def test_add_overlap_skips_short_tail() -> None:
    # When the previous chunk's tail has no 4+ char word, don't prepend
    prev = "ab cd ef gh ij kl"
    next_chunk = "next chunk body"
    out = pdf_fulltext._add_overlap(prev, next_chunk)
    assert out == next_chunk


def test_add_overlap_skips_sentence_ending_tail() -> None:
    # When the previous chunk ends with a sentence terminator, skip overlap
    prev = ("long body " * 20) + "Final sentence."
    next_chunk = "next body"
    out = pdf_fulltext._add_overlap(prev, next_chunk)
    assert out == next_chunk


def test_add_overlap_prepends_useful_context() -> None:
    prev = "long body " * 20
    next_chunk = "next body"
    out = pdf_fulltext._add_overlap(prev, next_chunk)
    assert out.startswith("[…")
    assert "next body" in out


def test_classify_chunk_text_detects_equation() -> None:
    # Math-heavy with mostly symbols
    text = "∑ ∑ ∑ ∑ ∑ a² + b² = c² ∫ ∂ φ ≈ 0" * 5
    assert pdf_fulltext._classify_chunk_text(text) == "equation"


def test_classify_chunk_text_detects_pdf_oxide_ascii_equations() -> None:
    text = """
    area of the horizon of the black hole
    m t ω 1 + 2r
    dr rdΩ ) (1) 4ω
    m t) = and k = 0
    µT = diag(ν
    p t, r ) = ρ
    """
    assert pdf_fulltext._classify_chunk_text(text) == "equation"


def test_classify_chunk_text_keeps_single_inline_formula_as_narrative() -> None:
    text = (
        "We study a bouncing cosmology where t = 0 changes the near-bounce "
        "evolution, but the paragraph remains explanatory prose."
    )
    assert pdf_fulltext._classify_chunk_text(text) == "narrative"


def test_classify_chunk_text_keeps_narrative_with_greek_as_narrative() -> None:
    """Narrative paragraphs that mention Greek letters are not equations."""
    text = (
        "The cosmological parameters α and β determine the early-universe "
        "dynamics. We show that for α > 0.05 the inflation rate exceeds "
        "the observational bound from Planck, while β stays close to unity "
        "throughout the allowed range. This contradicts the earlier claim "
        "by Smith et al. that both parameters are unconstrained."
    )
    assert pdf_fulltext._classify_chunk_text(text) == "narrative"


def test_classify_chunk_text_recognises_display_math_block() -> None:
    """$$...$$ blocks from Docling must classify as equation even in prose."""
    text = (
        "Einstein's field equation follows from the Einstein-Hilbert action.\n\n"
        "$$G_{\\mu\\nu} = 8\\pi G T_{\\mu\\nu}$$\n\n"
        "It couples spacetime curvature to the stress-energy tensor."
    )
    assert pdf_fulltext._classify_chunk_text(text) == "equation"


# ── Engine-aware cleanup (Phase 3) ─────────────────────────────────────────────


def test_normalize_text_skips_layout_cleanup_for_docling() -> None:
    """Docling output already strips page furniture, so layout regexes are skipped."""
    # Simulate Docling output that happens to contain text patterns that
    # the layout-cleanup regexes would normally attack (TOC entry, page
    # number, arXiv watermark). With source_engine="docling" the output
    # is returned unchanged (after markdown noise stripping).
    docling_text = (
        "## Introduction\n"
        "Some prose here.\n"
        "arXiv:2401.12345v1 [cs.AI] 5 Jan 2024\n"  # would be stripped for fast tier
        "1. Background 1\n"  # looks like TOC entry
        "**13**\n"  # bold page number
    )
    out = pdf_fulltext._normalize_text(docling_text, source_engine="docling")
    # Docling engine: keep all lines (markdown noise still stripped).
    assert "arXiv:2401.12345v1" in out
    assert "1. Background 1" in out
    assert "13" in out


def test_normalize_text_runs_layout_cleanup_for_fast_tier() -> None:
    """pdf_oxide / pypdf output still needs full layout cleanup."""
    text = (
        "## Introduction\n"
        "Some prose here.\n"
        "arXiv:2401.12345v1 [cs.AI] 5 Jan 2024\n"
        "1. Background 1\n"
        "**13**\n"
    )
    out = pdf_fulltext._normalize_text(text, source_engine="pdf_oxide")
    assert "arXiv:" not in out
    assert "1. Background 1" not in out


def test_normalize_text_treats_none_engine_as_legacy() -> None:
    """``source_engine=None`` preserves the legacy always-clean behaviour."""
    text = "arXiv:2401.12345v1 [cs.AI] 5 Jan 2024"
    out = pdf_fulltext._normalize_text(text)
    assert "arXiv:" not in out


def test_strip_markdown_noise_is_engine_agnostic() -> None:
    """Markdown noise strip runs for both fast tier and Docling."""
    text = "**bold** and *italic* and `code`"
    assert pdf_fulltext._strip_markdown_noise(text) == "bold and italic and code"


def test_strip_layout_artifacts_drops_arxiv_watermark() -> None:
    """Sanity check on the extracted layout-cleanup helper."""
    text = "Body text\narXiv:2401.12345v1 [cs.AI] 5 Jan 2024\nMore body"
    out = pdf_fulltext._strip_layout_artifacts(text)
    assert "arXiv:" not in out
    assert "Body text" in out
    assert "More body" in out


def test_classify_chunk_text_detects_table_pipe() -> None:
    text = "| col1 | col2 |\n|---|---|\n| a | b |"
    assert pdf_fulltext._classify_chunk_text(text) == "table"


def test_classify_chunk_text_detects_figure_caption() -> None:
    text = "Figure 1: A diagram of the system architecture."
    assert pdf_fulltext._classify_chunk_text(text) == "figure_caption"


@pytest.mark.asyncio
async def test_process_pdf_marks_ocr_required_for_empty_text(tmp_path: Path) -> None:
    from app.services.pdf_fulltext import process_pdf

    class _FakeSession:
        async def execute(self, *_args, **_kwargs):  # noqa: D401
            raise AssertionError("DB should not be hit when text is empty")

    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"%PDF")

    class _EmptyEngine:
        name = "empty"

        def extract(self, _pdf_path: Path) -> str | None:
            return None

    with patch.object(extraction_router, "_DEFAULT_ENGINES", [_EmptyEngine()]):
        result = await process_pdf(cast(AsyncSession, _FakeSession()), uuid4(), pdf)
    assert result.status == "ocr_required"
    assert result.chunk_count == 0
