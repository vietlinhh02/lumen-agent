"""5-signal quality scorer for PDF extraction backends.

Replaces the 2-signal heuristic in :mod:`app.services.pdf_fulltext`
(sections + boilerplate penalty) with a 5-signal audit derived from the
pdfmux self-healing pipeline formula (2026):

    confidence = (
        0.30 * text_density_score(text, page_area)    # chars/cm²
        + 0.25 * alphabetic_ratio(text)               # letters / total
        + 0.20 * structure_coherence(text)            # paragraph breaks, sentences
        + 0.15 * mojibake_score(text)                 # UTF-8 corruption detection
        + 0.10 * column_order_score(text)             # No interleaved columns
    )

Why five signals and not one (e.g. "looks like English"): each one captures
a distinct failure mode of the rule-based pipeline documented in
``docs/architecture/pdf-extraction-roadmap.md``:

- low density            → image-only page returned as empty text
- low alphabetic ratio   → mostly math / symbols / extraction noise
- low structure coherence → line soup, no paragraphs, no sentence terminators
- mojibake hits          → double-encoded UTF-8 from non-PDF text layer
- column interleave      → 2-column paper read across columns instead of down

We deliberately score on plain text (not page images) so the scorer can be
applied to *any* backend that returns text — pdf_oxide, pypdf, Docling,
Nougat, or a future OCR layer. Per-page scoring is supported via
:func:`score_pages` once a backend exposes page boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Weights ───────────────────────────────────────────────────────────────
# Sum to 1.0. Tuned to match pdfmux 2026 default; keep them explicit so a
# future tuning pass can A/B against this baseline without code archaeology.
_W_DENSITY = 0.30
_W_ALPHA = 0.25
_W_STRUCTURE = 0.20
_W_MOJIBAKE = 0.15
_W_COLUMN = 0.10

# Confidence threshold below which an extraction is considered weak and
# triggers a fallback engine. 0.85 mirrors the value used in
# ``pdf_fulltext.extract_text`` for the pdf_oxide-vs-pypdf switch.
DEFAULT_MIN_SCORE = 0.60
GOOD_SCORE = 0.85


# ── Public dataclasses ───────────────────────────────────────────────────


@dataclass(frozen=True)
class PageMetrics:
    """Per-page quality metrics. Aggregated into :class:`ExtractionQuality`."""

    page_number: int
    char_count: int
    density: float          # 0..1, chars-per-cm² proxy at page level
    alpha_ratio: float      # 0..1, letters / non-whitespace
    structure: float        # 0..1, paragraph + sentence coherence
    mojibake: float         # 1.0 = clean, 0.0 = unreadable
    column_order: float     # 1.0 = clean reading order, 0.0 = interleaved


@dataclass(frozen=True)
class ExtractionQuality:
    """Aggregate quality score for a full extraction."""

    density: float
    alpha_ratio: float
    structure: float
    mojibake: float
    column_order: float
    score: float          # weighted composite in [0, 1]
    char_count: int

    @property
    def is_good(self) -> bool:
        """True when the composite score clears the GOOD_SCORE bar."""
        return self.score >= GOOD_SCORE

    @property
    def weakest_signal(self) -> str:
        """Name of the lowest signal — the most actionable failure indicator."""
        signals = {
            "density": self.density,
            "alpha_ratio": self.alpha_ratio,
            "structure": self.structure,
            "mojibake": self.mojibake,
            "column_order": self.column_order,
        }
        return min(signals, key=signals.get)


# ── Signal helpers ───────────────────────────────────────────────────────


# Common mojibake signatures. Double-encoded UTF-8 (UTF-8 bytes interpreted
# as Latin-1 then re-encoded) produces these characteristic 2- and 3-byte
# sequences. We keep the table small and high-precision — false positives
# here are worse than misses because they push clean papers into the
# fallback path unnecessarily.
_MOJIBAKE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Replacement character / U+FFFD
    re.compile(r"\ufffd"),
    # Latin-1→UTF-8 reinterpretation of common Western characters
    re.compile(r"[ÃÂ][\u0080-\u00bf©®™±°·÷×¤¦¨ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿]"),
    # Smart quote / em-dash garble
    re.compile(r"â€[™œŸ¦""]"),
    # CJK / Cyrillic double-encoded fragments
    re.compile(r"Â[ ¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹]"),
)


def _alphabetic_ratio(text: str) -> float:
    """Fraction of non-whitespace characters that are ASCII letters.

    Pure math notation or extraction garbage scores low; normal English
    prose scores ~0.7-0.85. We use ASCII letters rather than the broader
    Unicode ``isalpha`` because pdf_oxide emits Greek/math as Unicode
    symbols we treat separately via the structure signal.
    """
    if not text:
        return 0.0
    significant = [c for c in text if not c.isspace()]
    if not significant:
        return 0.0
    letters = sum(1 for c in significant if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    return letters / len(significant)


def _structure_coherence(text: str) -> float:
    """Score how well-formed the text looks as paragraphs and sentences.

    Combines three sub-signals:
    - paragraph presence (blank lines separating blocks)
    - sentence terminators (period/!/? followed by space or newline)
    - line-length sanity (not all one-word lines, not all 500-char walls)
    """
    if not text:
        return 0.0
    lines = text.split("\n")
    if not lines:
        return 0.0

    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return 0.0

    # Paragraph presence: ratio of blank lines to total lines, capped at 0.2.
    # A well-extracted academic paper has blank-line density around 0.10-0.20.
    blank_ratio = (len(lines) - len(nonempty)) / len(lines)
    paragraph_score = min(blank_ratio / 0.15, 1.0)

    # Sentence terminators: roughly one per ~80 chars of prose.
    # We reward reaching that density, penalise both extremes.
    char_count = sum(len(line) for line in nonempty)
    if char_count < 200:
        sentence_score = 0.4  # too short to judge, don't punish
    else:
        terminators = sum(
            1
            for line in nonempty
            for match in re.finditer(r"[.!?](?:\s|$)", line)
        )
        density = terminators / (char_count / 80.0)
        # 1.0 terminators-per-80-chars = ideal, both directions decay
        sentence_score = max(0.0, 1.0 - abs(1.0 - density) * 0.6)

    # Line-length sanity: penalise documents where most lines are <20 chars
    # (column interleave / fragments) or all single-line walls.
    line_lengths = [len(line) for line in nonempty]
    short_ratio = sum(1 for ln in line_lengths if ln < 20) / len(line_lengths)
    long_ratio = sum(1 for ln in line_lengths if ln > 400) / len(line_lengths)
    if short_ratio > 0.5:
        line_score = 0.3
    elif long_ratio > 0.6:
        line_score = 0.5
    else:
        line_score = 1.0

    # Weighted blend — sentence and paragraph presence matter most.
    return 0.45 * sentence_score + 0.35 * paragraph_score + 0.20 * line_score


def _mojibake_score(text: str) -> float:
    """Score 1.0 = clean, 0.0 = unreadable.

    Counts the fraction of characters that fall inside a known mojibake
    pattern. We deliberately do NOT normalise via NFKD before scanning:
    NFKD decomposes "Ã" (U+00C3 = "A with tilde") into "A" + a combining
    tilde, which destroys the very byte sequences we are looking for.
    The patterns below are written to match the raw UTF-8-as-Latin-1
    characters as they appear in corrupted text.
    """
    if not text:
        return 0.0
    hit_chars = sum(
        len(m.group(0)) for pattern in _MOJIBAKE_PATTERNS for m in pattern.finditer(text)
    )
    if hit_chars == 0:
        return 1.0
    # Map hit density to a 0..1 score. >2% mojibake = essentially unreadable.
    density = hit_chars / max(len(text), 1)
    return max(0.0, 1.0 - density * 50.0)


def _density_score(text: str) -> float:
    """Score extraction density from line-level statistics.

    A well-extracted PDF has enough text to be readable: a few hundred
    characters and several non-empty lines. We don't try to grade
    "ideal" density because real PDFs vary widely (single-column
    physics paper vs dense table-heavy supplement). Instead we treat
    density as a *health check* that only fails on clear extraction
    failures: image-only pages, fragment soup, or a single wall of
    text with no structure.

    Three sub-checks, all three must pass for a full score:
    - char_count < 200          → likely empty / image-only
    - non-empty line count < 4  → too sparse to be useful
    - average line length < 10   → fragmented
    """
    if not text:
        return 0.0
    if len(text) < 200:
        return 0.2

    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < 4:
        return 0.3

    avg_chars = sum(len(line) for line in lines) / len(lines)
    if avg_chars < 10:
        return 0.4
    return 1.0
    # as a clear extraction failure (image-only or wall-of-text artefact).
    if avg_chars < 15 or avg_chars > 350:
        return 0.1
    diff = abs(avg_chars - 75) / 75.0
    return max(0.0, 1.0 - diff)


def _column_order_score(text: str) -> float:
    """Score reading-order cleanliness.

    Heuristic: an interleaved two-column extraction yields many *very*
    short lines (<30 chars) that alternate between citation-style endings
    ("(2020)", "et al.") and citation-style openings ("Smith, J.").
    We score 1.0 for clean reading order, drop toward 0.0 as the
    interleaving signal strengthens.

    The threshold is intentionally low (30 chars, not 60) because normal
    academic text often runs at 50-80 chars per line; flagging at 60
    produces too many false positives on real single-column papers.
    """
    if not text:
        return 0.0
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) < 4:
        # Too few lines to make a judgement — assume clean reading order.
        return 1.0

    # Very-short lines (<30 chars) are the true interleaving signal —
    # typical academic prose rarely goes below this even in 2-column layout.
    very_short = [line for line in lines if len(line) < 30]
    very_short_ratio = len(very_short) / len(lines)

    # Count "citation-y" tokens: lines that look like the tail of a
    # bibliographic reference or in-text citation.
    citation_end_re = re.compile(
        r"(?:\(\d{4}\)|\[\d+\]|et al\.?|\b\d{4}\b\s*[.,;:]?\s*$)"
    )
    citation_starts = sum(
        1
        for line in lines
        if re.match(r"^[A-Z][a-z]+(?:[,\s]+[A-Z][a-z]+){0,3}\s*[,.]", line)
    )
    citation_ends = sum(1 for line in lines if citation_end_re.search(line))
    citation_density = (citation_starts + citation_ends) / len(lines)

    # Strong interleave signature: many very-short lines + many citation tokens.
    if very_short_ratio > 0.5 and citation_density > 0.3:
        return 0.2
    if very_short_ratio > 0.35:
        return 0.5
    return 1.0


# ── Public API ──────────────────────────────────────────────────────────


def score_quality(text: str | None) -> ExtractionQuality:
    """Compute the 5-signal quality score for a string of extracted text.

    Returns a zero-quality result when *text* is ``None`` or empty so callers
    can branch on ``score > 0`` without a separate None check.
    """
    if not text:
        return ExtractionQuality(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
    char_count = len(text)

    density = _density_score(text)
    alpha = _alphabetic_ratio(text)
    structure = _structure_coherence(text)
    mojibake = _mojibake_score(text)
    column = _column_order_score(text)

    composite = (
        _W_DENSITY * density
        + _W_ALPHA * alpha
        + _W_STRUCTURE * structure
        + _W_MOJIBAKE * mojibake
        + _W_COLUMN * column
    )
    return ExtractionQuality(
        density=density,
        alpha_ratio=alpha,
        structure=structure,
        mojibake=mojibake,
        column_order=column,
        score=composite,
        char_count=char_count,
    )


def score_pages(page_texts: list[str]) -> list[PageMetrics]:
    """Compute per-page metrics for a list of page strings.

    Per-page scoring lets us identify the worst pages in a document so a
    self-healing pipeline can re-extract only those pages with a stronger
    backend. The aggregate document-level score should be obtained from
    :func:`score_quality` over the concatenated text.
    """
    metrics: list[PageMetrics] = []
    for index, page_text in enumerate(page_texts, start=1):
        quality = score_quality(page_text)
        metrics.append(
            PageMetrics(
                page_number=index,
                char_count=quality.char_count,
                density=quality.density,
                alpha_ratio=quality.alpha_ratio,
                structure=quality.structure,
                mojibake=quality.mojibake,
                column_order=quality.column_order,
            )
        )
    return metrics


__all__ = [
    "DEFAULT_MIN_SCORE",
    "ExtractionQuality",
    "GOOD_SCORE",
    "PageMetrics",
    "score_pages",
    "score_quality",
]