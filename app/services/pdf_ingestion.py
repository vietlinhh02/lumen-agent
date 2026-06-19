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
#          "III. METHODOLOGY", "## Results", "#### Title", "\section{Abstract}"
# Continuation words accept both Title-case and lower-case forms so we can
# capture academic titles like "1. The Grandfather Paradox" or
# "3. The Consequences of Consistent Closed Timelike Curves".
_SECTION_RE = re.compile(
    r"^(?:"
    r"(?:\d+(?:\.\d+)*[\.\)]?\s+)"  # "1", "1.", or "1.1)"
    r"|"
    r"(?:[A-Z]+\.\s*)"  # "A." or "III."
    r"|"
    r"(?:\\section\{\s*)"  # "\section{"
    r"|"
    r"(?:#{1,6}\s+)"  # "## ", "#### "
    r")?"
    r"("
    r"[A-Z][a-zA-Z]+"
    r"(?:\s+(?:[A-Z][a-zA-Z]+|[a-z][a-zA-Z]+|and|or|of|for|to|in|with|on|the|a|an))*"
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

# ── Front-matter / false-positive rejection (added in v2) ─────────────────
#
# Many body sentences match the heading regex (e.g. "1. Let us choose
# the canonical coordinates so that"). We use the rules below to reject
# them. The set is intentionally small — section titles almost never
# contain these words UNLESS the line is a body sentence.
_BODY_SENTENCE_STARTS = frozenset(
    {
        # Pronouns / demonstratives that head sentences, not headings
        "we", "i", "our", "you", "your", "it", "its", "they", "their",
        "this", "that", "these", "those", "such",
        # Conjunctions / transitions
        "however", "therefore", "thus", "hence", "moreover",
        "furthermore", "nevertheless", "nonetheless", "although",
        "though", "since", "because", "whereas", "while", "if", "when",
        "as", "but", "so", "yet", "or", "and",
        # Common verbs at start of body sentences
        "let", "consider", "suppose", "assume", "note", "recall",
        "observe", "remark", "define", "introduce", "show", "prove",
        "demonstrate", "discuss", "describe", "explain", "present",
        "examine", "explore", "investigate", "study", "analyze",
        "compare", "contrast", "evaluate", "measure", "estimate",
        "derive", "obtain", "compute", "calculate", "find", "give",
        "provide", "suggest", "propose", "argue", "claim", "conclude",
        # Common openers of academic prose
        "in", "on", "for", "with", "to", "from", "by", "of", "at",
        "between", "among", "through", "via",
        # Phrasal openers (after stripping "1. " prefix)
        "first", "second", "third", "fourth", "fifth", "next", "then",
        "finally", "lastly", "firstly", "secondly",
    }
)

# arXiv ID + common journal-info strings to reject outright
_NON_SECTION_LINE_RE = re.compile(
    r"^\s*#*\s*(?:"
    r"arXiv:"  # arXiv:NNNN.NNNNN
    r"|(?:article in press|accepted manuscript|received|revised|"
    r"available online|published online|preprint|in press|"
    r"to be published|under review|submitted to|manuscript)"
    r"|(?:copyright|©|elsevier|springer|wiley|ieee|acm|oup|cambridge university press)"
    r"|(?:typeset|noname|not for citation|open access)"
    r"|(?:year of|month of|date of)"
    r")",
    re.IGNORECASE,
)

# TOC entry pattern: "1.2.3 Title .... 47" — has dots + page number at the end
_TOC_DOTTED_RE = re.compile(
    r"^\d+(?:\.\d+)*\.?\s+.{2,80}\s*\.{3,}\s*\d+\s*$"
)
_TOC_DOTTED_BOLD_RE = re.compile(
    r"^\*\*\d+(?:\.\d+)*\.?\s+.+?\.{3,}.*?\d+\*\*\s*$"
)

# Reject lines that are clearly front matter / author block
_AUTHOR_LINE_RE = re.compile(
    r"^\*\*[A-Z][a-zA-Z\.\-]+(?:\s+[A-Z][a-zA-Z\.\-]+){0,4}\*\*$"
)

# "Contents" / "Table of contents" with a TOC immediately following
_TOC_HEADER_RE = re.compile(
    r"^(?:table\s+of\s+)?contents?\.?\s*$",
    re.IGNORECASE,
)

# A line that has lots of bolded number+text pairs is a TOC entry list.
# Used to drop the "Contents" section that contains "1 Introduction 1"
# "2 Methods 5" etc. lines instead of real body text.
_TOC_ENTRY_RE = re.compile(
    r"\*\*\d+(?:\.\d+)*\*\*\s+\*\*[A-Z][^*\n]{2,60}\*\*\s+\d+\s*$"
)


def _strip_markdown_noise(line: str) -> str:
    """Strip common pdf_oxide markdown noise from a line.

    Returns the line with leading ``**...**`` (bold) wrappers and markdown
    heading hashes removed, so the regex below sees the visible text only.
    """
    s = line.strip()
    # Drop leading "####" / "###" / "##" / "#" prefix
    s = re.sub(r"^#{1,6}\s+", "", s)
    # Collapse bold markers so "**Clifford** **M.** **Will**" -> "Clifford M. Will"
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    # Collapse italic markers
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
    return s.strip()


def _has_section_keyword(text_lower: str) -> bool:
    """Return True if *text_lower* looks like a real section header.

    A "real" section header is one where a known section keyword appears
    in a *structural* position — not just as a content word in the middle
    of a body sentence. We require the keyword to either:

    1. Be the entire visible text (case-insensitive).
    2. Be the FIRST word of the visible text — i.e. "Introduction to ...",
       "Results: ...", "Methodology and ...".
    3. Be a multi-word header that appears contiguously at the start,
       e.g. "Related work on ...".

    This deliberately rejects "we summarize the previous results as
    follows" (keyword "results" appears in the middle of a body
    sentence) and "the conclusions are ..." (keyword "conclusions" in
    the middle), but accepts "Results", "1. Results", "## Results".
    """
    s = text_lower.strip().rstrip(".: \t")
    if not s:
        return False

    # Tokenize once
    tokens = re.findall(r"[a-z][a-z\-]*", s)

    def _is_at_start(keyword: str) -> bool:
        """Return True if *keyword* appears as a contiguous prefix of tokens."""
        kw_tokens = keyword.split()
        if len(kw_tokens) > len(tokens):
            return False
        return tokens[: len(kw_tokens)] == kw_tokens

    # Whole-string match
    if s in _SECTION_HEADERS:
        return True
    # Whole-string match with trailing punctuation removed
    for h in _SECTION_HEADERS:
        if s == h.rstrip("s") or s + "s" == h or s.rstrip("s") == h:
            return True
    # Prefix-of-tokens match
    return any(_is_at_start(h) for h in _SECTION_HEADERS)


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


def _is_valid_section_title(
    candidate: str,
    stripped_line: str,
    has_explicit_prefix: bool,
) -> bool:
    """Validate a candidate section title to reject body sentences.

    Returns True if *candidate* looks like a real academic section title.
    *has_explicit_prefix* is True when the original line had "1.", "1.1",
    "##", "\\section{}", etc. — these are stronger structural signals than
    a bare Title-Case phrase, and we are willing to accept longer titles
    in that case (e.g. "1. The Grandfather Paradox").
    """
    if not candidate:
        return False

    words = candidate.split()
    if not words:
        return False

    # Reject candidates that contain common body-sentence openers.
    # We only check the FIRST word: a body sentence almost always starts
    # with "We", "This", "However", "In", "Let", etc. Real headings almost
    # never start with these.
    first_word_lower = re.sub(r"[^a-z]", "", words[0].lower())
    if first_word_lower in _BODY_SENTENCE_STARTS:
        return False

    # Reject candidates that contain a body-sentence open word in position 2+.
    # e.g. "The use of", "An overview of" are fine, but "The way in which"
    # or "In this section we" are not.
    tail = " ".join(w.lower() for w in words[1:])
    if any(
        tail.startswith(p) or f" {p} " in tail
        for p in (
            "we discuss",
            "we present",
            "we propose",
            "we show",
            "we have",
            "we will",
            "we can",
            "we use",
            "we define",
            "we assume",
            "we obtain",
            "we derive",
            "we compute",
            "we find",
            "we give",
            "we argue",
            "we claim",
            "we conclude",
            "we investigate",
            "we study",
            "we examine",
            "we analyze",
            "we consider",
            "we note",
            "we observe",
            "we remark",
            "we let",
            "we see",
            "in this section",
            "in this paper",
            "in this work",
            "in what follows",
            "in the following",
            "in the next",
            "is shown in",
            "are shown in",
            "is defined as",
            "are defined as",
            "it is",
            "there is",
            "there are",
            "as we",
            "if we",
            "when we",
            "for each",
            "for any",
            "for some",
            "for all",
            "such that",
            "such as",
            "let us",
            "it follows",
            "is a",
            "is the",
            "is an",
            "are the",
            "are a",
            "are an",
            "which is",
            "which are",
            "that is",
            "that are",
            "approach creates",
            "method needs",
            "vector it",
            "creates a user",
            "approach of",
            "method of",
            "approach is",
            "method is",
            "approach to",
            "method to",
            "approach for",
            "method for",
        )
    ):
        return False

    # Reject candidates that look like two words concatenated by a stray
    # uppercase (e.g. "Thediagonal", "Forthe", "ofthis") — typical
    # pdf_oxide bold-merge artefacts in tables / footers.
    if any(re.search(r"[a-z][A-Z]", w) for w in words):
        return False

    # Reject candidates that are way too long. Without a prefix we want
    # short noun phrases (≤ 6 words). With an explicit prefix we accept
    # up to 10 words for things like "1. The Consequences of Consistent
    # Closed Timelike Curves".
    max_words = 10 if has_explicit_prefix else 6
    if len(words) > max_words:
        return False

    # Reject single-word candidates that are not known section keywords.
    # This catches "Tab" (author), "Nils" (author), "Article" (random),
    # and "Andwewill" (concatenated body sentence). Strategy 1 already
    # accepts known keywords before this function is called, so any
    # single-word candidate reaching here is a false positive.
    if len(words) == 1:
        return False

    # Reject "Title Case density" check: a real section title is mostly
    # Title Case. A body sentence will have many lowercase-first words.
    # We require at most 1 non-Title-Case content word when the candidate
    # is longer than 3 words. This rejects:
    #   "The second approach creates a user feature vector it"
    # while keeping:
    #   "The Grandfather Paradox"          (3/3 = 100%)
    #   "The Consequences of Closed Timelike Curves"  (2/7 lowercase are
    #                                                    stopwords)
    if len(words) >= 3:
        allowed_lowercase = {
            "a", "an", "and", "or", "of", "for", "to", "in", "with",
            "on", "at", "by", "from", "as", "into", "than", "via",
            "the", "is", "vs", "vs.", "et", "al", "over", "under",
            "between", "among", "through",
        }
        non_compliant = 0
        for w in words[1:]:  # skip first word
            stripped_w = re.sub(r"[^a-zA-Z]", "", w)
            if not stripped_w:
                continue
            if stripped_w.lower() in allowed_lowercase:
                continue
            if not stripped_w[0].isupper():
                non_compliant += 1
        # If more than 1 non-Title-Case content word, treat as body sentence
        if non_compliant > 1:
            return False

    # If the original line is "## X" / "### X" we also accept short
    # lowercased fragments like "## references" -> "References".
    return True


def _detect_sections(text: str) -> list[Section]:
    """Detect academic sections by matching section headers (v2).

    Improvements over v1:
    1. Strip pdf_oxide markdown noise (bold/italic wrappers, "##" prefix)
       so we see the visible text.
    2. Reject front-matter lines: arXiv IDs, journal/copyright strings,
       single-name author lines, "Contents" headers.
    3. Reject body-sentence false positives: lines starting with "We",
       "This", "In", "However", "Let", etc.
    4. Cap section title length based on whether the original line had
       a structural prefix ("1.", "##", etc.).
    5. Drop the entire "Contents" section when it is followed by TOC
       entries ("1 Introduction 1", "2 Methods 5", ...).
    6. Skip the front-matter zone (everything before the first Abstract)
       so title/author block is never turned into a section.
    """
    lines = text.split("\n")
    section_starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Hard-reject noise: arXiv IDs, journal strings, etc.
        if _NON_SECTION_LINE_RE.match(stripped):
            continue

        # Hard-reject pure author block lines: "**Clifford M. Will**"
        if _AUTHOR_LINE_RE.match(stripped):
            continue

        # Hard-reject "Contents" — it is the TOC header, not a real section
        if _TOC_HEADER_RE.match(stripped):
            continue

        # Hard-reject TOC entries: "3.2 Title ............ 47" or bolded variants
        if _TOC_DOTTED_RE.match(stripped) or _TOC_DOTTED_BOLD_RE.match(stripped):
            continue

        # Strip pdf_oxide markdown noise for the actual matching
        visible = _strip_markdown_noise(line)
        if not visible:
            continue

        # Reject TOC entries after stripping noise: "3.2 Title ... 47"
        if _TOC_DOTTED_RE.match(visible.strip()):
            continue

        # Strategy 1: exact match against known headers (visible text)
        lower_visible = visible.lower().rstrip(".: \t")
        if lower_visible in _SECTION_HEADERS:
            section_starts.append((i, lower_visible.capitalize()))
            continue

        # Strategy 1b: inline front-matter headings such as
        # "Abstract. We present..." from Springer-style PDFs.
        inline_match = _INLINE_SECTION_RE.match(visible)
        if inline_match:
            section_starts.append((i, inline_match.group(1).capitalize()))
            continue

        # Strategy 2: numbered / formatted regex. The candidate must
        # have a structural prefix (numeric / roman / LaTeX / markdown
        # heading) AND pass title validation.
        m = _SECTION_RE.match(visible)
        if m:
            candidate = m.group(1).strip()
            prefix_match = re.match(
                r"^(?:\d+(?:\.\d+)*[\.\)]?\s+|[A-Z]+\.\s*|"
                r"\\section\{\s*|#{1,6}\s+)",
                visible,
            )
            has_prefix = bool(prefix_match)
            candidate_lower = candidate.lower().rstrip(".: \t")
            # Use word boundary check: a section header should match a
            # known keyword as a whole word, not as a substring
            # (otherwise "the previous results as follows" would match
            # "results" and "as follows" would match "follows" ... no,
            # "follows" isn't a keyword, but "results" is and that's
            # the bug we're fixing).
            keyword_hit = _has_section_keyword(candidate_lower)
            if keyword_hit:
                # Title contains a known academic keyword — accept directly.
                section_starts.append((i, candidate.capitalize()))
                continue
            if has_prefix and _is_valid_section_title(
                candidate, visible, has_explicit_prefix=True
            ):
                section_starts.append((i, candidate.capitalize()))
                continue

        # Strategy 3: markdown heading line "## Visible" without a numeric
        # prefix but with a heading marker. Only accept if the visible text
        # is a known keyword OR passes the strict title check.
        if stripped.startswith("#"):
            md_match = re.match(r"^#{1,6}\s+(.+)$", stripped)
            if md_match:
                candidate = md_match.group(1).strip()
                candidate_lower = candidate.lower().rstrip(".: \t")
                keyword_hit = _has_section_keyword(candidate_lower)
                if keyword_hit:
                    section_starts.append((i, candidate.capitalize()))
                    continue
                if _is_valid_section_title(
                    candidate, visible, has_explicit_prefix=True
                ):
                    section_starts.append((i, candidate.capitalize()))
                    continue

        # Strategy 4: all-caps headers (IEEE/ACM style) — e.g. "INTRODUCTION"
        if (
            len(visible) > 3
            and len(visible) < 60
            and _ALLCAPS_RE.match(visible)
        ):
            candidate = visible.lower().rstrip(".:")
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
                    "acknowledgment",
                    "acknowledgement",
                    "abstract",
                    "preliminary",
                    "conclusion",
                )
            ):
                section_starts.append((i, candidate.capitalize()))
                continue

    if not section_starts:
        return [Section(name="Full Text", start_line=0, end_line=len(lines) - 1)]

    # ── Front matter zone drop ─────────────────────────────────────────
    # Sections detected before the first Abstract are part of the
    # title/author/contents block, not real body sections. Drop them.
    abstract_idx = next(
        (idx for idx, (i, name) in enumerate(section_starts) if name == "Abstract"),
        None,
    )
    if abstract_idx is not None and abstract_idx > 0:
        section_starts = section_starts[abstract_idx:]
    elif abstract_idx is None:
        # No Abstract detected. Drop leading front matter sections:
        #   - sections whose text matches a known noise pattern
        #     ("Article in Press", "REVIEW ARTICLE", etc.)
        #   - leading H4 / H3 / H2 sections ("#### Title", "#### Author")
        while section_starts:
            first_start, first_name = section_starts[0]
            line_text = lines[first_start] if first_start < len(lines) else ""
            stripped = line_text.strip()
            looks_like_front_matter = False
            if _NON_SECTION_LINE_RE.match(stripped) or (
                stripped.startswith("####")
                or stripped.startswith("###")
                or stripped.startswith("## ")
            ):
                looks_like_front_matter = True
            if looks_like_front_matter:
                section_starts.pop(0)
            else:
                break

    if not section_starts:
        return [Section(name="Full Text", start_line=0, end_line=len(lines) - 1)]

    # ── Drop trailing noise sections ─────────────────────────────────
    # If a paper ends with one or more noise-only sections (e.g. a
    # stray "Manuscript" footer that pdf_oxide promoted to a heading),
    # they end up as the last section and produce tiny empty chunks.
    # Strip them.
    while section_starts:
        last_start, last_name = section_starts[-1]
        last_line = lines[last_start] if last_start < len(lines) else ""
        if _NON_SECTION_LINE_RE.match(last_line.strip()):
            section_starts.pop()
        else:
            break

    if not section_starts:
        return [Section(name="Full Text", start_line=0, end_line=len(lines) - 1)]

    # ── TOC drop ───────────────────────────────────────────────────────
    # If the section right after Abstract is "Contents" and the next
    # 1-3 lines look like TOC entries, drop the "Contents" section.
    if (
        len(section_starts) >= 2
        and section_starts[0][1] == "Abstract"
        and section_starts[1][1] in {"Contents", "Table of contents"}
    ):
        # Look ahead a few lines from the Contents section to see if it
        # is a real TOC.
        contents_start = section_starts[1][0]
        lookahead_end = min(contents_start + 20, len(lines))
        toc_window = "\n".join(lines[contents_start:lookahead_end])
        if _TOC_ENTRY_RE.search(toc_window) or "Contents" in toc_window[:50]:
            # Drop the Contents section so Abstract jumps to the real body
            section_starts.pop(1)

    if not section_starts:
        return [Section(name="Full Text", start_line=0, end_line=len(lines) - 1)]

    # ── Build Section objects ──────────────────────────────────────────
    sections: list[Section] = []
    for j, (start_idx, name) in enumerate(section_starts):
        end_idx = (
            section_starts[j + 1][0] - 1
            if j + 1 < len(section_starts)
            else len(lines) - 1
        )
        name = _clean_section_name(name)
        sections.append(Section(name=name, start_line=start_idx, end_line=end_idx))

    return sections


def _clean_section_name(name: str) -> str:
    """Sanitize a section name for storage and display.

    Steps:
    1. Strip leading structural prefixes that snuck through the regex
       ("I.", "1.", "1.1", "##", "**") so the name starts with the actual
       title word.
    2. Collapse internal whitespace (pdf_oxide sometimes inserts
       double spaces between bold runs).
    3. Strip a trailing period / colon.
    4. Cap at 8 words so the column in the UI doesn't overflow.
    """
    s = name.strip()
    # Drop leading markdown hashes
    s = re.sub(r"^#{1,6}\s*", "", s)
    # Drop leading bold markers that survived stripping
    s = re.sub(r"^\*+", "", s)
    # Drop leading numeric / roman / letter section numbers like "I.",
    # "1.", "1.1.", "A.", "II." — they are structural, not part of the title
    s = re.sub(
        r"^(?:\d+(?:\.\d+)*\.?\s+|[A-Z]+\.\s+|IV\.\s+)+",
        "",
        s,
    )
    # Collapse whitespace
    s = re.sub(r"\s{2,}", " ", s).strip()
    # Strip trailing punctuation
    s = s.rstrip(".:")
    # Cap at 8 words
    words = s.split()
    if len(words) > 8:
        s = " ".join(words[:8])
    return s or "Section"


# ── Stage 3: Chunking ──────────────────────────────────────────────────────


_MAX_CHUNK_CHARS = 2000  # ~500 tokens
_MIN_CHUNK_CHARS = 80  # chunks smaller than this are noise (page numbers, single words)

_IGNORE_SECTIONS = {"References", "Appendix", "Acknowledgments", "Acknowledgements"}

# Pattern for the start of a reference entry. Most BibTeX-style papers use
# "[1] Author, ..." or "1. Author, ...". AAS-style papers use
# "Author, A. B., others, (YEAR) Title...". We try the numbered form
# first, then fall back to AAS-style "Author (YEAR)" splitting.
_REFERENCE_ENTRY_RE = re.compile(
    r"(?m)(?=^\s*(?:\[\d+\]|\d{1,3}[.)]\s+)[A-Z])"
)
# AAS / MNRAS / ApJ style: entry begins with "Author," or "Author and"
# followed by "(YEAR)" anywhere on the line. We split just before such
# a line, but only when the previous line is "blank" (separating entries).
_REFERENCE_AAS_RE = re.compile(
    r"(?m)(?=^[A-Z][A-Za-z\.\-']+(?:[,\s]+[A-Z][A-Za-z\.\-']+){0,8}"
    r"(?:,\s*others|and\s+[A-Z][A-Za-z\.\-']+)*"
    r"\s*\(\d{4}\))"
)


def _chunk_references(section_text: str) -> list[str]:
    """Split a References section into per-entry chunks.

    Tries three strategies in order:
    1. Numbered entries: "[1] Author..." or "1. Author..."
    2. AAS-style: "Author, A.B., others, (YEAR) Title..."
    3. Paragraph-level split (last resort, when the section is a single
       paragraph because pdf_oxide merged all entries).
    """
    entries = _REFERENCE_ENTRY_RE.split(section_text)
    entries = [e.strip() for e in entries if e.strip() and len(e.strip()) >= _MIN_CHUNK_CHARS]
    # If numbered split gave us ONE giant block, try AAS-style
    if len(entries) <= 1 and len(section_text) > _MAX_CHUNK_CHARS * 2:
        aas_entries = _REFERENCE_AAS_RE.split(section_text)
        aas_entries = [
            e.strip() for e in aas_entries if e.strip() and len(e.strip()) >= _MIN_CHUNK_CHARS
        ]
        if len(aas_entries) > 1:
            entries = aas_entries
    # Last resort: paragraph splitting for any remaining oversized section
    final: list[str] = []
    for entry in entries:
        if len(entry) > _MAX_CHUNK_CHARS:
            final.extend(_split_by_paragraphs(entry, _MAX_CHUNK_CHARS))
        else:
            final.append(entry)
    return final


def _split_by_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split *text* by blank lines, joining adjacent paragraphs to stay
    under *max_chars*. Always returns at least one chunk.
    """
    paragraphs = re.split(r"\n\s*\n", text)
    out: list[str] = []
    current = ""
    for para in paragraphs:
        if not para.strip():
            continue
        if len(current) + len(para) < max_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                out.append(current)
            # If a single paragraph is itself longer than max_chars, hard-split
            if len(para) > max_chars:
                for i in range(0, len(para), max_chars):
                    piece = para[i : i + max_chars]
                    if piece.strip():
                        out.append(piece)
                current = ""
            else:
                current = para
    if current:
        out.append(current)
    return out


def _chunk_sections(text: str, sections: list[Section]) -> list[Chunk]:
    """Split document into chunks, one per section (or split large ones)."""
    lines = text.split("\n")
    chunks: list[Chunk] = []

    for section in sections:
        section_text = "\n".join(lines[section.start_line : section.end_line + 1])
        if not section_text.strip():
            continue

        if section.name == "References":
            # Split by entry to avoid one giant chunk for the bibliography.
            for entry in _chunk_references(section_text):
                chunks.append(
                    Chunk(
                        text=entry,
                        chunk_type="full_text",
                        section_label=section.name,
                    )
                )
            continue

        if section.name in _IGNORE_SECTIONS:
            # Appendices, acknowledgments: keep as one section, but still
            # split if oversized.
            pieces = (
                [section_text]
                if len(section_text) <= _MAX_CHUNK_CHARS
                else _split_by_paragraphs(section_text, _MAX_CHUNK_CHARS)
            )
            for piece in pieces:
                if piece.strip() and len(piece.strip()) >= _MIN_CHUNK_CHARS:
                    chunks.append(
                        Chunk(
                            text=piece,
                            chunk_type="full_text",
                            section_label=section.name,
                        )
                    )
            continue

        if len(section_text) <= _MAX_CHUNK_CHARS:
            if section_text.strip() and len(section_text.strip()) >= _MIN_CHUNK_CHARS:
                chunks.append(
                    Chunk(
                        text=section_text,
                        chunk_type="full_text",
                        section_label=section.name,
                    )
                )
        else:
            for piece in _split_by_paragraphs(section_text, _MAX_CHUNK_CHARS):
                if piece.strip() and len(piece.strip()) >= _MIN_CHUNK_CHARS:
                    chunks.append(
                        Chunk(
                            text=piece,
                            chunk_type="full_text",
                            section_label=section.name,
                        )
                    )

    # If everything got filtered, return a single Full Text chunk so
    # the paper is still searchable.
    if not chunks and text.strip():
        chunks.append(Chunk(text=text.strip(), chunk_type="full_text", section_label="Full Text"))

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
