"""External paper source adapters.

Only Semantic Scholar is used for search — it provides:
- Full metadata (title, abstract, authors, year, citations)
- arXiv IDs via ``externalIds.ArXiv`` (→ PDF from arXiv CDN)
- OA PDF URLs via ``openAccessPdf.url``
"""

from app.sources.base import PaperSource, RawPaper
from app.sources.semantic_scholar import SemanticScholarSource

__all__ = ["PaperSource", "RawPaper", "SemanticScholarSource"]
