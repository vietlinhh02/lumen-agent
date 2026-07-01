"""Download full-text PDFs for papers from available sources.

Priority: arXiv CDN (if arxiv_id) → Semantic Scholar openAccessPdf.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path


import httpx

from app.services.html_extractor import fetch_arxiv_html, fetch_europepmc_xml
from app.sources.base import RawPaper

logger = logging.getLogger(__name__)

_ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}.pdf"
_DEFAULT_DIR = Path("data/papers")
_CHUNK_SIZE = 64 * 1024  # 64 KiB

_HEADERS = {
    "User-Agent": "paperhub-cli/0.1 (academic research tool; +https://github.com/oraby8/paperhub-cli)",
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
}


class PDFDownloader:
    """Download PDFs from arXiv, Semantic Scholar OA URLs, or OpenAlex."""

    def __init__(
        self,
        output_dir: Path = _DEFAULT_DIR,
        timeout: float = 60.0,
    ) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._timeout = timeout

    # ── public API ─────────────────────────────────────────────────────────────

    async def resolve_pdf_url(self, paper: RawPaper) -> str | None:
        """Return the best available PDF URL for *paper*, or None."""
        # 1) arXiv CDN — fast, no rate limit, always available if we have an arxiv_id
        if paper.arxiv_id:
            return _ARXIV_PDF.format(arxiv_id=paper.arxiv_id)

        # 2) Semantic Scholar open-access PDF
        ss_pdf = paper.source_specific.get("pdf_url")
        if ss_pdf:
            return ss_pdf


        return None

    async def download(self, paper: RawPaper) -> Path | None:
        """Download the PDF for *paper*, return local file path or None."""
        # First try to extract HTML/XML if IDs are available
        if paper.arxiv_id:
            safe_arxiv = paper.arxiv_id.replace("/", "_")
            dest_md = self._dir / f"{safe_arxiv}.md"
            if dest_md.exists():
                return dest_md
                
            text = await fetch_arxiv_html(paper.arxiv_id)
            if text:
                dest_md.write_text(text, encoding='utf-8')
                logger.info(f"Extracted arXiv HTML to: {dest_md} ({len(text)} chars)")
                return dest_md

        pmc_id = paper.source_specific.get("pmc_id") if paper.source_specific else None
        if pmc_id:
            safe_pmc = pmc_id.replace("/", "_")
            dest_md = self._dir / f"{safe_pmc}.md"
            if dest_md.exists():
                return dest_md
                
            text = await fetch_europepmc_xml(pmc_id)
            if text:
                dest_md.write_text(text, encoding='utf-8')
                logger.info(f"Extracted Europe PMC XML to: {dest_md} ({len(text)} chars)")
                return dest_md
                
        # 2. Fallback to PDF download
        pdf_url = await self.resolve_pdf_url(paper)
        if not pdf_url:
            return None

        filename = _make_filename(paper)
        dest = self._dir / filename

        if dest.exists() and dest.stat().st_size > 0:
            logger.debug("PDF already cached: %s", dest)
            return dest

        async with httpx.AsyncClient(
            timeout=self._timeout, headers=_HEADERS, follow_redirects=True
        ) as client:
            try:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Failed to download PDF for '%s': %s", paper.title[:60], exc)
                return None

        content = resp.content
        # Basic check: does it look like a PDF?
        if not content.startswith(b"%PDF"):
            logger.warning("Downloaded file is not a PDF: %s — %d bytes", pdf_url, len(content))
            return None

        dest.write_bytes(content)
        logger.info("Downloaded PDF: %s (%d bytes)", dest, len(content))
        return dest

    async def download_many(
        self,
        papers: list[RawPaper],
        concurrency: int = 8,
    ) -> dict[str, Path | None]:
        """Download PDFs for a batch of papers in parallel.

        Uses an asyncio.Semaphore to cap concurrent downloads so we don't
        overwhelm upstream servers (especially arXiv). Default concurrency=8
        strikes a good balance between speed and politeness.

        Returns a dict mapping paper title → local Path or None.
        """
        if not papers:
            return {}

        sem = asyncio.Semaphore(concurrency)
        results: dict[str, Path | None] = {}

        async def _one(paper: RawPaper) -> None:
            async with sem:
                try:
                    results[paper.title] = await self.download(paper)
                except Exception as exc:
                    logger.warning("Parallel download failed for '%s': %s", paper.title[:60], exc)
                    results[paper.title] = None

        await asyncio.gather(*[_one(p) for p in papers])
        return results


def _make_filename(paper: RawPaper) -> str:
    """Build a safe, unique filename from paper metadata."""
    if paper.arxiv_id:
        # Sanitize: old-style arXiv IDs like 'gr-qc/0204022' contain a slash
        # which would create a subdirectory. Replace with underscore.
        safe_id = paper.arxiv_id.replace("/", "_")
        return f"{safe_id}.pdf"

    # Fall back to a hash of title
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", paper.title.strip().lower())[:80]
    digest = hashlib.md5(paper.title.encode()).hexdigest()[:8]
    return f"{slug}_{digest}.pdf"

