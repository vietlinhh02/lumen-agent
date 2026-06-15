"""PDF ingestion pipeline.

Extracts raw text from downloaded PDFs and stores it for the later
normalization/chunking/embedding batch. Local extraction uses Poppler when
available, falls back to pypdf, then uses Gemini OCR for image-only PDFs.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import PaperChunk, PaperEnrichment, ProjectPaper

logger = logging.getLogger(__name__)

# ── Section headings (lowercase, no colon) ───────────────────────────────

_SECTION_HEADERS = [
    "abstract",
    "introduction",
    "background",
    "related work",
    "literature review",
    "preliminaries",
    "methodology",
    "method",
    "approach",
    "system design",
    "proposed method",
    "framework",
    "experimental setup",
    "experiments",
    "experimental results",
    "results",
    "evaluation",
    "discussion",
    "conclusion",
    "conclusions",
    "future work",
    "limitations",
    "acknowledgments",
    "acknowledgements",
    "references",
    "appendix",
]

# Regex patterns for section heading detection.
# Matches: "1. Introduction", "1.1 Background", "A. Related Work",
#          "III. METHODOLOGY", "## Results", "\section{Abstract}"
_SECTION_RE = re.compile(
    r"^(?:"
    r"(?:\d+(?:\.\d+)*[\.\)]?\s+)"  # "1", "1.", or "1.1)"
    r"|"
    r"(?:[A-Z]+\.\s*)"  # "A." or "III."
    r"|"
    r"(?:\\section\{\s*)"  # "\section{"
    r"|"
    r"(?:#{1,3}\s+)"  # "## "
    r")?"
    r"("
    r"[A-Z][a-zA-Z]+(?:\s+(?:[A-Z][a-zA-Z]+|and|or|of|for|to|in|with))*"
    r")"
    r"\s*:?\s*$"
)

_INLINE_SECTION_RE = re.compile(
    r"^(abstract|keywords?)\.\s+.+",
    re.IGNORECASE,
)

# Second pass: match all-caps lines that look like section headers
# e.g. "INTRODUCTION", "RELATED WORK", "EXPERIMENTAL RESULTS"
_ALLCAPS_RE = re.compile(r"^[A-Z][A-Z\s]+$")


@dataclass
class Section:
    name: str
    start_line: int
    end_line: int


@dataclass
class Chunk:
    text: str
    chunk_type: str = "full_text"
    section_label: str | None = None
    page_number: int | None = None
    embedding: list[float] | None = None


# ── Public API ───────────────────────────────────────────────────────────


async def ingest_pdf(
    db: AsyncSession,
    project_paper_id: UUID,
    pdf_path: Path,
) -> str:
    """Extract raw text from PDF and store it — no chunk/embed yet.

    LLM normalization + chunk + embed happens in batch via
    :func:`normalize_project_papers`.

    Returns ``"raw_extracted"``, ``"failed"``, or ``"ocr_required"``.
    """
    text = await _extract_text(pdf_path)
    if text is not None:
        # Strip null bytes that PostgreSQL UTF8 encoding rejects
        text = text.replace("\x00", "")
    if text is None or len(text.strip()) < 50:
        await _update_status(db, project_paper_id, "ocr_required")
        await db.commit()
        logger.info("PDF appears image-only (no text layer): %s", pdf_path)
        return "ocr_required"

    try:
        # Store raw text in PaperEnrichment (upsert: may already exist)
        stmt = (
            pg_insert(PaperEnrichment)
            .values(
                project_paper_id=project_paper_id,
                raw_text=text,
                enrichment_status="completed",
            )
            .on_conflict_do_update(
                index_elements=["project_paper_id"],
                set_={"raw_text": text, "enrichment_status": "completed"},
            )
        )
        await db.execute(stmt)

        await _update_status(db, project_paper_id, "raw_extracted")
        await db.commit()
        logger.info(
            "Raw text extracted: %s (%d chars)",
            pdf_path.name,
            len(text),
        )
        return "raw_extracted"

    except Exception as exc:
        logger.exception("Raw text extraction failed for %s: %s", pdf_path, exc)
        with suppress(Exception):
            await db.rollback()
        with suppress(Exception):
            await _update_status(db, project_paper_id, "failed")
        return "failed"


# ── Stage 1: Text Extraction (Poppler + pypdf + Gemini OCR fallback) ─────


def _extract_text_poppler(pdf_path: Path) -> str | None:
    """Extract text with Poppler's pdftotext when available.

    Poppler generally preserves spaces and two-column reading order better than
    pypdf for academic PDFs. It is an optional system binary, so callers must
    fall back when it is missing or returns too little usable text.
    """
    if shutil.which("pdftotext") is None:
        return None

    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("pdftotext extraction failed for %s: %s", pdf_path, exc)
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.warning("pdftotext extraction failed for %s: %s", pdf_path, stderr)
        return None

    text = result.stdout.replace("\f", "\n").strip()
    return text or None


def _extract_text_pypdf(pdf_path: Path) -> str | None:
    """Extract text from a PDF using pypdf (fast, local, no network).

    Handles both single- and multi-column layouts natively.
    """
    try:
        reader = PdfReader(pdf_path)
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        full_text = "\n".join(parts)
        return full_text.strip() or None
    except Exception as exc:
        logger.warning("pypdf extraction failed for %s: %s", pdf_path, exc)
        return None


_OCR_MODEL = "gemini-2.5-flash"
_OCR_PROMPT = (
    "Extract all visible text from this scanned document. "
    "Return only the extracted text, preserving paragraphs and section structure."
)


async def _extract_text_ocr(pdf_path: Path) -> str | None:
    """Fallback: use Gemini vision to OCR an image-only PDF.

    Only called when pypdf returns empty text (scanned/image PDFs).
    """
    from google import genai
    from google.genai import types

    settings = get_settings()
    if not settings.google_api_key:
        logger.warning("GOOGLE_API_KEY not set, cannot OCR")
        return None

    try:
        pdf_bytes = pdf_path.read_bytes()
    except Exception as exc:
        logger.warning("Failed to read PDF for OCR %s: %s", pdf_path, exc)
        return None

    client = genai.Client(api_key=settings.google_api_key)

    try:
        response = await client.aio.models.generate_content(
            model=_OCR_MODEL,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                _OCR_PROMPT,
            ],
        )
        text = response.text
        if text and text.strip():
            logger.info("OCR extracted %d chars from %s", len(text), pdf_path.name)
            return text
        return None
    except Exception as exc:
        logger.warning("OCR failed for %s: %s", pdf_path, exc)
        return None


async def _extract_text(pdf_path: Path) -> str | None:
    """Extract text using the best available deterministic extractor."""
    text = _extract_text_poppler(pdf_path)
    if text is not None and len(text.strip()) >= 50:
        logger.info("Extracted text with pdftotext: %s (%d chars)", pdf_path.name, len(text))
        return text

    text = _extract_text_pypdf(pdf_path)
    if text is not None and len(text.strip()) >= 50:
        logger.info("Extracted text with pypdf: %s (%d chars)", pdf_path.name, len(text))
        return text

    logger.info(
        "Local PDF extractors returned too little text - trying Gemini OCR for %s",
        pdf_path.name,
    )
    return await _extract_text_ocr(pdf_path)


# ── Stage 2: Section Detection ────────────────────────────────────────────


def _detect_sections(text: str) -> list[Section]:
    """Detect academic sections by matching section headers.

    Tries three strategies in order:
    1. Exact match against known section header names.
    2. Regex for numbered / formatted headers.
    3. All-caps headers (common in IEEE/ACM papers).
    """
    lines = text.split("\n")
    sections: list[Section] = []
    section_starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Strategy 1: exact match against known headers
        lower = stripped.lower().rstrip(".: \t")
        if lower in _SECTION_HEADERS:
            section_starts.append((i, lower.capitalize()))
            continue

        # Strategy 1b: inline front-matter headings such as
        # "Abstract. We present..." from Springer-style PDFs.
        inline_match = _INLINE_SECTION_RE.match(stripped)
        if inline_match:
            section_starts.append((i, inline_match.group(1).capitalize()))
            continue

        # Strategy 2: numbered / formatted regex
        m = _SECTION_RE.match(stripped)
        if m:
            candidate = m.group(1).lower().strip()
            if any(h in candidate for h in _SECTION_HEADERS):
                section_starts.append((i, candidate.capitalize()))
                continue

        # Strategy 3: all-caps headers (IEEE/ACM style)
        if len(stripped) > 3 and len(stripped) < 60 and _ALLCAPS_RE.match(stripped):
            candidate = stripped.lower().rstrip(".:")
            # Only accept if it looks like a real section, not a random caps line
            if any(
                h in candidate
                for h in (
                    "introduction",
                    "background",
                    "related",
                    "approach",
                    "method",
                    "experiment",
                    "result",
                    "evaluation",
                    "discussion",
                    "conclusion",
                    "reference",
                    "appendix",
                    "future work",
                    "limitation",
                    "proposed",
                    "framework",
                    "implementation",
                    "dataset",
                    "analysis",
                )
            ):
                section_starts.append((i, candidate.capitalize()))
                continue

    if not section_starts:
        # No sections found — treat the whole document as one chunk
        return [Section(name="Full Text", start_line=0, end_line=len(lines) - 1)]

    for j, (start_idx, name) in enumerate(section_starts):
        end_idx = section_starts[j + 1][0] - 1 if j + 1 < len(section_starts) else len(lines) - 1
        sections.append(Section(name=name, start_line=start_idx, end_line=end_idx))

    return sections


# ── Stage 3: Chunking ──────────────────────────────────────────────────────


_MAX_CHUNK_CHARS = 2000  # ~500 tokens

_IGNORE_SECTIONS = {"References", "Appendix", "Acknowledgments", "Acknowledgements"}


def _chunk_sections(text: str, sections: list[Section]) -> list[Chunk]:
    """Split document into chunks, one per section (or split large ones)."""
    lines = text.split("\n")
    chunks: list[Chunk] = []

    for section in sections:
        if section.name in _IGNORE_SECTIONS:
            # Store references as a single chunk but skip embedding
            section_text = "\n".join(lines[section.start_line : section.end_line + 1])
            if section_text.strip():
                chunks.append(
                    Chunk(
                        text=section_text,
                        chunk_type="full_text",
                        section_label=section.name,
                    )
                )
            continue

        section_text = "\n".join(lines[section.start_line : section.end_line + 1])
        if not section_text.strip():
            continue

        if len(section_text) <= _MAX_CHUNK_CHARS:
            chunks.append(
                Chunk(
                    text=section_text,
                    chunk_type="full_text",
                    section_label=section.name,
                )
            )
        else:
            # Split large section into paragraph-level chunks
            paragraphs = re.split(r"\n\s*\n", section_text)
            current = ""
            for para in paragraphs:
                if not para.strip():
                    continue
                if len(current) + len(para) < _MAX_CHUNK_CHARS:
                    current += "\n\n" + para if current else para
                else:
                    if current:
                        chunks.append(
                            Chunk(
                                text=current,
                                chunk_type="full_text",
                                section_label=section.name,
                            )
                        )
                    current = para
            if current:
                chunks.append(
                    Chunk(
                        text=current,
                        chunk_type="full_text",
                        section_label=section.name,
                    )
                )

    return chunks


# ── Stage 4: Storage ──────────────────────────────────────────────────────


async def _store_chunks(
    db: AsyncSession,
    project_paper_id: UUID,
    chunks: list[Chunk],
) -> None:
    """Delete old chunks for this paper and insert new ones."""
    from sqlalchemy import delete

    # Remove existing full_text chunks for this paper
    await db.execute(
        delete(PaperChunk).where(
            PaperChunk.project_paper_id == project_paper_id,
            PaperChunk.chunk_type == "full_text",
        )
    )

    # Insert new chunks
    from app.core.embeddings import get_embedding_dimension, get_embedding_model_name

    dim = get_embedding_dimension()
    model_name = get_embedding_model_name()

    for chunk in chunks:
        db.add(
            PaperChunk(
                project_paper_id=project_paper_id,
                chunk_text=chunk.text,
                chunk_type=chunk.chunk_type,
                section_label=chunk.section_label,
                embedding=chunk.embedding,
                embedding_model=model_name,
                embedding_dimension=dim if chunk.embedding else None,
            )
        )

    await db.commit()


# ── Helpers ────────────────────────────────────────────────────────────────


async def _update_status(
    db: AsyncSession,
    project_paper_id: UUID,
    status: str,
) -> None:
    """Update the ``full_text_status`` on the ProjectPaper row.

    Does NOT commit — the caller is responsible for that.
    """
    result = await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    pp = result.scalar_one_or_none()
    if pp is not None:
        pp.full_text_status = status
