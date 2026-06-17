"""One-shot PDF full-text ingestion.

Replaces the old extract -> store raw -> batch normalize pipeline with a single
synchronous (per-paper) pass that goes from PDF to embedded chunks:

    pdf_oxide extract (markdown, academic profile)
        -> deterministic section detection
        -> paragraph-aware chunking
        -> text cleanup (bold noise, page numbers, TOC artefacts)
        -> batch embedding
        -> PaperChunk rows
        -> full_text_status = "completed"

No LLM normalization, no Gemini OCR, no batch trigger. The old
``pdf_ingestion`` / ``pdf_normalizer`` modules are kept for tests and the
slower manual path; this service is the hot path used by ``project.py``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pdf_oxide import PdfDocument
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import (
    encode_batch,
    get_embedding_dimension,
    get_embedding_model_name,
)
from app.db.models import PaperChunk, ProjectPaper
from app.services.pdf_ingestion import Chunk, _chunk_sections, _detect_sections

logger = logging.getLogger(__name__)

_PIPELINE_VERSION = "pdf-oxide-v2"
_MIN_TEXT_CHARS = 50  # below this we treat the PDF as image-only

# Overlap between consecutive chunks within the same section. ~80 chars is
# enough to keep a sentence boundary's worth of context without bloating
# the embedding storage. Set to 0 to disable.
_CHUNK_OVERLAP_CHARS = 80


@dataclass
class FulltextResult:
    status: str  # "completed" | "failed" | "ocr_required"
    chunk_count: int = 0
    char_count: int = 0


def extract_text(pdf_path: Path) -> str | None:
    """Extract the full text of *pdf_path* using pdf_oxide's academic profile.

    Returns ``None`` if the PDF has no usable text layer (image-only scan).
    The markdown output keeps heading structure, which makes the regex-based
    section detector downstream work well without an LLM call.
    """
    try:
        doc = PdfDocument(pdf_path)
    except Exception as exc:
        logger.warning("pdf_oxide failed to open %s: %s", pdf_path, exc)
        return None

    try:
        text = doc.to_markdown_all(
            preserve_layout=True,
            detect_headings=True,
            include_images=False,
        )
    except Exception as exc:
        logger.warning("pdf_oxide markdown extraction failed for %s: %s", pdf_path, exc)
        return None
    finally:
        # PdfDocument holds a Rust handle; release the local ref.
        del doc

    text = text.replace("\x00", "").strip() if text else ""
    return text or None


# ── Text cleanup helpers ────────────────────────────────────────────────────
# pdf_oxide emits markdown with bold/italic markers wrapping every word
# inside headings, abstracts, and equation labels. We strip these so the
# embedding model sees plain text, and so the chunk_text stored in the
# database renders cleanly in the UI.


_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
# Standalone page-number-like lines: just a 1-4 digit number on its own line
_PAGE_NUM_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$")
# Bold page number on its own line: "**13**" or "**2**"
_BOLD_PAGE_NUM_RE = re.compile(r"^\s*\*\*\d{1,4}\*\*\s*$")
# Subsection TOC entry: "A. Title 12" or "**A.** **Title** **12**"
# We accept: optional bold, single uppercase letter or number, dot,
# title (up to ~10 words), trailing page number.
_TOC_ENTRY_LINE_RE = re.compile(
    r"^\s*"
    r"(?:\*+\s*)?"
    r"(?:\d+(?:\.\d+)*\.?|[A-Z]+)\.\s+"
    r"[A-Z][^.\n]{0,80}?"
    r"(?:\*+\s*)?"
    r"\d{1,3}\s*$",
)
# Page number injected mid-paragraph: "  ... text 13 more text  ..."
# We only remove the digit token if it sits between two letters or is the
# only thing on a line. We keep digits in equations like "Eq. (13)".
_MID_PAGE_NUM_RE = re.compile(r"(?<=[A-Za-z\.\)])\s+\d{1,3}(?=\s+[A-Z])")
# TOC dotted leaders
_TOC_DOTTED_RE = re.compile(r"\s*\.{3,}\s*\d{1,4}\s*$")
# Horizontal rules
_HR_RE = re.compile(r"^\s*-{3,}\s*$|^\s*\*{3,}\s*$")
# arXiv watermark lines: "arXiv:NNNN.NNNNNvN [cat] DD Mon YYYY"
# The line may be preceded by a markdown heading ("# ") or other noise, and
# may have TOC content glued onto the end (e.g. "E. Title 14"). We split on
# arXiv and keep only what comes before it.
_ARXIV_RE = re.compile(r"arXiv:\d{4}\.\d{4,5}(v\d+)?(\s*\[[^\]]+\])?.*$", re.IGNORECASE)
# Email/affiliation fragments. Match even when buried inside a contact
# line ("Tel.: +32 ... E-mail: a@b.c") - we strip from the match onward.
_EMAIL_INLINE_RE = re.compile(
    r"\b(?:e-?mail|electronic address)\s*[:\-]?\s*[\w.+-]+@[\w.-]+\s*",
    re.IGNORECASE,
)
# Standalone email/affiliation lines (only at the start)
_EMAIL_LINE_RE = re.compile(
    r"^\s*(?:e-?mail|electronic address|tel\.?|phone|fax)\s*[:\-]",
    re.IGNORECASE,
)
# Publisher / DOI footers
_PUBLISHER_LINE_RE = re.compile(
    r"^\s*(?:published by|©|copyright|doi:|http://|https://|www\.).*$",
    re.IGNORECASE,
)


def _strip_markdown_inline(text: str) -> str:
    """Replace markdown inline markers with their visible content.

    >>> _strip_markdown_inline("**foo** and *bar* and [link](https://x)")
    'foo and bar and link'
    """
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1", text)
    return text


def _normalize_text(text: str) -> str:
    """Normalize a chunk of text before embedding and storage.

    Operations applied:
    1. Strip markdown inline markers (bold, italic, code, links)
    2. Drop standalone page-number lines (raw, bold, or TOC entries)
    3. Drop horizontal-rule separators
    4. Drop arXiv watermark lines, even if glued to other content
    5. Collapse runs of whitespace
    6. Fix common pdf_oxide artefacts: word splits across line breaks
       ("phys- ics" -> "physics"), hyphenation at line ends
    """
    # Pre-pass: strip markdown inline markers (handles multi-line bold spans)
    text = _strip_markdown_inline(text)
    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        # Drop horizontal rules
        if _HR_RE.match(stripped):
            continue
        # Drop standalone page-number lines (raw or bolded)
        if (
            _PAGE_NUM_LINE_RE.match(stripped)
            or _BOLD_PAGE_NUM_RE.match(stripped)
        ):
            continue
        # Drop e-mail / electronic address / DOI / publisher footers
        if (
            _EMAIL_LINE_RE.match(stripped)
            or _PUBLISHER_LINE_RE.match(stripped)
        ):
            continue
        # Strip any e-mail fragments that are buried inside a line
        # (e.g. "Tel.: +32 ... E-mail: a@b.c ...").
        stripped = _EMAIL_INLINE_RE.sub("", stripped).strip()
        if not stripped:
            continue
        # Drop / truncate arXiv watermark. The line may have a heading
        # prefix ("# ") or have TOC content glued on after the watermark
        # (e.g. "# arXiv:0710.4474v1 [gr-qc] 24 Oct 2007E. Title 14").
        if "arXiv:" in stripped:
            stripped = _ARXIV_RE.sub("", stripped).strip()
            if not stripped:
                continue
            # Strip leading markdown heading markers the regex left behind
            stripped = re.sub(r"^#+\s*", "", stripped).strip()
            if not stripped:
                continue
        # Drop subsection TOC entries. We have to check the *plain* form
        # of the line (with markdown inline markers stripped) because
        # pdf_oxide bolds the title and page number separately:
        # "A. Review of wormhole physics 2"
        plain = _strip_markdown_inline(stripped)
        if _TOC_ENTRY_LINE_RE.match(plain):
            continue
        # Drop TOC dotted-leader lines ("3.2 Title ............ 47")
        if _TOC_DOTTED_RE.search(stripped):
            cleaned_text = _TOC_DOTTED_RE.sub("", stripped).strip()
            if cleaned_text:
                cleaned.append(cleaned_text)
            continue
        # Drop inline page numbers injected mid-paragraph
        stripped = _MID_PAGE_NUM_RE.sub(" ", stripped)
        # Fix hyphenation at line ends
        stripped = re.sub(r"(\w)-\s+(\w)", r"\1\2", stripped)
        # Collapse multiple spaces
        stripped = re.sub(r" {2,}", " ", stripped)
        cleaned.append(stripped)

    out = "\n".join(cleaned)
    # Collapse 3+ consecutive newlines to 2
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _add_overlap(prev_chunk: str, next_chunk: str) -> str:
    """Add the trailing *overlap_chars* of *prev_chunk* as a context
    prefix to *next_chunk*. Returns the augmented next chunk.

    We only prepend overlap when:
      - the previous chunk contains natural language (more than half
        ASCII letters)
      - the previous chunk ends mid-sentence (not at a hard cut)
      - the tail contains at least one full word ≥ 4 chars (avoids
        useless fragments like "[…al…]")

    Skipping overlap for equation-heavy or single-word-tail chunks
    prevents polluting the next chunk with math symbols.
    """
    if _CHUNK_OVERLAP_CHARS <= 0 or not prev_chunk:
        return next_chunk
    tail = prev_chunk[-_CHUNK_OVERLAP_CHARS:].strip()
    if not tail:
        return next_chunk
    # Find the last word boundary in the tail so we don't cut words in half
    last_space = tail.rfind(" ")
    if last_space > 20:
        tail = tail[last_space + 1:]
    # Require at least one meaningful word (≥ 4 alpha chars) in the tail
    if not re.search(r"[A-Za-z]{4,}", tail):
        return next_chunk
    # Only keep overlap if the tail ends mid-sentence
    if tail[-1] in ".!?":
        return next_chunk
    return f"[…{tail}…]\n\n{next_chunk}"


def _classify_chunk_text(text: str) -> str:
    """Return a content_type hint for a chunk.

    "narrative"      — natural-language prose, the default
    "equation"       — math-heavy chunk, mostly symbols and short labels
    "table"          — tab-aligned or pipe-delimited tabular content
    "figure_caption" — starts with "Figure N:" or "Table N:"
    """
    stripped = text.strip()
    # Figure / Table caption
    if re.match(r"^(figure|table|fig\.?|tab\.?)\s*\d", stripped, re.IGNORECASE):
        return "figure_caption"
    # Tabular: many lines with multiple spaces, or pipe chars
    if "|" in stripped and "\n" in stripped:
        return "table"
    lines = stripped.split("\n")
    aligned_rows = sum(1 for line in lines if re.search(r"\S\s{2,}\S", line))
    if lines and aligned_rows / len(lines) > 0.4 and len(lines) >= 3:
        return "table"
    # Equation-heavy: alpha ratio < 30% AND many math symbols
    letter_count = sum(1 for c in stripped if c.isalpha())
    symbol_count = sum(1 for c in stripped if c in "∑∏∫∂∇≈≠≤≥±×÷∞°′″")
    if letter_count + symbol_count > 50:
        if letter_count / max(letter_count + symbol_count, 1) < 0.4:
            return "equation"
    return "narrative"


def chunk_text(text: str) -> list[Chunk]:
    """Split *text* into section-aware chunks sized for the embedding model.

    Reuses the deterministic section detector + chunker from
    ``pdf_ingestion`` and then post-processes each chunk for embedding
    quality:

    1. Normalize text (strip markdown noise, page numbers, TOC lines).
    2. Classify content type (narrative / equation / table / caption).
    3. Add ~80 char overlap from the previous chunk in the same section
       so cross-boundary context is preserved.
    """
    sections = _detect_sections(text)
    raw_chunks = _chunk_sections(text, sections)
    if not raw_chunks:
        return raw_chunks

    out: list[Chunk] = []
    for chunk in raw_chunks:
        normalized = _normalize_text(chunk.text)
        if not normalized.strip():
            continue
        # Add overlap from the previous chunk in the same section
        if out and out[-1].section_label == chunk.section_label:
            normalized = _add_overlap(out[-1].text, normalized)
        content_type = _classify_chunk_text(normalized)
        out.append(
            Chunk(
                text=normalized,
                chunk_type=content_type,
                section_label=chunk.section_label,
                page_number=chunk.page_number,
            )
        )
    return out


async def process_pdf(
    db: AsyncSession,
    project_paper_id: UUID,
    pdf_path: Path,
) -> FulltextResult:
    """Extract, chunk, embed, and store a PDF in one pass.

    Returns a :class:`FulltextResult` whose ``status`` is the final
    ``full_text_status`` value to set on the ``ProjectPaper`` row. The caller
    is responsible for updating that row.
    """
    text = extract_text(pdf_path)
    if text is None or len(text) < _MIN_TEXT_CHARS:
        logger.info("PDF appears image-only or empty: %s", pdf_path)
        return FulltextResult(status="ocr_required")

    chunks = chunk_text(text)
    if not chunks:
        logger.warning("Chunker produced 0 chunks for %s", pdf_path)
        return FulltextResult(status="failed")

    await _store_chunks(db, project_paper_id, chunks)
    await _update_status(db, project_paper_id, "completed")
    await db.commit()

    logger.info(
        "Fulltext done: %s - %d chunks, %d chars",
        pdf_path.name,
        len(chunks),
        len(text),
    )
    return FulltextResult(status="completed", chunk_count=len(chunks), char_count=len(text))


async def _store_chunks(
    db: AsyncSession,
    project_paper_id: UUID,
    chunks: list[Chunk],
) -> None:
    """Embed chunks in one batch call and replace existing full_text rows."""
    texts = [chunk.text for chunk in chunks]
    try:
        embeddings = await encode_batch(texts)
    except Exception as exc:
        logger.exception("Batch embedding failed for %s: %s", project_paper_id, exc)
        raise

    model_name = get_embedding_model_name()
    dimension = get_embedding_dimension()

    # Replace any existing full_text chunks for this paper so re-runs are clean.
    await db.execute(
        delete(PaperChunk).where(
            PaperChunk.project_paper_id == project_paper_id,
            PaperChunk.chunk_type == "full_text",
        )
    )

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        section = chunk.section_label
        if section and len(section) > 64:
            section = section[:64]
        # Map content_type to the enum expected by the schema
        if chunk.chunk_type in ("equation", "table", "figure_caption"):
            content_type = chunk.chunk_type
        else:
            content_type = "narrative"
        db.add(
            PaperChunk(
                project_paper_id=project_paper_id,
                chunk_text=chunk.text,
                chunk_type="full_text",
                section_label=section,
                section_path=section,
                chunk_index=None,
                content_type=content_type,
                pipeline_version=_PIPELINE_VERSION,
                content_hash=sha256(chunk.text.encode("utf-8")).hexdigest(),
                embedding=embedding,
                embedding_model=model_name,
                embedding_dimension=dimension,
            )
        )


async def _update_status(
    db: AsyncSession,
    project_paper_id: UUID,
    status: str,
) -> None:
    result = await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    pp = result.scalar_one_or_none()
    if pp is not None:
        pp.full_text_status = status


__all__ = [
    "FulltextResult",
    "chunk_text",
    "extract_text",
    "process_pdf",
    "_normalize_text",
    "_classify_chunk_text",
]
