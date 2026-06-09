"""PaperHub source adapter for multi-provider paper discovery."""

from __future__ import annotations

import asyncio
import logging
import os
import re

import aiohttp
from paperhub_cli.models import Paper, SearchFilters
from paperhub_cli.providers.merge import merge_and_dedupe_papers
from paperhub_cli.providers.registry import provider_factory
from paperhub_cli.providers.resolve import resolve_provider_names

from app.core.config import get_settings
from app.sources.base import PaperSource, RawPaper

logger = logging.getLogger(__name__)


class PaperHubSource(PaperSource):
    """Search papers through paperhub-cli's provider registry."""

    name = "paperhub"

    def __init__(self, provider_names: tuple[str, ...] | None = None) -> None:
        settings = get_settings()
        _configure_paperhub_environment(settings)
        self._provider_names = provider_names or _parse_provider_names(
            settings.paperhub_provider_names
        )
        self._provider_timeout_seconds = settings.paperhub_provider_timeout_seconds

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        """Fetch normalized papers from configured PaperHub providers."""
        filters = SearchFilters(
            year_from=year_from,
            year_to=year_to,
            provider_names=self._provider_names,
        )
        papers = await _search_providers_parallel(
            query=query,
            limit=limit,
            filters=filters,
            provider_timeout_seconds=self._provider_timeout_seconds,
        )
        return [_to_raw_paper(paper) for paper in papers]


def _configure_paperhub_environment(settings: object) -> None:
    values = {
        "PAPERHUB_SEMANTIC_SCHOLAR_API_KEY": getattr(settings, "semantic_scholar_api_key", ""),
        "PAPERHUB_CROSSREF_MAILTO": getattr(settings, "paperhub_crossref_mailto", ""),
        "PAPERHUB_OPENALEX_EMAIL": getattr(settings, "paperhub_openalex_email", ""),
        "PAPERHUB_UNPAYWALL_EMAIL": getattr(settings, "paperhub_unpaywall_email", ""),
        "PAPERHUB_CORE_API_KEY": getattr(settings, "paperhub_core_api_key", ""),
        "PAPERHUB_DOAJ_API_KEY": getattr(settings, "paperhub_doaj_api_key", ""),
        "PAPERHUB_ZENODO_ACCESS_TOKEN": getattr(settings, "paperhub_zenodo_access_token", ""),
    }
    for key, value in values.items():
        if value and not os.environ.get(key):
            os.environ[key] = value


def _parse_provider_names(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


async def _search_providers_parallel(
    query: str,
    limit: int,
    filters: SearchFilters,
    provider_timeout_seconds: float,
) -> list[Paper]:
    provider_names = resolve_provider_names(filters)
    async with aiohttp.ClientSession() as session:
        tasks = [
            _search_one_provider(session, provider_name, query, limit, filters)
            for provider_name in provider_names
        ]
        batches = await asyncio.gather(
            *(asyncio.wait_for(task, timeout=provider_timeout_seconds) for task in tasks),
            return_exceptions=True,
        )
    papers = _interleave_provider_batches([batch for batch in batches if isinstance(batch, list)])
    return merge_and_dedupe_papers(papers, limit=limit)


def _interleave_provider_batches(batches: list[list[Paper]]) -> list[Paper]:
    max_len = max((len(batch) for batch in batches), default=0)
    papers: list[Paper] = []
    for index in range(max_len):
        for batch in batches:
            if index < len(batch):
                papers.append(batch[index])
    return papers


async def _search_one_provider(
    session: aiohttp.ClientSession,
    provider_name: str,
    query: str,
    limit: int,
    filters: SearchFilters,
) -> list[Paper]:
    try:
        provider = provider_factory(provider_name, session)
        return await provider.search(query, limit, filters)
    except Exception as exc:
        logger.warning("PaperHub provider %s search failed: %s", provider_name, exc)
        return []


def _to_raw_paper(paper: Paper) -> RawPaper:
    extra = paper.extra or {}
    source_name = str(paper.source.value if hasattr(paper.source, "value") else paper.source)
    paper_id = paper.id or ""
    doi = _clean_doi(str(extra.get("doi") or ""))
    arxiv_id = _extract_prefixed_id(paper_id, "arxiv") or _arxiv_id_from_doi(doi)
    openalex_id = str(extra.get("openalex_id") or "") or _extract_prefixed_id(paper_id, "openalex")

    return RawPaper(
        title=paper.title,
        abstract=paper.abstract or None,
        year=paper.year,
        venue=paper.venue,
        doi=doi,
        arxiv_id=arxiv_id,
        semantic_scholar_id=_extract_prefixed_id(paper_id, "semantic_scholar"),
        openalex_id=openalex_id or None,
        url=paper.url or None,
        authors=[{"name": author, "author_id": ""} for author in paper.authors],
        source_name=source_name,
        source_specific={
            **extra,
            "paperhub_id": paper_id,
            "paperhub_source": source_name,
            "pdf_url": extra.get("pdf_url") or None,
        },
    )


def _extract_prefixed_id(paper_id: str, prefix: str) -> str | None:
    marker = f"{prefix}:"
    if paper_id.startswith(marker):
        return paper_id[len(marker) :]
    return None


def _clean_doi(raw: str) -> str | None:
    doi = raw.strip().removeprefix("https://doi.org/").strip()
    return doi or None


def _arxiv_id_from_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    match = re.match(r"10\.48550/arxiv\.(.+)$", doi, re.IGNORECASE)
    if match is None:
        return None
    return match.group(1)
