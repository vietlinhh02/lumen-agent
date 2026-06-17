"""Paper search + download orchestrator.

Glue layer that ties Semantic Scholar search to PDF download.  Exposed
as an async service function — easy to call from a router, an agent node,
or a script.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple

from app.core.config import get_settings
from app.schemas.paper import (
    LanguageBiasAudit as LanguageBiasAuditSchema,
)
from app.schemas.paper import (
    PaperAuthor,
    PaperPDFStatus,
    PaperResult,
    PaperSearchRequest,
    PaperSearchResponse,
)
from app.schemas.paper import (
    QueryVariant as QueryVariantSchema,
)
from app.services.language_bias import (
    QueryVariant,
    compute_bias_audit,
    detect_and_generate_variants,
)
from app.services.pdf_downloader import PDFDownloader
from app.sources.base import RawPaper
from app.sources.exa import ExaSource
from app.sources.paperhub import PaperHubSource

logger = logging.getLogger(__name__)

# ── Search result cache ───────────────────────────────────────────────────
# Simple in-memory LRU cache for search results
# Key: hash of (query, limit, year_from, year_to)
# Value: (raw_papers, source_diagnostics, detected_lang, variants)
_SEARCH_CACHE: OrderedDict[str, tuple] = OrderedDict()
_CACHE_MAX_SIZE = 100
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_key(query: str, limit: int, year_from: int | None, year_to: int | None) -> str:
    """Generate a cache key for search parameters."""
    raw = f"{query}:{limit}:{year_from}:{year_to}"
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached_search(
    cache_key: str,
) -> tuple[list[RawPaper], list[dict], str, list[QueryVariant]] | None:
    """Return cached search results if available and not expired."""
    if cache_key not in _SEARCH_CACHE:
        return None
    raw_papers, source_diagnostics, detected_lang, variants, cached_at = _SEARCH_CACHE[cache_key]
    import time as _time

    if _time.time() - cached_at > _CACHE_TTL_SECONDS:
        del _SEARCH_CACHE[cache_key]
        return None
    # Move to end (most recently used)
    _SEARCH_CACHE.move_to_end(cache_key)
    return raw_papers, source_diagnostics, detected_lang, variants


def _cache_search_result(
    cache_key: str,
    raw_papers: list[RawPaper],
    source_diagnostics: list[dict],
    detected_lang: str,
    variants: list[QueryVariant],
) -> None:
    """Cache search results with LRU eviction."""
    import time as _time

    _SEARCH_CACHE[cache_key] = (
        raw_papers,
        source_diagnostics,
        detected_lang,
        variants,
        _time.time(),
    )
    while len(_SEARCH_CACHE) > _CACHE_MAX_SIZE:
        _SEARCH_CACHE.popitem(last=False)


class SearchOutcome(NamedTuple):
    """Container returned by :func:`search_and_download`.

    Holds both the high-level response for the API and a flat list of
    :class:`RawPaper` — useful when the caller is an agent that needs
    the canonical dataclass (e.g. to insert into the DB).
    """

    response: PaperSearchResponse
    raw_papers: list[RawPaper]
    pdf_statuses: list[PaperPDFStatus]


# ── primary service function ─────────────────────────────────────────────


async def search_and_download(request: PaperSearchRequest) -> SearchOutcome:
    """Search Semantic Scholar, optionally download PDFs, return structured results.

    Args:
        request: Validated search parameters.

    Returns:
        ``SearchOutcome`` with the API response, raw papers, and per-paper
        PDF statuses.
    """
    settings = get_settings()
    pdf_dir = Path(settings.paper_pdf_dir)

    # ── 0. Check cache first ─────────────────────────────────────────────
    cache_key = _cache_key(request.query, request.limit, request.year_from, request.year_to)
    cached = _get_cached_search(cache_key)
    search_ms: float = 0.0

    if cached:
        all_raw, source_diagnostics, detected_lang, variants = cached
        logger.debug("Search cache hit for query: %s", request.query[:50])
    else:
        # ── 1. Language bias: detect + generate variants ─────────────────────
        detected_lang = "en"
        variants: list[QueryVariant] = []
        source_diagnostics: list[dict] = []

        try:
            variants, detected_lang = await detect_and_generate_variants(
                request.query,
                request.target_languages or [detected_lang, "en"],
            )
        except Exception as exc:
            logger.warning("Language bias detection failed: %s", exc)
            # Fallback: use default English variants for common sources
            variants = [
                QueryVariant(source="semantic_scholar", query=request.query, language="en"),
                QueryVariant(source="arxiv", query=request.query, language="en"),
            ]

        # ── 2. Build source query map ───────────────────────────────────
        t0 = time.monotonic()
        _CANONICAL_SOURCES = {"semantic_scholar", "arxiv", "exa", "firecrawl", "openalex"}
        source_query_map: dict[str, str] = {}
        for v in variants:
            canonical = _normalize_source_name(v.source, _CANONICAL_SOURCES)
            if canonical and canonical not in source_query_map:
                source_query_map[canonical] = v.query

        if not source_query_map:
            source_query_map["semantic_scholar"] = request.query

        # ── 3. Search all sources in parallel with early exit ────────────
        all_raw, source_diagnostics = await _search_sources_parallel(
            source_query_map,
            request.limit,
            request.year_from,
            request.year_to,
        )

        search_ms = round((time.monotonic() - t0) * 1000, 1)
        logger.debug("Search took %dms for query: %s", search_ms, request.query[:50])

        # Cache the results
        _cache_search_result(cache_key, all_raw, source_diagnostics, detected_lang, variants)

    raw_papers = _deduplicate_raw_books(all_raw)
    raw_papers = raw_papers[: request.limit]

    # ── 4. Build paper results ───────────────────────────────────────────
    results: list[PaperResult] = []
    pdf_statuses: list[PaperPDFStatus] = []

    pdfs_downloaded = 0
    pdfs_failed = 0
    download_ms: float | None = None

    # ── 5. Download PDFs (optional) ──────────────────────────────────────
    if request.download_pdfs and raw_papers:
        t_dl = time.monotonic()
        downloader = PDFDownloader(output_dir=pdf_dir, timeout=90)
        pdf_map = await downloader.download_many(raw_papers)
        download_ms = round((time.monotonic() - t_dl) * 1000, 1)
    else:
        pdf_map: dict[str, Path | None] = {}

    # ── 6. Assemble output ───────────────────────────────────────────────
    for paper in raw_papers:
        pdf_path = pdf_map.get(paper.title)
        pdf_source = _classify_pdf_source(paper)

        result = PaperResult(
            title=paper.title,
            abstract=paper.abstract,
            year=paper.year,
            venue=paper.venue,
            doi=paper.doi,
            arxiv_id=paper.arxiv_id,
            semantic_scholar_id=paper.semantic_scholar_id,
            url=paper.url,
            citation_count=paper.citation_count,
            authors=[
                PaperAuthor(name=a["name"], author_id=a.get("author_id")) for a in paper.authors
            ],
            fields_of_study=paper.source_specific.get("fields_of_study") or [],
            is_open_access=paper.source_specific.get("is_open_access"),
            source_names=[paper.source_name] if paper.source_name else [],
            source_specific=paper.source_specific,
        )

        if pdf_path is not None:
            result.pdf_downloaded = True
            result.pdf_path = str(pdf_path)
            result.pdf_source = pdf_source
            pdfs_downloaded += 1
            pdf_status = PaperPDFStatus(
                paper_title=paper.title,
                paper_arxiv_id=paper.arxiv_id,
                paper_doi=paper.doi,
                downloaded=True,
                pdf_path=str(pdf_path),
                pdf_source=pdf_source,
                file_size_bytes=pdf_path.stat().st_size,
            )
        else:
            pdfs_failed += 1
            pdf_status = PaperPDFStatus(
                paper_title=paper.title,
                paper_arxiv_id=paper.arxiv_id,
                paper_doi=paper.doi,
                downloaded=False,
                error=_failure_reason(paper),
            )

        results.append(result)
        pdf_statuses.append(pdf_status)

    # Sort results to prioritize papers with a downloadable PDF.
    # Tier 0: already downloaded this run
    # Tier 1: arXiv ID — extremely reliable to download on retry
    # Tier 2: direct open PDF URL from S2
    # Tier 3: needs DOI/OpenAlex fallback or has no known PDF route
    zipped = list(zip(results, pdf_statuses, raw_papers, strict=True))

    def sort_key(item):
        res, _, raw = item
        year_rank = -(res.year or 0)
        if res.pdf_downloaded:
            return (0, year_rank)
        if res.arxiv_id:
            return (1, year_rank)
        if raw.source_specific.get("pdf_url"):
            return (2, year_rank)
        return (3, year_rank)

    zipped.sort(key=sort_key)

    # Unzip back to lists
    results = [item[0] for item in zipped]
    pdf_statuses = [item[1] for item in zipped]
    raw_papers = [item[2] for item in zipped]

    # ── 5. Compute language bias audit ──────────────────────────────────
    audit_schema: LanguageBiasAuditSchema | None = None
    if source_diagnostics:
        try:
            audit = compute_bias_audit(
                source_diagnostics,
                request.language_policy,
                variants,
            )
            audit_schema = LanguageBiasAuditSchema(
                policy=audit.policy,
                candidate_counts_by_language=audit.candidate_counts_by_language,
                english_dominance_score=audit.english_dominance_score,
                adjustments_applied=audit.adjustments_applied,
            )
        except Exception as exc:
            logger.warning("Failed to compute bias audit: %s", exc)

    response_variants = [
        QueryVariantSchema(source=v.source, query=v.query, language=v.language) for v in variants
    ]

    response = PaperSearchResponse(
        query=request.query,
        total_found=len(raw_papers),
        total_returned=len(raw_papers),
        search_time_ms=search_ms,
        download_time_ms=download_ms,
        pdfs_downloaded=pdfs_downloaded,
        pdfs_failed=pdfs_failed,
        papers=results,
        detected_language=detected_lang,
        query_variants=response_variants,
        language_bias_audit=audit_schema,
        source_diagnostics=source_diagnostics,
    )

    return SearchOutcome(response=response, raw_papers=raw_papers, pdf_statuses=pdf_statuses)


# ── helpers ──────────────────────────────────────────────────────────────


def _normalize_source_name(name: str, valid_sources: set[str]) -> str | None:
    """Map a possibly multi-word source name to a canonical single source.

    Examples:
        "Semantic Scholar" → "semantic_scholar"
        "Semantic Scholar, arXiv" → "semantic_scholar" (first match by position)
        "Exa, Firecrawl" → "exa" (first match by position)
        "unknown_source" → None
    """
    _ALIASES = {
        "semantic scholar": "semantic_scholar",
        "open alex": "openalex",
    }
    lower = name.lower().strip()
    # Exact match
    if lower in valid_sources:
        return lower
    # Check aliases
    for alias, canonical in _ALIASES.items():
        if alias in lower and canonical in valid_sources:
            return canonical
    # Find the earliest appearing canonical source in the string
    best: str | None = None
    best_pos = len(lower)
    for canonical in valid_sources:
        pos = lower.find(canonical)
        if pos != -1 and pos < best_pos:
            best = canonical
            best_pos = pos
    return best


def _deduplicate_raw_books(papers: list[RawPaper]) -> list[RawPaper]:
    """Deduplicate by strongest identifier, preserving order."""
    seen: set[str] = set()
    result: list[RawPaper] = []
    for p in papers:
        key = p.semantic_scholar_id or p.arxiv_id or p.doi or p.title.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result


def _classify_pdf_source(paper: RawPaper) -> str | None:
    """Return a short label describing where the PDF came from."""
    if paper.arxiv_id:
        return "arxiv_cdn"
    if paper.source_specific.get("pdf_url"):
        return "s2_oa"
    if paper.source_specific.get("paperhub_source"):
        return str(paper.source_specific["paperhub_source"])
    return None


def _failure_reason(paper: RawPaper) -> str:
    """Return a human-readable reason why the PDF couldn't be downloaded."""
    if not paper.arxiv_id and not paper.source_specific.get("pdf_url"):
        return "no direct PDF source available from PaperHub search"
    return "download failed (server error, paywall, or non-PDF response)"


async def _search_sources_parallel(
    source_query_map: dict[str, str],
    limit: int,
    year_from: int | None,
    year_to: int | None,
) -> tuple[list[RawPaper], list[dict]]:
    """Search all configured sources in parallel with early exit optimization.

    Stops collecting results once we have >= `limit` deduplicated papers,
    to avoid unnecessary processing when the first source(s) return enough.
    """
    # Track papers as they arrive to enable early exit
    collected: list[RawPaper] = []
    seen_ids: set[str] = set()
    diagnostics: list[dict] = []
    found_enough = asyncio.Event()
    lock = asyncio.Lock()

    async def _search_one_source(src_name: str, src_query: str) -> None:
        """Search a single source, add to collected, update diagnostics."""
        if found_enough.is_set():
            return

        try:
            if src_name == "semantic_scholar":
                from app.core.config import get_settings as _gs
                from app.sources.semantic_scholar import SemanticScholarSource

                s2_settings = _gs()
                source = SemanticScholarSource(
                    api_key=s2_settings.semantic_scholar_api_key or None,
                    timeout=30,  # Reduced from 45s
                )
            elif src_name in ("arxiv", "openalex"):
                source = PaperHubSource()
            elif src_name == "exa":
                source = ExaSource()
            else:
                async with lock:
                    diagnostics.append(
                        {
                            "source": src_name,
                            "status": "skipped",
                            "result_count": 0,
                        }
                    )
                return

            papers = await source.search(
                query=src_query,
                limit=min(limit * 2, 100),  # Fetch extra to account for dedup
                year_from=year_from,
                year_to=year_to,
            )

            async with lock:
                for p in papers:
                    key = p.semantic_scholar_id or p.arxiv_id or p.doi or p.title.lower().strip()
                    if key not in seen_ids:
                        seen_ids.add(key)
                        collected.append(p)
                diagnostics.append(
                    {
                        "source": src_name,
                        "status": "ok",
                        "result_count": len(papers),
                    }
                )

                # Early exit if we have enough deduplicated results
                if len(collected) >= limit:
                    found_enough.set()

        except Exception as exc:
            logger.warning("Source %s failed: %s", src_name, exc)
            async with lock:
                diagnostics.append(
                    {
                        "source": src_name,
                        "status": "failed",
                        "result_count": 0,
                        "message": str(exc)[:200],
                    }
                )

    # Launch all source searches concurrently as Tasks
    task_objs: list[asyncio.Task] = [
        asyncio.create_task(_search_one_source(src_name, src_query))
        for src_name, src_query in source_query_map.items()
    ]

    # Wait for all tasks, but early exit if we have enough results
    try:
        await asyncio.wait_for(
            asyncio.gather(*task_objs, return_exceptions=True),
            timeout=30.0,
        )
    except TimeoutError:
        logger.warning("Search sources timed out after 30s")
        for t in task_objs:
            if not t.done():
                t.cancel()

    return collected, diagnostics
