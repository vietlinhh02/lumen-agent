"""Smoke tests for the one-shot pdf_fulltext service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services import pdf_fulltext
from app.services.pdf_fulltext import chunk_text, extract_text


def test_extract_text_returns_none_when_pdf_oxide_cannot_open(tmp_path: Path) -> None:
    bad = tmp_path / "nope.pdf"
    bad.write_bytes(b"not a pdf")
    with patch.object(pdf_fulltext, "PdfDocument", side_effect=RuntimeError("bad")):
        assert extract_text(bad) is None


def test_extract_text_strips_null_bytes_and_empty_output(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")

    class _Doc:
        def to_markdown_all(self, **_kwargs) -> str:  # noqa: D401
            return "\x00   \n"

    with patch.object(pdf_fulltext, "PdfDocument", return_value=_Doc()):
        assert extract_text(pdf) is None


def test_extract_text_returns_cleaned_markdown(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")

    class _Doc:
        def to_markdown_all(self, **_kwargs) -> str:
            return "## Abstract\n\nSome text\x00 with junk."

    with patch.object(pdf_fulltext, "PdfDocument", return_value=_Doc()):
        text = extract_text(pdf)
        assert text is not None
        assert "\x00" not in text
        assert "## Abstract" in text


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

    class _Doc:
        def to_markdown_all(self, **_kwargs) -> str:
            return ""

    with patch.object(pdf_fulltext, "PdfDocument", return_value=_Doc()):
        result = await process_pdf(_FakeSession(), object(), pdf)  # type: ignore[arg-type]
    assert result.status == "ocr_required"
    assert result.chunk_count == 0
