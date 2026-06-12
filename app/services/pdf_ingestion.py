"""PDF Ingestion Pipeline.

Extracts text from downloaded PDFs, detects sections, chunks the
content, and generates embeddings.  Designed to be called inline
after a PDF is downloaded so the enriched text is immediately
available for matrix/gap/review workflows.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from operator import itemgetter
from pathlib import Path
from uuid import UUID

import pdfplumber
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaperChunk, ProjectPaper

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
    text = _extract_text(pdf_path)
    if text is None or len(text.strip()) < 50:
        await _update_status(db, project_paper_id, "ocr_required")
        logger.info("PDF appears image-only (no text layer): %s", pdf_path)
        return "ocr_required"

    try:
        # Store raw text in PaperEnrichment
        from app.db.models import PaperEnrichment

        result = await db.execute(
            select(PaperEnrichment).where(PaperEnrichment.project_paper_id == project_paper_id)
        )
        enrichment = result.scalar_one_or_none()
        if enrichment is None:
            enrichment = PaperEnrichment(
                project_paper_id=project_paper_id,
                raw_text=text,
                enrichment_status="completed",
            )
            db.add(enrichment)
        else:
            enrichment.raw_text = text
            enrichment.enrichment_status = "completed"

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
        await _update_status(db, project_paper_id, "failed")
        return "failed"


# ── Stage 1: Text Extraction ─────────────────────────────────────────────


def _extract_text(pdf_path: Path) -> str | None:
    """Extract text from a PDF using pdfplumber (memory-efficient)."""
    try:
        lines: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=2, y_tolerance=2)
                if not words:
                    continue
                _extract_page_lines(words, page.width, lines)
        full_text = "\n".join(lines)
        return full_text if full_text.strip() else None
    except Exception as exc:
        logger.warning("Failed to extract text from %s: %s", pdf_path, exc)
        return None


def _extract_page_lines(
    words: list[dict],
    page_width: float,
    lines: list[str],
) -> None:
    """Extract lines from one page, handling two-column layout."""
    boundary = _detect_column_boundary(words, page_width)

    if boundary is not None:
        left = sorted(
            [w for w in words if w["x0"] < boundary],
            key=lambda w: (w["top"], w["x0"]),
        )
        right = sorted(
            [w for w in words if w["x0"] >= boundary],
            key=lambda w: (w["top"], w["x0"]),
        )
        for col_words in (left, right):
            if len(col_words) < 3:
                continue
            groups = pdfplumber.utils.cluster_objects(
                col_words,
                itemgetter("top"),
                1.6,
            )
            for group in groups:
                line = " ".join(w["text"] for w in group)
                lines.append(line)
    else:
        groups = pdfplumber.utils.cluster_objects(
            words,
            itemgetter("top"),
            1.6,
        )
        for group in groups:
            line = " ".join(w["text"] for w in group)
            lines.append(line)


def _detect_column_boundary(words: list[dict], page_width: float) -> float | None:
    """Detect two-column layout and return x boundary, or None."""
    if len(words) < 50:
        return None
    x_vals = sorted(w["x0"] for w in words)
    max_gap = 0.0
    boundary: float | None = None
    for i in range(len(x_vals) - 1):
        gap = x_vals[i + 1] - x_vals[i]
        if gap > max_gap and gap > page_width * 0.12:
            max_gap = gap
            boundary = (x_vals[i] + x_vals[i + 1]) / 2
    if boundary and page_width * 0.2 < boundary < page_width * 0.8:
        return boundary
    return None


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
        embedding_str = json.dumps(chunk.embedding) if chunk.embedding else None
        db.add(
            PaperChunk(
                project_paper_id=project_paper_id,
                chunk_text=chunk.text,
                chunk_type=chunk.chunk_type,
                section_label=chunk.section_label,
                embedding=embedding_str,
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
    """Update the ``full_text_status`` on the ProjectPaper row."""
    result = await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    pp = result.scalar_one_or_none()
    if pp is not None:
        pp.full_text_status = status
        await db.commit()
