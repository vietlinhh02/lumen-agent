"""Canonical types shared by all source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawPaper:
    """Normalised paper record returned by any source adapter.

    The service layer uses these values to populate the canonical ``papers``
    table.  Fields that are missing from a particular source are set to their
    natural empty / None defaults.
    """

    title: str
    abstract: str | None = None
    language: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    semantic_scholar_id: str | None = None
    openalex_id: str | None = None
    url: str | None = None
    citation_count: int | None = None
    authors: list[dict[str, str]] = field(default_factory=list)
    source_name: str = ""
    source_specific: dict = field(default_factory=dict)


class PaperSource:
    """Interface every academic source adapter must implement."""

    name: str  # e.g. "semantic_scholar", "openalex", "arxiv"

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        """Return canonical papers matching *query*."""
        raise NotImplementedError
