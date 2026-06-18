"""Unit tests for the 5-signal quality scorer and self-healing router."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.pdf_extraction.quality import (
    GOOD_SCORE,
    score_pages,
    score_quality,
)
from app.services.pdf_extraction.router import (
    PdfOxideEngine,
    PyPdfEngine,
    extract_pages_with_routing,
    extract_with_routing,
    list_registered_engines,
    register_engine,
)

# ── score_quality: per-signal behaviour ──────────────────────────────────


def test_score_quality_returns_zero_for_empty_input() -> None:
    q = score_quality("")
    assert q.score == 0.0
    assert q.char_count == 0
    assert q.weakest_signal == "density"


def test_score_quality_returns_zero_for_none() -> None:
    q = score_quality(None)
    assert q.score == 0.0


def test_alphabetic_ratio_high_for_prose() -> None:
    prose = "We present a new routing strategy that selects the highest-quality PDF backend."
    q = score_quality(prose)
    assert q.alpha_ratio > 0.7


def test_alphabetic_ratio_low_for_symbol_soup() -> None:
    soup = "∑∏∫ ±÷×=≠≈ ≡ → ↔ ∈ ∉ ⊂ ⊃ ∪ ∩ ∅ √ ∞ ∂ ∇"
    q = score_quality(soup)
    assert q.alpha_ratio < 0.1


def test_structure_coherence_high_for_paragraphs_and_sentences() -> None:
    text = (
        "We present a new routing strategy.\n\n"
        "The strategy evaluates each backend.\n\n"
        "Each backend produces a candidate text stream.\n\n"
        "The router selects the highest-quality extraction."
    )
    q = score_quality(text)
    assert q.structure > 0.6


def test_structure_coherence_low_for_one_word_lines() -> None:
    # Many short fragments with no periods, no blank-line paragraphs.
    text = "\n".join("abc" for _ in range(50))
    q = score_quality(text)
    assert q.structure < 0.5


def test_mojibake_perfect_for_clean_text() -> None:
    text = "This is a clean PDF extraction result with no encoding issues."
    q = score_quality(text)
    assert q.mojibake == 1.0


def test_mojibake_drops_for_double_encoded_utf8() -> None:
    # Ã© is the most common mojibake pattern: 'é' encoded as UTF-8 then
    # re-decoded as Latin-1.
    text = "CafÃ© Ã  table NaÃ¯ve prÃ©sentation Ã©vÃ©nement"
    q = score_quality(text)
    assert q.mojibake < 0.7


def test_mojibake_flags_replacement_char() -> None:
    text = "Some text with a replacement char \ufffd in the middle."
    q = score_quality(text)
    assert q.mojibake < 1.0


def test_density_low_for_image_only_page() -> None:
    # Only 3 short lines, very sparse — typical of a near-empty extraction.
    text = "Page header\nA title\nEnd"
    q = score_quality(text)
    assert q.density < 0.5


def test_density_low_for_very_short_text() -> None:
    q = score_quality("only ten chars")
    assert q.density < 0.5


def test_density_healthy_for_normal_line_lengths() -> None:
    # ~80 chars per line is the sweet spot.
    line = "The quick brown fox jumps over the lazy dog. " * 2
    text = "\n".join(line for _ in range(20))
    q = score_quality(text)
    assert q.density > 0.5


def test_column_order_drops_for_interleaved_pattern() -> None:
    # Simulate interleaved two-column reading: short citation-y lines.
    text = "\n".join(
        [
            "Smith et al. (2020).",
            "Brown, J. and Jones, K.",
            "Patel et al. (2019).",
            "Garcia, M., 2018.",
            "Lee et al. (2017).",
            "Wang, X. and Liu, Y.",
            "Kumar et al. (2016).",
            "Singh, R., 2015.",
        ]
    )
    q = score_quality(text)
    assert q.column_order < 0.5


def test_column_order_clean_for_normal_prose() -> None:
    text = (
        "We present a new routing layer for PDF extraction. The layer\n"
        "evaluates each backend via five quality signals: text density,\n"
        "alphabetic ratio, structural coherence, mojibake detection,\n"
        "and reading-order cleanliness. The router then selects the\n"
        "highest-scoring backend for each document."
    )
    q = score_quality(text)
    assert q.column_order == 1.0


# ── score_quality: composite behaviour ───────────────────────────────────


def test_composite_score_weight_matches_published_formula() -> None:
    """Spot-check that the composite uses the documented weights."""

    class _Stub:
        def __init__(self, density=1.0, alpha=1.0, structure=1.0, mojibake=1.0, column=1.0):
            self.density = density
            self.alpha_ratio = alpha
            self.structure = structure
            self.mojibake = mojibake
            self.column_order = column
            self.score = (
                0.30 * density
                + 0.25 * alpha
                + 0.20 * structure
                + 0.15 * mojibake
                + 0.10 * column
            )
            self.char_count = 100
            self.weakest_signal = "density"

    text = "Hello world " * 30
    q = score_quality(text)
    # Compare against a hand-computed reference using the same signals.
    reference = _Stub(
        density=q.density,
        alpha=q.alpha_ratio,
        structure=q.structure,
        mojibake=q.mojibake,
        column=q.column_order,
    )
    assert q.score == pytest.approx(reference.score, abs=1e-6)


def test_score_quality_is_good_for_well_extracted_paper() -> None:
    """A realistic extraction should clear the GOOD_SCORE bar."""
    # A snippet that mirrors what pdf_oxide emits for a clean paper.
    text = (
        "## Abstract\n\n"
        "We present a self-healing PDF extraction router. Our system\n"
        "evaluates each extraction backend against five quality signals\n"
        "and selects the highest-scoring result for each document.\n\n"
        "## Introduction\n\n"
        "PDFs are a 2D spatial document format. Naive text extraction\n"
        "tools read them as a 1D stream of lines and lose the original\n"
        "reading order. We argue that layout-aware extraction is required\n"
        "for robust scientific document processing.\n\n"
        "## Method\n\n"
        "Our router runs pdf_oxide first because it preserves markdown\n"
        "headings. When its output fails the quality audit we re-extract\n"
        "with pypdf, which produces a cleaner column-separated result on\n"
        "some two-column journal papers."
    )
    q = score_quality(text)
    assert q.score >= GOOD_SCORE
    assert q.is_good


def test_weakest_signal_points_to_real_failure() -> None:
    """When mojibake dominates, weakest_signal should name it."""
    text = (
        "CafÃ© prÃ©sentation Ã©vÃ©nement NoÃ¯ve garÃ§on trÃ¨s agrÃ©able\n"
        "PiÃ±ata jalapeÃ±o maÃ±ana cumpleaÃ±os enseÃ±ar\n"
        "EspaÃ±a corazÃ³n otoÃ±o niÃ±o"
    )
    q = score_quality(text)
    assert q.weakest_signal == "mojibake"


# ── score_pages ──────────────────────────────────────────────────────────


def test_score_pages_returns_one_metric_per_page() -> None:
    pages = ["We present a routing strategy.", "Another page with prose text here."]
    metrics = score_pages(pages)
    assert len(metrics) == 2
    assert metrics[0].page_number == 1
    assert metrics[1].page_number == 2


def test_score_pages_handles_empty_page() -> None:
    metrics = score_pages(["Some prose here.", "", "More prose on page 3."])
    assert metrics[1].char_count == 0


# ── router: engine behaviour ─────────────────────────────────────────────


def test_registered_engines_include_default_backends() -> None:
    names = list_registered_engines()
    assert "pdf_oxide" in names
    assert "pypdf" in names


class _RecordingEngine:
    def __init__(self, name: str, text: str | None) -> None:
        self.name = name
        self._text = text
        self.calls = 0

    def extract(self, _pdf_path: Path) -> str | None:
        self.calls += 1
        return self._text


def test_router_runs_all_engines_and_picks_highest_score(tmp_path: Path) -> None:
    """The router picks the highest-scoring engine, not just the first one.

    Regression test for the previous oxide-vs-pypdf tie-breaker. We give
    the first engine a short stub and the second a realistic multi-paragraph
    extraction; the 5-signal scorer must rate the second higher.
    """
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    weak = _RecordingEngine("weak", "This is one short line with no paragraph structure.")
    strong = _RecordingEngine(
        "strong",
        (
            "We present a new routing strategy for PDF extraction. The strategy "
            "evaluates each backend via five quality signals and selects the "
            "highest-scoring result for downstream chunking and embedding.\n\n"
            "PDFs are a 2D spatial document format. Naive text extraction tools "
            "read them as a 1D stream of lines and lose the original reading "
            "order. In this paper we propose a layout-aware extraction pipeline "
            "that addresses the failure modes of pure regex cleanup.\n\n"
            "Our router runs pdf_oxide first because it preserves markdown "
            "headings. When its output fails the quality audit we re-extract "
            "with pypdf, which produces a cleaner column-separated result on "
            "some two-column journal papers. The router exposes an extensible "
            "engine registry so future Docling or MinerU adapters can plug in."
        ),
    )
    result = extract_with_routing(pdf, engines=[weak, strong])
    assert result.engine == "strong"
    assert weak.calls == 1
    assert strong.calls == 1
    assert result.quality.score > 0.5
    assert result.succeeded


def test_router_returns_none_text_when_every_engine_fails(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    failing = _RecordingEngine("failing", None)
    result = extract_with_routing(pdf, engines=[failing])
    assert result.text is None
    assert not result.succeeded
    assert result.quality.score == 0.0


def test_router_flags_fell_back_when_below_min_score(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    weak = _RecordingEngine("weak", "two words")
    # Very high min_score so the best result still falls back.
    result = extract_with_routing(pdf, engines=[weak], min_score=0.99)
    assert result.fell_back
    assert result.engine == "weak"


def test_router_does_not_flag_fell_back_when_above_min_score(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    body = (
        "## Abstract\n\n"
        "We present a self-healing PDF extraction router. Our system evaluates\n"
        "each backend against five quality signals.\n\n"
        "## Introduction\n\n"
        "PDFs are a 2D spatial document format. Naive text extraction tools\n"
        "read them as a 1D stream and lose the original reading order.\n\n"
        "## Method\n\n"
        "Our router runs pdf_oxide first because it preserves markdown headings."
    )
    good = _RecordingEngine("good", body)
    result = extract_with_routing(pdf, engines=[good])
    assert not result.fell_back


def test_router_engine_failure_is_swallowed(tmp_path: Path) -> None:
    """An engine that raises must not crash the router."""

    class _RaisingEngine:
        name = "raising"

        def extract(self, _pdf_path: Path) -> str | None:
            raise RuntimeError("boom")

    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    fallback = _RecordingEngine("fallback", "Some prose text here.")
    result = extract_with_routing(pdf, engines=[_RaisingEngine(), fallback])
    assert result.engine == "fallback"
    assert result.text == "Some prose text here."


def test_router_audit_trail_records_every_engine(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    a = _RecordingEngine("a", "First engine output.")
    b = _RecordingEngine("b", "Second engine output that is longer and richer.")
    result = extract_with_routing(pdf, engines=[a, b])
    assert [name for name, _ in result.tried] == ["a", "b"]


def test_register_engine_prepends_when_at_front(tmp_path: Path) -> None:
    class _FirstEngine:
        name = "_test_first"

        def extract(self, _pdf_path: Path) -> str | None:
            return "first"

    # Remove if present from a previous test.
    from app.services.pdf_extraction import router as _router

    _router._DEFAULT_ENGINES[:] = [e for e in _router._DEFAULT_ENGINES if e.name != "_test_first"]
    register_engine(_FirstEngine(), at_front=True)
    assert _router._DEFAULT_ENGINES[0].name == "_test_first"
    _router._DEFAULT_ENGINES.pop(0)


# ── Public engine classes surface the protocol ───────────────────────────


def test_default_engines_implement_protocol() -> None:
    """Both engines must satisfy the ExtractionEngine contract."""
    for engine in (PdfOxideEngine(), PyPdfEngine()):
        assert hasattr(engine, "name")
        assert hasattr(engine, "extract")
        assert callable(engine.extract)
        assert isinstance(engine.name, str)


# ── Fallback tier (Docling) ───────────────────────────────────────────


class _RecordingFallback:
    """Stand-in for DoclingEngine in fallback tests."""

    def __init__(self, text: str | None, *, name: str = "fake_fallback") -> None:
        self.name = name
        self._text = text
        self.calls = 0

    def extract(self, _pdf_path: Path) -> str | None:
        self.calls += 1
        return self._text


def test_router_skips_fallback_when_fast_tier_passes(tmp_path: Path) -> None:
    """The fast tier satisfying min_score must skip fallback entirely."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    fast = _RecordingFallback(None, name="fast")
    fb = _RecordingFallback("would be amazing but never called", name="fb")
    original_fast = list(_router._DEFAULT_ENGINES)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._DEFAULT_ENGINES[:] = [fast]
        _router._FALLBACK_ENGINES[:] = [fb]
        extract_with_routing(pdf, min_score=0.0)
    finally:
        _router._DEFAULT_ENGINES[:] = original_fast
        _router._FALLBACK_ENGINES[:] = original_fb
    assert fb.calls == 0


def test_router_invokes_fallback_when_fast_tier_below_min(tmp_path: Path) -> None:
    """When the fast tier falls below min_score, the fallback tier runs.

    Fast returns a fragment so it scores ~0.65; we set min_score=0.7 so
    the router escalates. The fallback returns multi-paragraph text
    that scores ~0.94, which clears the bar.
    """
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    fast = _RecordingFallback("ab", name="fast")
    fb = _RecordingFallback(
        "## Abstract\n\nThis is a multi-paragraph extraction with proper "
        "section headers and complete sentences throughout.\n\n"
        "## Introduction\n\n"
        "The introduction explains the paper's contribution clearly. "
        "The router should prefer this output because it scores higher.",
        name="docling",
    )
    original_fast = list(_router._DEFAULT_ENGINES)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._DEFAULT_ENGINES[:] = [fast]
        _router._FALLBACK_ENGINES[:] = [fb]
        result = extract_with_routing(pdf, min_score=0.7)
    finally:
        _router._DEFAULT_ENGINES[:] = original_fast
        _router._FALLBACK_ENGINES[:] = original_fb
    assert fast.calls == 1
    assert fb.calls == 1
    assert result.engine == "docling"
    assert not result.fell_back
    assert result.quality.score > 0.7


def test_router_can_disable_fallback_via_flag(tmp_path: Path) -> None:
    """``use_fallback=False`` must skip the fallback tier entirely."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    fast = _RecordingFallback("ab", name="fast")
    fb = _RecordingFallback("never called", name="fb")
    original_fast = list(_router._DEFAULT_ENGINES)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._DEFAULT_ENGINES[:] = [fast]
        _router._FALLBACK_ENGINES[:] = [fb]
        result = extract_with_routing(pdf, min_score=0.99, use_fallback=False)
    finally:
        _router._DEFAULT_ENGINES[:] = original_fast
        _router._FALLBACK_ENGINES[:] = original_fb
    assert fb.calls == 0
    assert result.fell_back


def test_register_optional_fallback_engines_handles_missing_dep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the docling extra isn't installed, registration is a no-op."""
    from app.services.pdf_extraction import router as _router

    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        # Simulate docling not being importable.
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):  # noqa: ANN401
            if name.startswith("docling") or "docling" in name:
                raise ImportError("docling not installed in test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        registered = _router.register_optional_fallback_engines()
    finally:
        _router._FALLBACK_ENGINES[:] = original_fb
    assert registered == []


# ── Docling markdown builder preserves formulas ─────────────────────────


class _FakeItem:
    """Stand-in for a Docling text item."""

    def __init__(self, label: str, text: str = "", orig: str = "") -> None:
        self.label = label
        self.text = text
        self.orig = orig


class _FakeDoc:
    """Stand-in for a Docling document with .texts list."""

    def __init__(self, items: list[_FakeItem]) -> None:
        self.texts = items


def test_build_markdown_with_formulas_emits_dollar_blocks() -> None:
    """Formula items must surface their ``orig`` field as ``$$…$$`` blocks."""
    from app.services.pdf_extraction.engines.docling import _build_markdown_with_formulas

    doc = _FakeDoc(
        [
            _FakeItem("section_header", text="Introduction"),
            _FakeItem(
                "text",
                text="Einstein's field equation is the cornerstone of GR.",
            ),
            _FakeItem(
                "formula",
                text="",  # Docling leaves text empty for formulas
                orig="G μν = 8 π G T μν",
            ),
            _FakeItem("text", text="It encodes the geometry-matter coupling."),
        ]
    )
    out = _build_markdown_with_formulas(doc)
    assert "## Introduction" in out
    assert "Einstein's field equation" in out
    assert "$$" in out
    assert "G μν = 8 π G T μν" in out
    assert "geometry-matter coupling" in out


def test_build_markdown_with_formulas_skips_page_furniture() -> None:
    """page_header / page_footer / page_number must be stripped at source."""
    from app.services.pdf_extraction.engines.docling import _build_markdown_with_formulas

    doc = _FakeDoc(
        [
            _FakeItem("page_header", text="arXiv:2403.12345v1 [cs.AI]"),
            _FakeItem("section_header", text="Methods"),
            _FakeItem("text", text="We trained a model."),
            _FakeItem("page_footer", text="5"),
            _FakeItem("page_number", text="5"),
        ]
    )
    out = _build_markdown_with_formulas(doc)
    assert "arXiv:" not in out
    assert "5" not in out.split("\n\n")[-1]  # last block is "We trained a model."
    assert "## Methods" in out


def test_build_markdown_with_formulas_falls_back_to_text_when_orig_empty() -> None:
    """When orig is empty (rare), use the text field as the formula body."""
    from app.services.pdf_extraction.engines.docling import _build_markdown_with_formulas

    doc = _FakeDoc([_FakeItem("formula", text="a + b = c", orig="")])
    out = _build_markdown_with_formulas(doc)
    assert "$$" in out
    assert "a + b = c" in out


# ── Page-aware routing (Phase 2) ───────────────────────────────────────────────


class _PageRecordingEngine:
    """Engine that returns a fixed per-page list."""

    def __init__(self, name: str, pages: list[str | None]) -> None:
        self.name = name
        self._pages = pages
        self.calls = 0

    def extract(self, _pdf_path: Path) -> str | None:
        # Not used by the page router, but the protocol still requires it.
        self.calls += 1
        return "\n\n".join(p for p in self._pages if p) or None

    def extract_pages(self, _pdf_path: Path) -> list[str | None] | None:
        self.calls += 1
        return list(self._pages)


def test_page_aware_router_picks_fast_tier_when_all_pages_pass(tmp_path: Path) -> None:
    """When every fast-tier page clears the bar, no fallback runs."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    good_pages = [
        "We present a new result with proper section structure.\n\n" * 3
        for _ in range(3)
    ]
    fast = _PageRecordingEngine("fast", good_pages)
    fb = _PageRecordingEngine("docling", ["never used"] * 3)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._FALLBACK_ENGINES[:] = [fb]
        result = extract_pages_with_routing(pdf, engines=[fast])
    finally:
        _router._FALLBACK_ENGINES[:] = original_fb
    assert result.fast_score >= 0.5
    assert result.weak_pages == []
    assert result.fully_re_extracted is False
    assert all(engine == "fast" for engine in result.page_engines)
    assert fb.calls == 0


def test_page_aware_router_selective_fallback_for_few_weak_pages(tmp_path: Path) -> None:
    """When only a few pages are weak, re-extract just those."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    # 4 good pages + 1 weak page. Weak fraction = 1/5 = 20%, below the
    # 50% full-reextract threshold, so selective fallback should run.
    good_pages = [
        "We present a new result with proper section structure.\n\n" * 3
    ] * 4
    weak = "ab"  # too short, scores ~0.61 vs good pages ~0.70
    fast_pages = good_pages + [weak]
    fb_pages = ["## Replaced\n\nThis page was re-extracted by the fallback engine.\n\n" * 4]
    fast = _PageRecordingEngine("fast", fast_pages)
    fb = _PageRecordingEngine("docling", fb_pages + ["unreached"] * 4)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._FALLBACK_ENGINES[:] = [fb]
        # min_score=0.65 sits between good (0.70) and weak (0.61) pages.
        result = extract_pages_with_routing(pdf, engines=[fast], min_score=0.65)
    finally:
        _router._FALLBACK_ENGINES[:] = original_fb
    assert result.weak_pages == [4]
    assert result.fully_re_extracted is False
    # The fallback replaced only the weak page.
    assert result.page_engines[4] == "docling"
    assert all(result.page_engines[i] == "fast" for i in range(4))


def test_page_aware_router_full_reextract_when_most_pages_weak(tmp_path: Path) -> None:
    """When >=50% of pages are weak, re-extract the whole document."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    fast_pages = ["ab", "cd", "ef", "gh"]   # 4 weak pages
    fb_pages = ["fallback page text with enough content " * 5] * 4
    fast = _PageRecordingEngine("fast", fast_pages)
    fb = _PageRecordingEngine("docling", fb_pages)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._FALLBACK_ENGINES[:] = [fb]
        result = extract_pages_with_routing(pdf, engines=[fast], min_score=0.99)
    finally:
        _router._FALLBACK_ENGINES[:] = original_fb
    assert len(result.weak_pages) == 4
    assert result.fully_re_extracted is True
    assert all(engine == "docling" for engine in result.page_engines)


def test_page_aware_router_can_disable_fallback(tmp_path: Path) -> None:
    """``use_fallback=False`` must keep the fast-tier pages even when weak."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    fast_pages = ["ab", "cd"]
    fast = _PageRecordingEngine("fast", fast_pages)
    fb = _PageRecordingEngine("docling", ["never used"] * 2)
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._FALLBACK_ENGINES[:] = [fb]
        result = extract_pages_with_routing(
            pdf, engines=[fast], min_score=0.99, use_fallback=False
        )
    finally:
        _router._FALLBACK_ENGINES[:] = original_fb
    assert result.weak_pages == [0, 1]
    assert all(engine == "fast" for engine in result.page_engines)
    assert fb.calls == 0


def test_page_aware_router_handles_empty_engine_result(tmp_path: Path) -> None:
    """When every engine returns None, the router returns empty result."""
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    from app.services.pdf_extraction import router as _router

    broken = _PageRecordingEngine("broken", [])
    original_fb = list(_router._FALLBACK_ENGINES)
    try:
        _router._FALLBACK_ENGINES[:] = []
        result = extract_pages_with_routing(pdf, engines=[broken])
    finally:
        _router._FALLBACK_ENGINES[:] = original_fb
    assert result.page_texts == []
    assert result.engine == "broken"