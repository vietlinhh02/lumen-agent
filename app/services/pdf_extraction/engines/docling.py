"""Docling layout-aware PDF extraction engine.

Docling (IBM, MIT) is the layout-aware backend added in Phase 1 of
``docs/architecture/pdf-extraction-roadmap.md``. It runs an ML layout
model (DiT / LayoutLMv3) on each page image, classifies regions as
{title, paragraph, list, figure, table, formula, caption, header,
footer, reference}, then reconstructs reading order via XY-Cut++.

Why it sits behind the fast engines:

- First-time model load is 1-2 minutes and pulls ~500MB from
  HuggingFace Hub. Acceptable for batch / fallback, not for the
  request hot path.
- Per-paper runtime is 5-20x slower than pdf_oxide / pypdf.
- The hot-path pdf_oxide + pypdf pair already clears the GOOD_SCORE
  bar for ~87% of papers. We only want Docling for the in-between
  zone.

Why a separate module:

The docling stack is an *optional* dependency (``uv sync --extra
docling``). We keep its imports lazy inside :meth:`extract` so the
app boots and runs the fast path even on installations without the
``docling`` extra. Engines that aren't installed degrade to no-ops.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Docling's first convert() call downloads models and warms CUDA/CPU
# kernels — easily 60-120 seconds. We cache the converter process-wide
# so subsequent calls only pay the model inference cost, not the load.
_CONVERTER_LOCK = threading.Lock()
_CONVERTER: Any | None = None


def _get_converter() -> Any:
    """Return a process-wide :class:`DocumentConverter`, creating lazily.

    The converter holds several GB of model weights in memory; creating
    it on every call would force a full reload per paper. The lock makes
    the lazy creation safe across concurrent FastAPI worker threads.
    """
    global _CONVERTER
    if _CONVERTER is not None:
        return _CONVERTER
    with _CONVERTER_LOCK:
        if _CONVERTER is not None:
            return _CONVERTER
        from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]

        logger.info("Initialising Docling DocumentConverter (one-time model load)")
        _CONVERTER = DocumentConverter()
        return _CONVERTER


class DoclingEngine:
    """Layout-aware PDF extraction via Docling.

    Implements the :class:`~app.services.pdf_extraction.router.ExtractionEngine`
    protocol. Designed to be registered as a *fallback* engine — invoked
    only when the fast pdf_oxide / pypdf pair scores below the routing
    threshold. See :func:`register_fallback_engine` for the wiring.
    """

    name = "docling"

    def __init__(self, *, timeout_seconds: int = 600) -> None:
        # Docling per-paper latency can hit 1-2 minutes on large PDFs.
        # We don't actually enforce a timeout here — that's the router's
        # job via :class:`concurrent.futures` cancellation — but expose
        # the field so callers can configure their own ceiling.
        self._timeout_seconds = timeout_seconds

    def extract(self, pdf_path: Path) -> str | None:
        """Run Docling on *pdf_path* and return the markdown export.

        We build a custom markdown export rather than calling
        :meth:`Document.export_to_markdown` because the built-in export
        drops the formula ``orig`` field — which holds the OCR'd LaTeX
        representation of each equation. Walking :attr:`document.texts`
        in document order lets us emit ``$$…$$`` blocks for formulas
        while still streaming prose text. Returns ``None`` on any
        failure (missing dep, model error, OOM, timeout). Never raises,
        so the router can move on gracefully.
        """
        try:
            converter = _get_converter()
        except ImportError:
            logger.warning(
                "DoclingEngine.extract: docling is not installed. "
                "Install with `uv sync --extra docling` to enable this engine."
            )
            return None
        except Exception as exc:
            logger.warning("Docling converter init failed: %s", exc)
            return None

        try:
            result = converter.convert(str(pdf_path))
        except Exception as exc:
            logger.warning("Docling convert failed for %s: %s", pdf_path.name, exc)
            return None

        try:
            document = getattr(result, "document", None)
            if document is None:
                logger.warning("Docling returned no document for %s", pdf_path.name)
                return None
            markdown = _build_markdown_with_formulas(document)
        except Exception as exc:
            logger.warning("Docling markdown export failed for %s: %s", pdf_path.name, exc)
            return None

        if not markdown:
            return None
        text = markdown.replace("\x00", "").strip()
        return text or None

    def extract_pages(self, pdf_path: Path) -> list[str | None] | None:
        """Per-page extraction via Docling's structured output.

        Walks ``document.texts`` and groups by ``prov[0].page_no`` so
        the page-aware router can re-extract just the low-scoring pages
        with another backend. Returns one entry per page (1-indexed) in
        document order; ``None`` for pages with no content (blank
        end-papers), empty string for pages with only skipped content.
        """
        try:
            converter = _get_converter()
        except ImportError:
            return None
        except Exception as exc:
            logger.warning("Docling converter init failed: %s", exc)
            return None

        try:
            result = converter.convert(str(pdf_path))
        except Exception as exc:
            logger.warning("Docling convert failed for %s: %s", pdf_path.name, exc)
            return None

        try:
            document = getattr(result, "document", None)
            if document is None:
                return None
            pages = _build_pages_with_formulas(document)
        except Exception as exc:
            logger.warning("Docling per-page export failed for %s: %s", pdf_path.name, exc)
            return None
        # Normalise: None for empty pages.
        return [p if p else None for p in pages]


# Docling text-item labels we map to specific markdown output.
# Anything not in this set is emitted as plain prose.
_LABEL_SECTION_HEADER = "section_header"
_LABEL_FORMULA = "formula"
_LABEL_TEXT = "text"
# Page header / footer are stripped here so downstream chunking
# doesn't see them as body content (the pdf_fulltext normaliser also
# strips them, but doing it at the source keeps output lean).
_LABELS_TO_SKIP = frozenset({"page_header", "page_footer", "page_number"})


def _build_markdown_with_formulas(document: Any) -> str:
    """Convert Docling's structured output into LaTeX-aware markdown.

    Walks :attr:`document.texts` in order, emits section headers as
    ``##`` lines, formula items as ``$$…$$`` blocks using their
    ``orig`` (LaTeX-like) text, and skips page furniture. Returns the
    concatenated markdown string.
    """
    parts: list[str] = []
    for item in getattr(document, "texts", []) or []:
        label = str(getattr(item, "label", "") or "")
        text = (getattr(item, "text", "") or "").strip()
        if label in _LABELS_TO_SKIP:
            continue
        if label == _LABEL_FORMULA:
            orig = (getattr(item, "orig", "") or "").strip()
            # Prefer orig (LaTeX-like) over text; fall back to text if
            # orig is empty.
            body = orig or text
            if body:
                parts.append(f"$$\n{body}\n$$")
            continue
        if label == _LABEL_SECTION_HEADER:
            if text:
                parts.append(f"## {text}")
            continue
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _build_pages_with_formulas(document: Any) -> list[str]:
    """Same as :func:`_build_markdown_with_formulas` but splits per page.

    Walks :attr:`document.texts` and groups by ``prov[0].page_no`` so
    the page-aware router can re-extract just the low-scoring pages
    with a fallback engine. Pages with no content (e.g. blank
    end-papers) emit an empty string rather than being omitted, so the
    returned list has one entry per page in document order.
    """
    page_buckets: dict[int, list[str]] = {}
    max_page = 0
    for item in getattr(document, "texts", []) or []:
        label = str(getattr(item, "label", "") or "")
        text = (getattr(item, "text", "") or "").strip()
        prov = getattr(item, "prov", None) or []
        page_no = prov[0].page_no if prov else None
        if page_no is None:
            continue
        max_page = max(max_page, page_no)
        if label in _LABELS_TO_SKIP:
            continue
        if label == _LABEL_FORMULA:
            orig = (getattr(item, "orig", "") or "").strip()
            body = orig or text
            if body:
                page_buckets.setdefault(page_no, []).append(f"$$\n{body}\n$$")
            continue
        if label == _LABEL_SECTION_HEADER:
            if text:
                page_buckets.setdefault(page_no, []).append(f"## {text}")
            continue
        if text:
            page_buckets.setdefault(page_no, []).append(text)
    # Emit one entry per page (1-indexed), empty string for blanks.
    return [
        "\n\n".join(page_buckets.get(page_no, []))
        for page_no in range(1, max_page + 1)
    ]


__all__ = ["DoclingEngine"]