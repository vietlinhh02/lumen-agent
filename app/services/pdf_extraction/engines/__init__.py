"""Engines package — holds optional, heavier PDF extraction backends.

Each engine is in its own submodule so its heavy dependencies (torch,
HuggingFace models, etc.) are imported lazily inside the ``extract``
method. The main router runs only the lightweight engines
(:class:`PdfOxideEngine`, :class:`PyPdfEngine`) on the hot path; this
package hosts the layout-aware / OCR fallback engines that activate
only when the fast path scores below threshold.
"""

from __future__ import annotations

from app.services.pdf_extraction.engines.docling import DoclingEngine

__all__ = ["DoclingEngine"]