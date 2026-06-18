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

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import (
    encode_batch,
    get_embedding_dimension,
    get_embedding_model_name,
)
from app.db.models import PaperChunk, ProjectPaper
from app.services.pdf_extraction import (
    ExtractionQuality,
    ExtractionResult,
    extract_with_routing,
    score_quality,
)
from app.services.pdf_ingestion import Chunk, _chunk_sections, _detect_sections

logger = logging.getLogger(__name__)

_PIPELINE_VERSION = "pdf-oxide-v2"
_MIN_TEXT_CHARS = 50  # below this we treat the PDF as image-only
# Below this score we treat the extraction as low-quality and surface the
# "ocr_required" status so the caller can route to a heavier backend.
_ROUTING_MIN_SCORE = 0.45

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
    """Extract the full text of *pdf_path* via the self-healing router.

    The router runs each registered engine (pdf_oxide, then pypdf) and
    returns the highest-scoring extraction per the 5-signal quality
    audit in :mod:`app.services.pdf_extraction.quality`. Returns
    ``None`` when no engine produced usable text (e.g. image-only scan).

    The returned text is markdown when pdf_oxide wins and plain text
    when pypdf wins. Both branches preserve enough structure for the
    regex-based section detector in :mod:`app.services.pdf_ingestion`
    to work without an LLM call.

    Note: this function returns text only. Use
    :func:`get_last_extraction_result` if you also need the engine name
    (needed by :func:`chunk_text` to skip layout cleanup for Docling
    output).
    """
    result = extract_with_routing(pdf_path, min_score=_ROUTING_MIN_SCORE)
    if result.fell_back:
        logger.info(
            "Routing fell back for %s: best=%s score=%.3f weakest=%s",
            pdf_path.name,
            result.engine or "<none>",
            result.quality.score,
            result.quality.weakest_signal,
        )
    return result.text


def get_extraction_quality(pdf_path: Path) -> ExtractionQuality:
    """Return the quality audit of the best engine's output for *pdf_path*.

    Exposed for tests and the future benchmark tooling. The returned
    object includes per-signal scores and the composite in ``score``.
    """
    result = extract_with_routing(pdf_path)
    return result.quality


def extract_and_chunk(pdf_path: Path) -> tuple[str | None, list[Chunk], str]:
    """Extract text then chunk it, propagating the engine name through cleanup.

    Returns ``(text, chunks, engine_name)`` where ``engine_name`` is the
    name of the engine that produced the winning extraction (used by
    downstream code to decide whether to skip layout cleanup).

    When no engine produced usable text, returns ``(None, [], "")``.
    """
    result = extract_with_routing(pdf_path, min_score=_ROUTING_MIN_SCORE)
    if result.text is None:
        return None, [], result.engine
    chunks = chunk_text(result.text, source_engine=result.engine)
    return result.text, chunks, result.engine


def get_last_extraction_result(pdf_path: Path) -> ExtractionResult:
    """Return the full :class:`ExtractionResult` (text + audit metadata).

    Use this when you need the per-engine scoring, not just the winner.
    The benchmark script uses this to compare engines on a corpus.
    """
    return extract_with_routing(pdf_path)


# ── Deprecated thin shims ──────────────────────────────────────────────────
# Kept so external callers (tests, scripts) that still reference these
# names keep working. They delegate to the engines in the router and
# will be removed once all callers are migrated to ``extract_with_routing``.


def _extract_text_pdf_oxide(pdf_path: Path) -> str | None:
    """Deprecated: use ``app.services.pdf_extraction.router.PdfOxideEngine``."""
    from app.services.pdf_extraction.router import PdfOxideEngine

    return PdfOxideEngine().extract(pdf_path)


def _extract_text_pypdf(pdf_path: Path) -> str | None:
    """Deprecated: use ``app.services.pdf_extraction.router.PyPdfEngine``."""
    from app.services.pdf_extraction.router import PyPdfEngine

    return PyPdfEngine().extract(pdf_path)


def _extraction_quality_score(text: str) -> float:
    """Deprecated: use ``app.services.pdf_extraction.score_quality``."""
    return score_quality(text).score


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
_JOURNAL_BOILERPLATE_RE = re.compile(
    r"^\s*(?:"
    r"research article\s+issn\b"
    r"|i\s*j\s*t\s*c\s*physics\b"
    r"|volume\s+\d+\s*\|\s*issue\s+\d+"
    r"|v\s*olume\s+\d+\s*\|\s*issue\s+\d+"
    r"|www\.unisciencepub\.com"
    r")",
    re.IGNORECASE,
)
_LATEX_MATH_RE = re.compile(
    r"\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|nu|rho|sigma|"
    r"tau|phi|varphi|chi|psi|omega|Omega|Lambda|frac|sqrt|sum|prod|int|"
    r"partial|nabla|cdot|times|leq|geq|neq|approx|equiv)\b"
)
_UNICODE_MATH_RE = re.compile(r"[∑∏∫∂∇≈≠≤≥±×÷∞°′″πµνρσχψωΩΛγφϕθλ]")
_EQUATION_LABEL_RE = re.compile(r"\(\s*\d{1,3}\s*\)")
_MATH_OPERATOR_RE = re.compile(
    r"(?:[A-Za-zΑ-Ωα-ω0-9_\)\]]\s*[=<>]\s*[\-A-Za-zΑ-Ωα-ω0-9_\(\[]|[+\-*/^])"
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


def _strip_markdown_noise(text: str) -> str:
    """Strip markdown bold/italic/code/link markers and collapse whitespace.

    This pass is engine-agnostic — both pdf_oxide (markdown native) and
    Docling (markdown export) emit some markdown noise. Keep it always-on.
    """
    text = _strip_markdown_inline(text)
    # Collapse multiple spaces (a single PDF column wrap can introduce them)
    text = re.sub(r" {2,}", " ", text)
    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_layout_artifacts(text: str) -> str:
    """Strip PDF layout artefacts (headers, footers, page numbers, TOC).

    Only applied to fast-tier engines (pdf_oxide / pypdf). Docling's
    layout-aware output already excludes page furniture at the source
    (we walk ``document.texts`` and skip ``page_header`` / ``page_footer``
    labels), so re-running these regexes on Docling output is wasted
    work — and worse, some of them (TOC dotted-leader detection) can
    accidentally strip legitimate hyphenation in math-heavy paragraphs.

    Operations applied:
    1. Drop horizontal-rule separators.
    2. Drop standalone page-number lines (raw or bolded).
    3. Drop e-mail / DOI / publisher footer lines.
    4. Drop journal boilerplate (``www.unisciencepub.com`` etc.).
    5. Strip inline e-mail fragments inside paragraphs.
    6. Drop / truncate arXiv watermark lines.
    7. Drop TOC entry / TOC dotted-leader lines.
    8. Drop mid-paragraph page numbers (e.g. ``text 13 more text``).
    9. Fix hyphenation at line ends (``phys- ics`` → ``physics``).
    """
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
            or _JOURNAL_BOILERPLATE_RE.match(stripped)
        ):
            continue
        # Strip any e-mail fragments that are buried inside a line
        # (e.g. "Tel.: +32 ... E-mail: a@b.c ...").
        stripped = _EMAIL_INLINE_RE.sub("", stripped).strip()
        if not stripped:
            continue
        # Drop / truncate arXiv watermark.
        if "arXiv:" in stripped:
            stripped = _ARXIV_RE.sub("", stripped).strip()
            if not stripped:
                continue
            stripped = re.sub(r"^#+\s*", "", stripped).strip()
            if not stripped:
                continue
        # Drop subsection TOC entries.
        plain = _strip_markdown_inline(stripped)
        if _TOC_ENTRY_LINE_RE.match(plain):
            continue
        # Drop TOC dotted-leader lines.
        if _TOC_DOTTED_RE.search(stripped):
            cleaned_text = _TOC_DOTTED_RE.sub("", stripped).strip()
            if cleaned_text:
                cleaned.append(cleaned_text)
            continue
        # Drop inline page numbers injected mid-paragraph.
        stripped = _MID_PAGE_NUM_RE.sub(" ", stripped)
        # Fix hyphenation at line ends.
        stripped = re.sub(r"(\w)-\s+(\w)", r"\1\2", stripped)
        # Collapse multiple spaces.
        stripped = re.sub(r" {2,}", " ", stripped)
        cleaned.append(stripped)

    out = "\n".join(cleaned)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _normalize_text(text: str, *, source_engine: str | None = None) -> str:
    """Normalize a chunk of text before embedding and storage.

    Parameters
    ----------
    text:
        The raw extracted text.
    source_engine:
        Name of the engine that produced the text. When set to
        ``"docling"`` the layout-artifact cleanup is skipped because
        Docling already removed page furniture at the source. The
        markdown noise strip and whitespace collapse still run because
        Docling emits some bold/italic markers too.
    """
    # Step 1: engine-agnostic markdown noise + whitespace collapse.
    text = _strip_markdown_noise(text)
    # Step 2: layout-artifact cleanup only for the fast tier. Docling
    # already stripped page furniture at the source (the DoclingEngine
    # walks ``document.texts`` and skips page_header / page_footer
    # labels), so re-running these regexes is wasted work and can
    # accidentally strip legitimate hyphenation in math-heavy chunks.
    if source_engine != "docling":
        text = _strip_layout_artifacts(text)
    return text


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

    The classifier is intentionally conservative on "equation" because
    false positives silently bury narrative prose in a content-type
    bucket the retrieval layer treats as a separate stream.

    Decision order:

    1. **Explicit LaTeX blocks** (``$$…$$``, ``[ … ]``) or math
       delimiters (``( … )``) → ``equation`` (high-confidence).
    2. **Figure / table caption opener** → ``figure_caption``.
    3. **Pipe / tab-aligned table** → ``table``.
    4. **Equation-line majority** (most lines look like formulas) →
       ``equation``.
    5. Default → ``narrative``.

    "narrative"      — natural-language prose, the default
    "equation"       — math-heavy chunk, mostly symbols and short labels
    "table"          — tab-aligned or pipe-delimited tabular content
    "figure_caption" — starts with "Figure N:" or "Table N:"
    """
    stripped = text.strip()

    # 1. Strong signal: explicit LaTeX / display-math delimiters.
    # Docling emits formulas inside $$ … $$; pdf_oxide/pypdf rarely
    # produce these, so a positive match here is unambiguous.
    if _has_display_math(stripped):
        return "equation"

    # 2. Figure / table caption opener.
    if re.match(r"^(figure|table|fig\.?|tab\.?)\s*\d", stripped, re.IGNORECASE):
        return "figure_caption"

    # 3. Tabular content: pipe-delimited or multi-line aligned rows.
    if "|" in stripped and "\n" in stripped:
        return "table"
    lines = stripped.split("\n")
    aligned_rows = sum(1 for line in lines if re.search(r"\S\s{2,}\S", line))
    if lines and aligned_rows / len(lines) > 0.4 and len(lines) >= 3:
        return "table"

    # 4. Equation-line majority. We tightened the heuristic so narrative
    # chunks with sparse inline math ("We set t = 0 and find ...") don't
    # get pulled in. Now requires either:
    #   - most non-empty lines look like equations, OR
    #   - absolute count of equation lines is high AND math density
    #     is consistent across the chunk.
    nonempty_lines = [line for line in lines if line.strip()]
    if nonempty_lines:
        equation_lines = [line for line in nonempty_lines if _looks_like_equation_line(line)]
        line_ratio = len(equation_lines) / len(nonempty_lines)
        if line_ratio >= 0.5 and len(equation_lines) >= 3:
            return "equation"

        # Fallback char-level check: only counts when the chunk is
        # genuinely math-dominant. High math count alone is not enough
        # — narrative chunks in scientific papers frequently mention
        # "α", "β", "ρ" without being equations.
        letter_count = sum(1 for c in stripped if c.isalpha())
        math_count = sum(1 for c in stripped if _is_math_char(c))
        if (
            letter_count + math_count > 50
            and math_count >= 20
            and letter_count / max(letter_count + math_count, 1) < 0.45
        ):
            return "equation"

    return "narrative"


_DISPLAY_MATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Docling's $$ … $$ blocks.
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    # LaTeX display math \[ … \] and inline \( … \).
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"\\\(.*?\\\)", re.DOTALL),
)


def _has_display_math(text: str) -> bool:
    """Return True when *text* contains explicit LaTeX display-math delimiters.

    Used as a high-confidence signal by :func:`_classify_chunk_text` so
    a single ``$$E = mc^2$$`` line in an otherwise narrative chunk
    still gets classified correctly (without flagging the rest).
    """
    return any(p.search(text) for p in _DISPLAY_MATH_PATTERNS)


def _looks_like_equation_line(line: str) -> bool:
    """Return True when a line looks like a formula rather than prose.

    Tightened in 2026 to cut false-positive "equation" classifications
    on narrative text with sparse inline math. The classifier accepts
    a line when *two* independent signals fire together:

    - explicit LaTeX command (``\\alpha``, ``\\frac``, ...) **and**
      a math operator on a short line, OR
    - 3+ Unicode math symbols on a short line, OR
    - an equation label like ``(12)`` **and** a math operator.

    A lone operator on a short narrative sentence ("We set t = 0.")
    is no longer enough — we need either a LaTeX-style command, an
    equation label, or several Unicode math tokens to count.
    """
    stripped = line.strip()
    if len(stripped) < 2:
        return False
    if re.match(r"^(figure|table|fig\.?|tab\.?)\s*\d", stripped, re.IGNORECASE):
        return False
    if len(stripped) > 200:
        # Long lines are paragraph prose, not formulas.
        return False

    has_latex = bool(_LATEX_MATH_RE.search(stripped))
    unicode_math = _UNICODE_MATH_RE.findall(stripped)
    has_operator = bool(_MATH_OPERATOR_RE.search(stripped))
    has_equation_label = bool(_EQUATION_LABEL_RE.search(stripped))

    # Explicit LaTeX command + operator = equation line.
    if has_latex and has_operator:
        return True
    # Many Unicode math symbols on a short line = equation line.
    if len(unicode_math) >= 3:
        return True
    # Short line with Unicode math + operator. Catches broken pdf_oxide
    # ASCII output like "µT = diag(ν" and "T 0 = 3 K" that have only
    # one or two Unicode math tokens. The 80-char cap keeps narrative
    # paragraphs that happen to mention "α = 0.05" from being flagged.
    if len(unicode_math) >= 1 and has_operator and len(stripped) <= 80:
        return True
    # Equation label (12) with operator present = equation line. We
    # require a math marker or operator immediately before the label
    # so we don't catch citations like "see Smith (2020)".
    return has_equation_label and (has_operator or has_latex or bool(unicode_math))


def _is_math_char(char: str) -> bool:
    """Return whether *char* is a common math symbol emitted by PDF extractors."""
    return bool(_UNICODE_MATH_RE.fullmatch(char)) or char in "=<>+-*/^()[]{}|"


def chunk_text(text: str, *, source_engine: str | None = None) -> list[Chunk]:
    """Split *text* into section-aware chunks sized for the embedding model.

    Reuses the deterministic section detector + chunker from
    ``pdf_ingestion`` and then post-processes each chunk for embedding
    quality:

    1. Normalize text (strip markdown noise, page numbers, TOC lines).
    2. Classify content type (narrative / equation / table / caption).
    3. Add ~80 char overlap from the previous chunk in the same section
       so cross-boundary context is preserved.

    Parameters
    ----------
    text:
        Raw extracted text from any PDF backend.
    source_engine:
        Name of the engine that produced *text* (``"pdf_oxide"``,
        ``"pypdf"``, ``"docling"``). When ``"docling"`` the layout
        cleanup pass is skipped because Docling already stripped
        page furniture at the source. Pass ``None`` for the legacy
        behaviour (always run layout cleanup).
    """
    sections = _detect_sections(text)
    raw_chunks = _chunk_sections(text, sections)
    if not raw_chunks:
        return raw_chunks

    out: list[Chunk] = []
    for chunk in raw_chunks:
        normalized = _normalize_text(chunk.text, source_engine=source_engine)
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
    "extract_and_chunk",
    "extract_text",
    "get_extraction_quality",
    "get_last_extraction_result",
    "process_pdf",
    "_normalize_text",
    "_classify_chunk_text",
]
