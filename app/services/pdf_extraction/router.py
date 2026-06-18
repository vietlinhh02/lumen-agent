"""Self-healing PDF extraction router.

Routes a PDF through an ordered list of extraction engines, scores each
result with :func:`app.services.pdf_extraction.quality.score_quality`,
and returns the highest-quality extraction that clears the minimum
score bar. This is the "Self-Healing Routing" stage of the pipeline
described in ``docs/architecture/pdf-extraction-roadmap.md``.

Engines are pluggable via the :class:`ExtractionEngine` protocol so the
layout-aware backends (Docling, MinerU, Nougat) can be added later
without touching the call sites in ``pdf_fulltext``. The current
production engines are:

- :class:`PdfOxideEngine` — fast markdown with academic profile
- :class:`PyPdfEngine`   — plain text, strong on some two-column papers

Why two engines and not one: pdf_oxide occasionally interleaves columns
on certain IEEE/Springer layouts; pypdf reads the underlying text
stream and produces a cleaner column-separated result on those papers.
The router picks the winner per-document via the 5-signal scorer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.services.pdf_extraction.quality import (
    DEFAULT_MIN_SCORE,
    ExtractionQuality,
    score_quality,
)

logger = logging.getLogger(__name__)


# ── Engine protocol ─────────────────────────────────────────────────────


class ExtractionEngine(Protocol):
    """Interface every PDF extraction backend must implement.

    Implementations must be *safe to call multiple times*: the router
    may invoke several engines in sequence when the first fails the
    quality bar. They must never raise on a malformed PDF — return
    ``None`` instead so the router can move to the next engine.

    Engines SHOULD override :meth:`extract_pages` when they can extract
    text per page natively (pypdf, Docling). The default implementation
    calls :meth:`extract` and splits on the form-feed character ``\\f``
    — good enough for text-layer engines, but engines with their own
    page-level API should override to preserve accurate page boundaries.
    """

    name: str

    def extract(self, pdf_path: Path) -> str | None:
        """Return extracted text or ``None`` on any failure."""
        ...

    def extract_pages(self, pdf_path: Path) -> list[str | None] | None:
        """Return a list of per-page text strings, or ``None`` on failure.

        ``None`` entries in the returned list mean that page failed to
        extract cleanly (e.g. encrypted page, image-only page) — the
        router will treat that page as empty and may re-extract it via
        the fallback tier.
        """
        ...


@dataclass(frozen=True)
class ExtractionResult:
    """The router's return value: chosen text plus audit metadata."""

    text: str | None
    engine: str
    quality: ExtractionQuality
    tried: list[tuple[str, ExtractionQuality]] = field(default_factory=list)
    fell_back: bool = False

    @property
    def succeeded(self) -> bool:
        return self.text is not None and self.quality.score > 0


# ── Built-in engines ────────────────────────────────────────────────────


class PdfOxideEngine:
    """pdf_oxide with the academic profile (markdown + heading detection)."""

    name = "pdf_oxide"

    def extract(self, pdf_path: Path) -> str | None:
        try:
            from pdf_oxide import PdfDocument
        except ImportError:
            logger.warning("pdf_oxide not installed; cannot run pdf_oxide engine")
            return None
        try:
            doc = PdfDocument(pdf_path)
        except Exception as exc:
            logger.warning("pdf_oxide failed to open %s: %s", pdf_path.name, exc)
            return None
        try:
            text = doc.to_markdown_all(
                preserve_layout=True,
                detect_headings=True,
                include_images=False,
            )
        except Exception as exc:
            logger.warning("pdf_oxide markdown failed for %s: %s", pdf_path.name, exc)
            return None
        finally:
            del doc
        text = text.replace("\x00", "").strip() if text else ""
        return text or None

    def extract_pages(self, pdf_path: Path) -> list[str | None] | None:
        """Per-page extraction using pdf_oxide's page-by-page API."""
        try:
            from pdf_oxide import PdfDocument
        except ImportError:
            return None
        try:
            doc = PdfDocument(pdf_path)
            page_count = doc.page_count()
            pages: list[str | None] = []
            for page_index in range(page_count):
                try:
                    page_text = doc.extract_text(page_index) or ""
                    page_text = page_text.replace("\x00", "").strip()
                    pages.append(page_text or None)
                except Exception as exc:
                    logger.warning(
                        "pdf_oxide page %d failed for %s: %s",
                        page_index,
                        pdf_path.name,
                        exc,
                    )
                    pages.append(None)
        except Exception as exc:
            logger.warning("pdf_oxide open failed for %s: %s", pdf_path.name, exc)
            return None
        finally:
            del doc
        return pages


class PyPdfEngine:
    """pypdf plain-text fallback. Strong on some two-column journal papers."""

    name = "pypdf"

    def extract(self, pdf_path: Path) -> str | None:
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.warning("pypdf not installed; cannot run pypdf engine")
            return None
        try:
            reader = PdfReader(pdf_path)
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            logger.warning("pypdf failed for %s: %s", pdf_path.name, exc)
            return None
        text = "\n".join(page for page in pages if page.strip())
        text = text.replace("\x00", "").strip()
        return text or None

    def extract_pages(self, pdf_path: Path) -> list[str | None] | None:
        """Per-page extraction via pypdf's native page-by-page API."""
        try:
            from pypdf import PdfReader
        except ImportError:
            return None
        try:
            reader = PdfReader(pdf_path)
            pages: list[str | None] = []
            for page in reader.pages:
                try:
                    text = page.extract_text() or ""
                    text = text.replace("\x00", "").strip()
                    pages.append(text or None)
                except Exception as exc:
                    logger.warning(
                        "pypdf single-page extract failed: %s", exc
                    )
                    pages.append(None)
        except Exception as exc:
            logger.warning("pypdf open failed for %s: %s", pdf_path.name, exc)
            return None
        return pages


# ── Engine registry ────────────────────────────────────────────────────


_DEFAULT_ENGINES: list[ExtractionEngine] = [
    PdfOxideEngine(),
    PyPdfEngine(),
]

# Fallback engines run only when the fast tier scores below min_score.
# Docling is heavy (1-2min first call for model load, ~5-20x slower per
# paper), so it never runs on the happy path. Engines register here via
# :func:`register_fallback_engine`.
_FALLBACK_ENGINES: list[ExtractionEngine] = []


def list_registered_engines() -> list[str]:
    """Return the names of the engines used by default routing."""
    return [engine.name for engine in _DEFAULT_ENGINES]


def list_fallback_engines() -> list[str]:
    """Return the names of fallback engines (run only after fast tier falls back)."""
    return [engine.name for engine in _FALLBACK_ENGINES]


def register_engine(engine: ExtractionEngine, *, at_front: bool = False) -> None:
    """Append (or prepend) an engine to the default routing list.

    Provided so future Docling / MinerU / Nougat adapters can plug in
    without modifying this module. Not thread-safe; call once at startup.
    """
    if at_front:
        _DEFAULT_ENGINES.insert(0, engine)
    else:
        _DEFAULT_ENGINES.append(engine)


def register_fallback_engine(engine: ExtractionEngine, *, at_front: bool = False) -> None:
    """Add an engine to the fallback tier.

    Fallback engines (e.g. Docling, Mistral OCR) are heavy and only
    invoked when the fast tier fails to clear ``min_score``. Use this
    instead of :func:`register_engine` when the backend has multi-second
    or longer latency per paper.
    """
    if at_front:
        _FALLBACK_ENGINES.insert(0, engine)
    else:
        _FALLBACK_ENGINES.append(engine)


def register_optional_fallback_engines() -> list[str]:
    """Register all layout-aware / OCR fallback engines whose dependencies are installed.

    Returns the list of engine names actually registered, so callers
    can log which engines are active. This is the function to call from
    ``app.main`` at startup — it costs nothing when the optional
    dependencies aren't installed.

    Currently registered when available:

    - :class:`~app.services.pdf_extraction.engines.DoclingEngine` —
      layout-aware ML extraction. Install with
      ``uv sync --extra docling``.
    """
    registered: list[str] = []
    try:
        from app.services.pdf_extraction.engines.docling import DoclingEngine

        register_fallback_engine(DoclingEngine())
        registered.append(DoclingEngine.name)
    except ImportError:
        logger.debug("Docling not installed; skipping fallback registration")
    return registered


def register_layout_engines_as_primary() -> list[str]:
    """Register Docling in the fast tier (production-grade mode).

    Use this when Docling is fast enough on your hardware to be the
    default extraction backend. Trade-off vs the fallback mode:

    + Higher extraction quality (Docling scores 0.97 vs pypdf 0.90 on
      typical scientific PDFs from the 244-paper benchmark).
    + Layout-aware: handles two-column papers, figures, formulas,
      tables without regex cleanup.
    + LaTeX formulas preserved as ``$$…$$`` blocks (read :func:`extract`).
    − ~10-20x slower per paper than pdf_oxide / pypdf (5-15s vs 0.5s).
    − First call in a worker pays a 1-2 minute model warmup cost.
    − Each worker holds ~1-2GB of model weights in RAM.

    Falls back to pdf_oxide / pypdf automatically when Docling scores
    below the routing threshold, so image-only PDFs (which Docling
    may struggle with) still get the best of the remaining engines.

    Returns the list of engine names registered, so callers can log
    the active set. No-op when the docling extra is not installed.
    """
    registered: list[str] = []
    try:
        from app.services.pdf_extraction.engines.docling import DoclingEngine

        register_engine(DoclingEngine(), at_front=True)
        registered.append(DoclingEngine.name)
    except ImportError:
        logger.debug("Docling not installed; skipping primary registration")
    return registered


def _run_engines(
    engines: list[ExtractionEngine],
    pdf_path: Path,
) -> tuple[str | None, str, ExtractionQuality, list[tuple[str, ExtractionQuality]]]:
    """Run a list of engines against *pdf_path* and return the best result.

    Helper extracted from :func:`extract_with_routing` so the same logic
    applies to the fast tier and the fallback tier without duplication.
    """
    tried: list[tuple[str, ExtractionQuality]] = []
    best_text: str | None = None
    best_engine = ""
    best_quality = score_quality(None)
    for engine in engines:
        try:
            text = engine.extract(pdf_path)
        except Exception as exc:
            logger.warning("Engine %s raised on %s: %s", engine.name, pdf_path.name, exc)
            continue
        quality = score_quality(text)
        tried.append((engine.name, quality))
        if quality.score > best_quality.score:
            best_quality = quality
            best_text = text
            best_engine = engine.name
    return best_text, best_engine, best_quality, tried


# ── Routing ─────────────────────────────────────────────────────────────


def extract_with_routing(
    pdf_path: Path,
    *,
    engines: list[ExtractionEngine] | None = None,
    min_score: float = DEFAULT_MIN_SCORE,
    use_fallback: bool = True,
) -> ExtractionResult:
    """Run each engine in order and return the highest-quality result.

    The router runs the fast tier (pdf_oxide, pypdf by default) first,
    scores every successful extraction, and returns the highest-scoring
    result that clears ``min_score``. When the fast tier falls below
    ``min_score`` and ``use_fallback`` is True, the fallback tier
    (Docling by default after :func:`register_fallback_engine`) runs.

    The returned ``ExtractionResult`` always carries the highest score
    found across all tiers; ``fell_back`` is True when even the fallback
    tier did not clear ``min_score``. Callers can read
    :attr:`ExtractionResult.tried` to see the per-engine audit trail.

    Parameters
    ----------
    pdf_path:
        The PDF file to extract.
    engines:
        Optional explicit engine list for the fast tier. Defaults to
        the registered engines in order: pdf_oxide, pypdf. Pass a
        custom list for tests or to force a single-backend evaluation.
    min_score:
        Minimum composite score to accept without falling back.
    use_fallback:
        When True (default), run the fallback tier if the fast tier
        falls below ``min_score``. Set False to skip fallback entirely
        — useful for the request hot path, or when benchmarking the
        fast tier in isolation.
    """
    fast_tier = engines if engines is not None else list(_DEFAULT_ENGINES)
    best_text, best_engine, best_quality, tried = _run_engines(fast_tier, pdf_path)

    fell_back = best_quality.score < min_score
    if fell_back and use_fallback and _FALLBACK_ENGINES:
        logger.info(
            "Fast tier fell back on %s (best=%s score=%.3f, min=%.2f); "
            "running fallback tier: %s",
            pdf_path.name,
            best_engine or "<none>",
            best_quality.score,
            min_score,
            ", ".join(e.name for e in _FALLBACK_ENGINES),
        )
        fb_text, fb_engine, fb_quality, fb_tried = _run_engines(_FALLBACK_ENGINES, pdf_path)
        tried.extend(fb_tried)
        if fb_quality.score > best_quality.score:
            best_text = fb_text
            best_engine = fb_engine
            best_quality = fb_quality
        # Only clear fell_back if the fallback actually passed the bar.
        fell_back = best_quality.score < min_score

    if fell_back:
        logger.info(
            "Self-healing routing: best engine for %s was %s with score=%.3f "
            "(min=%.2f); all engines failed",
            pdf_path.name,
            best_engine or "<none>",
            best_quality.score,
            min_score,
        )
    elif best_engine:
        logger.debug(
            "Routing %s -> %s (score=%.3f, weakest_signal=%s)",
            pdf_path.name,
            best_engine,
            best_quality.score,
            best_quality.weakest_signal,
        )

    return ExtractionResult(
        text=best_text,
        engine=best_engine,
        quality=best_quality,
        tried=tried,
        fell_back=fell_back,
    )


# ── Page-aware routing (Phase 2) ────────────────────────────────────────────────────────────


# Default page-quality threshold below which a page is considered "weak"
# and escalated to the fallback tier. The value matches the document-level
# DEFAULT_MIN_SCORE so the per-page decision is consistent with the
# whole-document decision.
_PAGE_MIN_SCORE = 0.45
# Below this fraction of bad pages in the fast-tier output, we re-extract
# only the bad pages (cheap). Above this fraction, the document is mostly
# broken and re-extracting the whole thing via the fallback tier is cheaper.
_BAD_PAGE_FRACTION_FOR_FULL_REEXTRACT = 0.5


@dataclass(frozen=True)
class PageAwareExtractionResult:
    """Page-by-page extraction with selective fallback.

    Returned by :func:`extract_pages_with_routing`. Splits the document
    into per-page text, scores each page with the fast tier, then either
    keeps all fast-tier pages (when most are clean) or escalates the
    weak pages to the fallback tier individually.
    """

    page_texts: list[str | None]
    page_engines: list[str]                  # engine per page (post-merge)
    page_scores: list[float]                 # score per page (post-merge)
    engine: str                              # primary engine name
    quality: ExtractionQuality               # composite over the merged text
    fast_score: float                        # composite before any fallback
    weak_pages: list[int]                    # page indices that needed fallback
    fully_re_extracted: bool                 # True when fallback ran on whole doc


def extract_pages_with_routing(
    pdf_path: Path,
    *,
    engines: list[ExtractionEngine] | None = None,
    min_score: float = _PAGE_MIN_SCORE,
    use_fallback: bool = True,
) -> PageAwareExtractionResult:
    """Per-page extraction with selective fallback.

    Runs the fast tier per page (pypdf or pdf_oxide, whichever scores
    higher). Scores each page individually. When most pages are clean,
    keeps the fast-tier output as-is. When many pages are weak, escalates
    the entire document to the fallback tier (cheaper than running
    Docling page-by-page because of the model warmup cost).

    When the fallback tier is used selectively (only on weak pages),
    the per-page text is replaced with the fallback output and the
    composite quality is recomputed over the merged document.
    """
    fast_tier = engines if engines is not None else list(_DEFAULT_ENGINES)
    pages_per_engine: dict[str, list[str | None]] = {}

    for engine in fast_tier:
        try:
            pages = engine.extract_pages(pdf_path)
        except Exception as exc:
            logger.warning(
                "Engine %s.extract_pages raised on %s: %s",
                engine.name,
                pdf_path.name,
                exc,
            )
            continue
        if pages is not None:
            pages_per_engine[engine.name] = pages

    if not pages_per_engine:
        return PageAwareExtractionResult(
            page_texts=[],
            page_engines=[],
            page_scores=[],
            engine="",
            quality=score_quality(None),
            fast_score=0.0,
            weak_pages=[],
            fully_re_extracted=False,
        )

    # Pick the engine with the highest per-page coverage. If both engines
    # return all-None pages, fall back to whichever has fewer Nones.
    best_engine_name = max(
        pages_per_engine,
        key=lambda name: sum(1 for p in pages_per_engine[name] if p),
    )
    fast_pages = pages_per_engine[best_engine_name]
    page_count = len(fast_pages)

    # Score each page from the fast tier.
    fast_page_scores = [
        score_quality(page).score if page else 0.0 for page in fast_pages
    ]
    weak_indices = [
        i for i, s in enumerate(fast_page_scores) if s < min_score
    ]
    fast_text = "\n\n".join(p for p in fast_pages if p)
    fast_quality = score_quality(fast_text)
    fast_score = fast_quality.score

    weak_fraction = len(weak_indices) / max(page_count, 1)
    too_many_weak = weak_fraction >= _BAD_PAGE_FRACTION_FOR_FULL_REEXTRACT

    # Decide: full re-extract or per-page re-extract.
    page_texts: list[str | None] = list(fast_pages)
    page_engines: list[str] = [best_engine_name] * page_count
    fully_re_extracted = False

    if use_fallback and _FALLBACK_ENGINES and weak_indices:
        if too_many_weak:
            # Re-extract the entire document via the fallback tier.
            fb_engine = _FALLBACK_ENGINES[0]
            try:
                fb_pages = fb_engine.extract_pages(pdf_path)
            except Exception as exc:
                logger.warning(
                    "Fallback %s.extract_pages raised on %s: %s",
                    fb_engine.name,
                    pdf_path.name,
                    exc,
                )
                fb_pages = None
            if fb_pages is not None:
                page_texts = fb_pages
                page_engines = [fb_engine.name] * len(fb_pages)
                fully_re_extracted = True
        else:
            # Selective: re-extract only the weak pages.
            fb_engine = _FALLBACK_ENGINES[0]
            try:
                fb_pages_all = fb_engine.extract_pages(pdf_path)
            except Exception as exc:
                logger.warning(
                    "Fallback %s.extract_pages raised on %s: %s",
                    fb_engine.name,
                    pdf_path.name,
                    exc,
                )
                fb_pages_all = None
            if fb_pages_all is not None:
                for i in weak_indices:
                    if i < len(fb_pages_all) and fb_pages_all[i]:
                        page_texts[i] = fb_pages_all[i]
                        page_engines[i] = fb_engine.name

    merged_text = "\n\n".join(p for p in page_texts if p)
    merged_quality = score_quality(merged_text)
    merged_page_scores = [
        score_quality(p).score if p else 0.0 for p in page_texts
    ]

    return PageAwareExtractionResult(
        page_texts=page_texts,
        page_engines=page_engines,
        page_scores=merged_page_scores,
        engine=best_engine_name,
        quality=merged_quality,
        fast_score=fast_score,
        weak_pages=weak_indices,
        fully_re_extracted=fully_re_extracted,
    )


__all__ = [
    "ExtractionEngine",
    "ExtractionResult",
    "PageAwareExtractionResult",
    "PdfOxideEngine",
    "PyPdfEngine",
    "extract_pages_with_routing",
    "extract_with_routing",
    "list_fallback_engines",
    "list_registered_engines",
    "register_engine",
    "register_fallback_engine",
    "register_layout_engines_as_primary",
    "register_optional_fallback_engines",
]