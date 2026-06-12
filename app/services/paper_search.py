"""Paper search + download orchestrator.

Glue layer that ties Semantic Scholar search to PDF download.  Exposed
as an async service function — easy to call from a router, an agent node,
or a script.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import NamedTuple

from app.core.config import get_settings
from app.schemas.paper import (
    LanguageBiasAudit as LanguageBiasAuditSchema,
    PaperAuthor,
    PaperPDFStatus,
    PaperResult,
    PaperSearchRequest,
    PaperSearchResponse,
    QueryVariant as QueryVariantSchema,
)
from app.services.pdf_downloader import PDFDownloader
from app.services.language_bias import (
    compute_bias_audit,
    detect_and_generate_variants,
)
from app.sources.base import RawPaper
from app.sources.exa import ExaSource
from app.sources.firecrawl import crawl_pdf_links
from app.sources.paperhub import PaperHubSource

logger = logging.getLogger(__name__)


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

    # ── 1. Language bias: detect + generate variants ─────────────────────
    detected_lang = "en"
    variants: list = []
    source_diagnostics: list[dict] = []

    try:
        variants, detected_lang = await detect_and_generate_variants(
            request.query,
            request.target_languages or [detected_lang, "en"],
        )
    except Exception as exc:
        logger.warning("Language bias detection failed: %s", exc)

    # ── 2. Search ────────────────────────────────────────────────────────
    t0 = time.monotonic()
    all_raw: list[RawPaper] = []

    # Normalize source names and collect queries per canonical source
    _CANONICAL_SOURCES = {"semantic_scholar", "arxiv", "exa", "firecrawl", "openalex"}
    source_query_map: dict[str, str] = {}
    for v in variants:
        canonical = _normalize_source_name(v.source, _CANONICAL_SOURCES)
        if canonical:
            # Keep the first (best) query per source
            if canonical not in source_query_map:
                source_query_map[canonical] = v.query

    if not source_query_map:
        source_query_map["semantic_scholar"] = request.query

    for src_name, src_query in source_query_map.items():
        try:
            if src_name in ("semantic_scholar", "arxiv", "openalex"):
                source = PaperHubSource()
            elif src_name == "exa":
                source = ExaSource()
            else:
                # firecrawl handled separately after search
                continue

            papers = await source.search(
                query=src_query,
                limit=min(request.limit, 100),
                year_from=request.year_from,
                year_to=request.year_to,
            )
            all_raw.extend(papers)
            source_diagnostics.append(
                {
                    "source": src_name,
                    "status": "ok",
                    "result_count": len(papers),
                }
            )
        except Exception as exc:
            logger.warning("Source %s failed: %s", src_name, exc)
            source_diagnostics.append(
                {
                    "source": src_name,
                    "status": "failed",
                    "result_count": 0,
                    "message": str(exc)[:200],
                }
            )

    search_ms = round((time.monotonic() - t0) * 1000, 1)
    raw_papers = _deduplicate_raw_books(all_raw)
    raw_papers = raw_papers[: request.limit]

    # ── 2.5. Enrich PDF links via Firecrawl ─────────────────────────────
    try:
        all_raw = await crawl_pdf_links(all_raw)
    except Exception as exc:
        logger.warning("Firecrawl crawl failed: %s", exc)

    # ── 3. Build paper results ───────────────────────────────────────────
    results: list[PaperResult] = []
    pdf_statuses: list[PaperPDFStatus] = []

    pdfs_downloaded = 0
    pdfs_failed = 0
    download_ms: float | None = None

    # ── 3. Download PDFs (optional) ──────────────────────────────────────
    if request.download_pdfs and raw_papers:
        t_dl = time.monotonic()
        downloader = PDFDownloader(output_dir=pdf_dir, timeout=90)
        pdf_map = await downloader.download_many(raw_papers)
        download_ms = round((time.monotonic() - t_dl) * 1000, 1)
    else:
        pdf_map: dict[str, Path | None] = {}

    # ── 4. Assemble output ───────────────────────────────────────────────
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

    # Sort results to prioritize papers with a direct PDF route.
    # We zip results and pdf_statuses to keep their order synchronized
    zipped = list(zip(results, pdf_statuses, raw_papers, strict=True))

    def sort_key(item):
        res, _, raw = item
        year_rank = -(res.year or 0)
        # Priority 1: Has arXiv ID (extremely reliable to download)
        if res.arxiv_id:
            return (0, year_rank)
        # Priority 2: Has a direct open PDF URL from any PaperHub provider
        if raw.source_specific.get("pdf_url"):
            return (1, year_rank)
        # Priority 3: Needs DOI/OpenAlex fallback or has no known PDF route
        return (2, year_rank)

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
