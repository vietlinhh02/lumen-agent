"""PDF extraction package: layout-aware, self-healing extraction.

This package replaces the monolithic ``pdf_fulltext`` regex pipeline with a
modular system where each backend (pdf_oxide, pypdf, future Docling/MinerU
adapters) is scored independently and the best result wins. The motivation
is documented in ``docs/architecture/pdf-extraction-roadmap.md``.

Public surface (kept small on purpose):

- :func:`extract_with_routing` — entry point used by ``pdf_fulltext``.
- :class:`ExtractionQuality` and :func:`score_quality` — page-level audit.
- :class:`ExtractionEngine` protocol — interface every backend implements.
"""

from __future__ import annotations

from app.services.pdf_extraction.quality import (
    ExtractionQuality,
    PageMetrics,
    score_quality,
)
from app.services.pdf_extraction.router import (
    ExtractionResult,
    PageAwareExtractionResult,
    extract_pages_with_routing,
    extract_with_routing,
    list_fallback_engines,
    list_registered_engines,
    register_fallback_engine,
    register_layout_engines_as_primary,
    register_optional_fallback_engines,
)

__all__ = [
    "ExtractionQuality",
    "ExtractionResult",
    "PageAwareExtractionResult",
    "PageMetrics",
    "extract_pages_with_routing",
    "extract_with_routing",
    "list_fallback_engines",
    "list_registered_engines",
    "register_fallback_engine",
    "register_layout_engines_as_primary",
    "register_optional_fallback_engines",
    "score_quality",
]