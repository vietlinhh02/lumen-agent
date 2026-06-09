"""Batch PDF text normalization and evidence chunking.

Takes raw extracted PDF text (from ``PaperEnrichment.raw_text``), sends it
to the configured LLM for a readable markdown view, then chunks and embeds the
raw evidence text. Raw text remains the retrieval source so cleaning cannot
drop details needed for citation-safe RAG.

Triggered automatically when a project has ≥3 papers with
``full_text_status = 'raw_extracted'``.
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    PDF_NORMALIZE_SYSTEM,
    PDF_NORMALIZE_USER,
    PDF_STRUCTURE_SYSTEM,
    PDF_STRUCTURE_USER,
)
from app.ai.provider import get_provider
from app.db.models import Paper, PaperChunk, PaperEnrichment, ProjectPaper
from app.services.pdf_ingestion import Section, _detect_sections

logger = logging.getLogger(__name__)

# ── Token-aware constants ────────────────────────────────────────────────────
# Approximate ratio: 1 token ≈ 4 characters for English academic text.
# Embedding models work in token space, so all limits are defined in tokens.
_TOKEN_RATIO = 4

# Section-specific token budgets (based on 2026 research benchmarks)
_ABSTRACT_MAX_TOKENS = 300
_INTRODUCTION_MAX_TOKENS = 350
_METHOD_MAX_TOKENS = 400
_RESULTS_MAX_TOKENS = 400
_NARRATIVE_MAX_TOKENS = 450
_LIMITATION_MAX_TOKENS = 300
_REFERENCE_MAX_TOKENS = 500
_DEFAULT_MAX_TOKENS = 400

_OVERLAP_TOKENS = 40  # ~10% of default chunk size
_MIN_CHUNK_WORDS = 5  # minimum words to keep a chunk

_LLM_CONTEXT_MAX_CHARS = 50000
_PIPEINE_VERSION = "paper-tree-v2"
_STRUCTURE_LINES_PER_BATCH = 220
_MAX_HEADING_LENGTH = 120
_MIN_ACCEPTABLE_SECTION_SCORE = 0.55
_MIN_LLM_ADVANTAGE = 0.08
_CORE_SECTION_KEYWORDS = (
    "abstract",
    "introduction",
    "related",
    "method",
    "experiment",
    "result",
    "discussion",
    "conclusion",
    "reference",
    "appendix",
)

_PDF_STRUCTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "headings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_index": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["line_index", "title"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["headings"],
    "additionalProperties": False,
}


def _approx_tokens(text: str) -> int:
    """Approximate token count from character count (1 token ≈ 4 chars)."""
    return len(text) // _TOKEN_RATIO


def _tokens_to_chars(tokens: int) -> int:
    """Convert token count to approximate character count."""
    return tokens * _TOKEN_RATIO


@dataclass(frozen=True)
class ChunkPolicy:
    """Chunking policy selected from an academic section label.

    All size limits are in tokens for embedding-model alignment.
    """

    max_tokens: int
    overlap_tokens: int
    content_type: str
    embed: bool = True

    @property
    def max_chars(self) -> int:
        return _tokens_to_chars(self.max_tokens)

    @property
    def overlap_chars(self) -> int:
        return _tokens_to_chars(self.overlap_tokens)


async def count_raw_papers(db: AsyncSession, project_id: UUID) -> int:
    """Return how many papers in the project have raw text waiting."""
    result = await db.execute(
        select(ProjectPaper).where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.full_text_status == "raw_extracted",
        )
    )
    return len(result.scalars().all())


async def normalize_project_papers(
    db: AsyncSession,
    project_id: UUID,
) -> dict:
    """Batch-normalise all papers with ``raw_extracted`` status.

    Returns a summary dict with counts of processed / skipped / failed.
    """
    provider = get_provider()

    # Load papers needing normalization
    result = await db.execute(
        select(ProjectPaper, Paper, PaperEnrichment)
        .join(Paper, ProjectPaper.paper_id == Paper.id)
        .outerjoin(
            PaperEnrichment,
            PaperEnrichment.project_paper_id == ProjectPaper.id,
        )
        .where(
            ProjectPaper.project_id == project_id,
            ProjectPaper.full_text_status == "raw_extracted",
        )
    )
    rows = result.all()

    if not rows:
        return {"processed": 0, "skipped": 0, "failed": 0}

    processed = 0
    skipped = 0
    failed = 0

    for pp, paper, enrichment in rows:
        if not enrichment or not enrichment.raw_text:
            skipped += 1
            continue

        raw_text = enrichment.raw_text.strip()

        try:
            # 1. LLM normalize only for a readable markdown view. Do not use it
            # as the evidence source because the model may omit details.
            normalized = await _normalize_text(provider, paper.title, _llm_context(raw_text))
            if normalized:
                enrichment.crawled_markdown = normalized

            # 2. Use the LLM as a structure parser over numbered raw lines.
            sections = await _detect_sections_with_llm(provider, paper.title, raw_text)

            # 3. Chunk raw text using section boundaries and token-aware size guards.
            chunks = _chunk_raw_evidence(raw_text, sections)
            if not chunks:
                skipped += 1
                continue

            # 4. Embed contextualized text, but store only raw chunk text.
            embed_indices = [i for i, chunk in enumerate(chunks) if chunk.get("embed", True)]
            texts = [_embedding_text(paper.title, chunks[i]) for i in embed_indices]
            try:
                from app.core.embeddings import (
                    encode_batch,
                    get_embedding_dimension,
                    get_embedding_model_name,
                )

                if texts:
                    embeddings = encode_batch(texts)
                    for i, emb in zip(embed_indices, embeddings, strict=True):
                        chunks[i]["embedding"] = emb
                        chunks[i]["embedding_model"] = get_embedding_model_name()
                        chunks[i]["embedding_dimension"] = get_embedding_dimension()
            except ImportError as exc:
                raise RuntimeError(
                    "Embedding dependency is missing. Run `uv sync` to install."
                ) from exc

            # 5. Store
            await _store_chunks(db, pp.id, chunks)
            await _update_status(db, pp.id, "completed")
            processed += 1
            logger.info("Normalized: %s (%d chunks)", paper.title[:60], len(chunks))

        except Exception as exc:
            logger.exception("Normalization failed for %s: %s", paper.title[:60], exc)
            with suppress(Exception):
                await db.rollback()
            await _update_status(db, pp.id, "failed")
            failed += 1

    return {"processed": processed, "skipped": skipped, "failed": failed}


# ── LLM Normalization ────────────────────────────────────────────────────


async def _normalize_text(
    provider,
    title: str,
    raw_text: str,
) -> str | None:
    """Send raw PDF text to LLM and get back clean markdown sections."""
    user_msg = PDF_NORMALIZE_USER.format(title=title, raw_text=raw_text)
    try:
        result = await provider.complete(
            messages=[{"role": "user", "content": user_msg}],
            system=PDF_NORMALIZE_SYSTEM,
            max_tokens=16000,
        )
        if not result:
            return None
        # Strip code fences if the model wraps in markdown
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n```$", "", cleaned)
        return cleaned.strip()
    except Exception as exc:
        logger.warning("LLM normalization failed: %s", exc)
        return None


async def _detect_sections_with_llm(provider, title: str, raw_text: str) -> list[Section]:
    """Detect section boundaries with an LLM, falling back to regex heuristics."""
    lines = raw_text.split("\n")
    headings: list[tuple[int, str]] = []

    for start in range(0, len(lines), _STRUCTURE_LINES_PER_BATCH):
        batch_lines = lines[start : start + _STRUCTURE_LINES_PER_BATCH]
        numbered_lines = _format_numbered_lines(batch_lines, start)
        try:
            result = await provider.complete_structured(
                messages=[
                    {
                        "role": "user",
                        "content": PDF_STRUCTURE_USER.format(
                            title=title,
                            line_offset=start,
                            numbered_lines=numbered_lines,
                        ),
                    }
                ],
                schema=_PDF_STRUCTURE_SCHEMA,
                tool_name="paper_structure",
                system=PDF_STRUCTURE_SYSTEM,
                max_tokens=2048,
            )
        except Exception as exc:
            logger.warning("LLM section parsing failed for batch %d: %s", start, exc)
            return _detect_sections(raw_text)

        headings.extend(_valid_headings(result, lines, start, len(batch_lines)))

    fallback_sections = _detect_sections(raw_text)
    llm_sections = _sections_from_headings(lines, headings)
    llm_score = _section_quality_score(llm_sections)
    fallback_score = _section_quality_score(fallback_sections)
    if llm_score < _MIN_ACCEPTABLE_SECTION_SCORE:
        return fallback_sections
    if llm_score < fallback_score + _MIN_LLM_ADVANTAGE:
        return fallback_sections
    return llm_sections


def _format_numbered_lines(lines: list[str], offset: int) -> str:
    """Return compact line-numbered text for LLM structure parsing."""
    formatted: list[str] = []
    for index, line in enumerate(lines, start=offset):
        stripped = line.strip()
        if stripped:
            formatted.append(f"{index}: {stripped[:500]}")
    return "\n".join(formatted)


def _valid_headings(
    result: dict,
    lines: list[str],
    batch_start: int,
    batch_len: int,
) -> list[tuple[int, str]]:
    """Validate LLM heading candidates against raw lines."""
    raw_headings = result.get("headings", [])
    if not isinstance(raw_headings, list):
        return []

    headings: list[tuple[int, str]] = []
    batch_end = batch_start + batch_len
    for item in raw_headings:
        if not isinstance(item, dict):
            continue
        line_index = item.get("line_index")
        title = item.get("title")
        if not isinstance(line_index, int) or not isinstance(title, str):
            continue
        if line_index < batch_start or line_index >= batch_end or line_index >= len(lines):
            continue
        title = _clean_heading_title(title)
        if not title or _is_rejected_heading(lines[line_index], title):
            continue
        headings.append((line_index, title))
    return headings


def _clean_heading_title(title: str) -> str:
    """Normalize a heading title returned by the LLM."""
    title = re.sub(r"^\d+(?:\.\d+)*[\.\)]?\s+", "", title.strip())
    title = title.strip(" #:\t")
    if len(title) > _MAX_HEADING_LENGTH:
        return ""
    return title[:1].upper() + title[1:] if title else ""


def _is_rejected_heading(raw_line: str, title: str) -> bool:
    """Return whether a heading candidate is PDF noise."""
    line = raw_line.strip()
    lower = line.lower()
    title_lower = title.lower()
    if "@" in line:
        return True
    if "copyright" in lower or "creative commons" in lower or "ceur-ws" in lower:
        return True
    if title_lower in {"and", "the", "for", "of"}:
        return True
    if re.fullmatch(r"(?:[A-Z]\s+){2,}[A-Z]", line):
        return True
    return title_lower.startswith(("table ", "fig. ", "figure "))


def _sections_from_headings(
    lines: list[str],
    headings: list[tuple[int, str]],
) -> list[Section]:
    """Build sections from validated heading starts."""
    unique: dict[int, str] = {}
    for line_index, title in sorted(headings, key=lambda item: item[0]):
        unique.setdefault(line_index, title)
    heading_items = list(unique.items())
    if not heading_items:
        return [Section(name="Full Text", start_line=0, end_line=len(lines) - 1)]

    sections: list[Section] = []
    for i, (start, title) in enumerate(heading_items):
        end = heading_items[i + 1][0] - 1 if i + 1 < len(heading_items) else len(lines) - 1
        if start <= end:
            sections.append(Section(name=title, start_line=start, end_line=end))
    return sections


def _section_quality_score(sections: list[Section]) -> float:
    """Estimate whether LLM-detected sections look credible enough to trust."""
    if len(sections) < 2:
        return 0.0

    valid = 0
    noisy = 0
    for section in sections:
        title = section.name.strip()
        lower = title.lower()
        token_count = len(re.findall(r"[A-Za-z0-9]+", title))
        if token_count <= 1 and lower not in _CORE_SECTION_KEYWORDS:
            noisy += 1
            continue
        if any(keyword in lower for keyword in _CORE_SECTION_KEYWORDS):
            valid += 2
            continue
        if re.search(r"\b(i|ii|iii|iv|v)\b", lower) and len(title.split()) > 8:
            noisy += 1
            continue
        if len(title) > 80 or re.search(r"\b[a-z] [A-Z]\b", title):
            noisy += 1
            continue
        valid += 1

    return valid / max(valid + noisy, 1)


def _chunk_raw_evidence(
    text: str,
    sections: list[Section],
) -> list[dict]:
    """Split raw paper text into section-aware evidence chunks.

    Each chunk carries a ``section_path`` reflecting its position in the
    document hierarchy, which is prepended to the chunk text during
    embedding for richer retrieval context.
    """
    lines = text.split("\n")
    chunks: list[dict] = []
    chunk_index = 0
    parent_heading = ""

    for section in sections:
        section_lines = lines[section.start_line : section.end_line + 1]
        section_text = "\n".join(_clean_section_lines(section_lines)).strip()
        if not section_text:
            continue

        # Track parent heading for hierarchy context
        parent_heading = _update_parent_heading(parent_heading, section.name)

        policy = _policy_for_section(section.name)
        for content_type, chunk_text in _split_section_by_content(section_text, policy):
            if _is_low_value_chunk(chunk_text, content_type):
                continue
            chunk_index += 1
            chunks.append(
                _build_chunk(
                    section.name,
                    parent_heading,
                    chunk_index,
                    content_type,
                    chunk_text,
                    policy,
                )
            )

    return chunks


def _update_parent_heading(current: str, new_heading: str) -> str:
    """Maintain a 2-level parent heading context (e.g. 'Method > Training')."""
    if not new_heading:
        return current
    new_lower = new_heading.lower()
    # Top-level headings reset the context
    if not any(kw in new_lower for kw in (".", "sub", "part")):
        return new_heading
    # Subsections: keep parent if it's a top-level heading
    if current and "." not in current.lower():
        return f"{current} > {new_heading}"
    return new_heading


def _policy_for_section(section_name: str) -> ChunkPolicy:
    """Select an adaptive token-aware chunk policy for a paper section."""
    name = section_name.lower()
    if "abstract" in name:
        return ChunkPolicy(
            max_tokens=_ABSTRACT_MAX_TOKENS, overlap_tokens=0, content_type="abstract"
        )
    if "reference" in name or "bibliography" in name:
        return ChunkPolicy(
            max_tokens=_REFERENCE_MAX_TOKENS,
            overlap_tokens=0,
            content_type="reference",
            embed=False,
        )
    if "limitation" in name or "future work" in name:
        return ChunkPolicy(
            max_tokens=_LIMITATION_MAX_TOKENS,
            overlap_tokens=_OVERLAP_TOKENS,
            content_type="limitation",
        )
    if any(keyword in name for keyword in ("method", "approach", "framework", "system design")):
        return ChunkPolicy(
            max_tokens=_METHOD_MAX_TOKENS, overlap_tokens=_OVERLAP_TOKENS, content_type="method"
        )
    if any(keyword in name for keyword in ("experiment", "result", "evaluation", "discussion")):
        return ChunkPolicy(
            max_tokens=_RESULTS_MAX_TOKENS, overlap_tokens=_OVERLAP_TOKENS, content_type="results"
        )
    if any(keyword in name for keyword in ("related", "literature review", "background")):
        return ChunkPolicy(
            max_tokens=_NARRATIVE_MAX_TOKENS,
            overlap_tokens=_OVERLAP_TOKENS,
            content_type="narrative",
        )
    if "introduction" in name:
        return ChunkPolicy(
            max_tokens=_INTRODUCTION_MAX_TOKENS,
            overlap_tokens=_OVERLAP_TOKENS,
            content_type="narrative",
        )
    return ChunkPolicy(
        max_tokens=_DEFAULT_MAX_TOKENS,
        overlap_tokens=_OVERLAP_TOKENS,
        content_type="narrative",
    )


def _split_section_by_content(
    section_text: str,
    policy: ChunkPolicy,
) -> list[tuple[str, str]]:
    """Split a section into typed evidence chunks."""
    if policy.content_type == "reference":
        return [("reference", chunk) for chunk in _split_section_text(section_text, policy)]

    extracted: list[tuple[str, str]] = []
    narrative_lines: list[str] = []
    table_lines: list[str] = []

    for line in section_text.split("\n"):
        stripped = line.strip()
        if _looks_like_table_line(stripped):
            _flush_narrative(narrative_lines, policy, extracted)
            table_lines.append(stripped)
            continue
        if _looks_like_figure_caption(stripped):
            _flush_narrative(narrative_lines, policy, extracted)
            if table_lines:
                _flush_table(table_lines, extracted)
            extracted.append(("figure_caption", stripped))
            continue
        narrative_lines.append(line)

    if table_lines:
        _flush_table(table_lines, extracted)
    _flush_narrative(narrative_lines, policy, extracted)
    return extracted


def _flush_narrative(
    lines: list[str],
    policy: ChunkPolicy,
    chunks: list[tuple[str, str]],
) -> None:
    """Flush accumulated narrative lines into adaptive chunks."""
    text = "\n".join(lines).strip()
    lines.clear()
    if not text:
        return
    for chunk_text in _split_section_text(text, policy):
        chunks.append((policy.content_type, chunk_text))


_TABLE_GROUP_MIN_CHARS = 30


def _flush_table(
    lines: list[str],
    chunks: list[tuple[str, str]],
) -> None:
    """Merge consecutive table lines into one chunk, skipping bare headers."""
    text = "\n".join(lines).strip()
    lines.clear()
    if not text or len(text) < _TABLE_GROUP_MIN_CHARS:
        return
    chunks.append(("table", text))


def _looks_like_table_line(line: str) -> bool:
    """Return whether a line likely belongs to a table."""
    if not line:
        return False
    if re.fullmatch(r"(?:table|tab\.)\s+\d+\.?", line, flags=re.IGNORECASE):
        return False
    lower = line.lower()
    if lower.startswith(("table ", "tab. ")):
        return True
    separators = line.count("|") + line.count("\t")
    digit_ratio = sum(char.isdigit() for char in line) / max(len(line), 1)
    return separators >= 2 or (digit_ratio > 0.25 and len(line.split()) >= 4)


def _looks_like_figure_caption(line: str) -> bool:
    """Return whether a line likely starts a figure caption."""
    lower = line.lower()
    return lower.startswith(("figure ", "fig. ", "fig "))


def _clean_section_lines(lines: list[str]) -> list[str]:
    """Remove PDF boilerplate lines that should not become evidence chunks."""
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            cleaned.append(line)
            continue
        if "@" in stripped:
            continue
        if "ceur-ws.org" in lower or "ceur workshop proceedings" in lower:
            continue
        if "creative commons" in lower or "copyright" in lower:
            continue
        if re.fullmatch(r"(?:[A-Z]\s+){2,}[A-Z]", stripped):
            continue
        if "w pr o o r c k e s e h" in lower:
            continue
        cleaned.append(line)
    return cleaned


def _is_low_value_chunk(chunk_text: str, content_type: str) -> bool:
    """Return whether a chunk has too little evidence value to store."""
    words = re.findall(r"[A-Za-z0-9]+", chunk_text)
    word_count = len(words)
    if content_type == "table":
        return word_count < 10
    if content_type == "figure_caption":
        return word_count < 5
    if content_type == "reference":
        return word_count < 3
    return word_count < _MIN_CHUNK_WORDS


def _build_chunk(
    section_name: str,
    parent_heading: str,
    chunk_index: int,
    content_type: str,
    chunk_text: str,
    policy: ChunkPolicy,
) -> dict:
    """Build a chunk record with deterministic metadata.

    ``section_path`` stores the hierarchy (e.g. "Method > Training") for
    metadata display. The raw ``chunk_text`` is stored as-is; the parent
    heading context is only added during embedding via ``_embedding_text``.
    """
    embed = policy.embed and content_type != "reference"
    section_path = parent_heading if parent_heading else section_name
    return {
        "text": chunk_text,
        "section_label": section_name,
        "section_path": section_path,
        "chunk_index": chunk_index,
        "chunk_type": "full_text",
        "content_type": content_type,
        "pipeline_version": _PIPEINE_VERSION,
        "content_hash": sha256(chunk_text.encode("utf-8")).hexdigest(),
        "embed": embed,
    }


def _split_section_text(section_text: str, policy: ChunkPolicy | None = None) -> list[str]:
    """Split a section while preserving paragraph and sentence boundaries.

    Uses token-aware size limits instead of character counts.
    """
    policy = policy or ChunkPolicy(
        max_tokens=_DEFAULT_MAX_TOKENS,
        overlap_tokens=_OVERLAP_TOKENS,
        content_type="narrative",
    )
    max_chars = policy.max_chars
    if len(section_text) <= max_chars:
        return [section_text]

    chunks: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", section_text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        parts = _split_oversized_paragraph(paragraph, policy)
        for part in parts:
            current = _append_or_flush(chunks, current, part, policy)

    if current:
        chunks.append(current)
    return chunks


def _append_or_flush(
    chunks: list[str],
    current: str,
    part: str,
    policy: ChunkPolicy,
) -> str:
    """Append text to the current chunk or flush with a small overlap."""
    max_chars = policy.max_chars
    separator = "\n\n" if current else ""
    candidate = f"{current}{separator}{part}" if current else part
    if len(candidate) <= max_chars:
        return candidate

    if current:
        chunks.append(current)
    return _with_overlap(current, part, policy)


def _with_overlap(previous: str, part: str, policy: ChunkPolicy) -> str:
    """Prefix the next chunk with a short tail from the previous chunk."""
    if not previous:
        return part
    overlap_chars = policy.overlap_chars
    max_chars = policy.max_chars
    overlap = previous[-overlap_chars:].strip()
    if not overlap:
        return part
    candidate = f"{overlap}\n\n{part}"
    if len(candidate) <= max_chars:
        return candidate
    return part


def _split_oversized_paragraph(
    paragraph: str,
    policy: ChunkPolicy | None = None,
) -> list[str]:
    """Split paragraphs that are longer than the embedding chunk budget."""
    policy = policy or ChunkPolicy(
        max_tokens=_DEFAULT_MAX_TOKENS,
        overlap_tokens=_OVERLAP_TOKENS,
        content_type="narrative",
    )
    max_chars = policy.max_chars
    if len(paragraph) <= max_chars:
        return [paragraph]

    parts: list[str] = []
    current = ""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.extend(_split_by_chars(sentence, policy))
            continue
        current = _append_or_flush(parts, current, sentence, policy)

    if current:
        parts.append(current)
    return parts


def _split_by_chars(text: str, policy: ChunkPolicy | None = None) -> list[str]:
    """Last-resort split for long unbroken text."""
    policy = policy or ChunkPolicy(
        max_tokens=_DEFAULT_MAX_TOKENS,
        overlap_tokens=_OVERLAP_TOKENS,
        content_type="narrative",
    )
    max_chars = policy.max_chars
    overlap_chars = policy.overlap_chars
    parts: list[str] = []
    start = 0
    step = max_chars - overlap_chars
    while start < len(text):
        end = min(start + max_chars, len(text))
        parts.append(text[start:end].strip())
        if end == len(text):
            break
        start += step
    return [part for part in parts if part]


def _embedding_text(title: str, chunk: dict) -> str:
    """Return chunk text with parent heading context for richer retrieval.

    Prepends the section path (e.g. "Method > Training") so the embedding
    captures hierarchical relationships, not just raw text. This follows the
    ChunkNorris principle: parent headings disambiguate similar content.
    """
    section_path = chunk.get("section_path") or chunk.get("section_label") or "Unknown"
    content_type = chunk.get("content_type") or "narrative"
    return (
        f"Paper: {title}\n"
        f"Section: {section_path}\n"
        f"Content type: {content_type}\n\n"
        f"Chunk:\n{chunk['text']}"
    )


def _llm_context(raw_text: str) -> str:
    """Return a bounded sample for the optional readable markdown pass."""
    if len(raw_text) <= _LLM_CONTEXT_MAX_CHARS:
        return raw_text

    head_budget = _LLM_CONTEXT_MAX_CHARS // 2
    tail_budget = _LLM_CONTEXT_MAX_CHARS - head_budget
    head = raw_text[:head_budget]
    tail = raw_text[-tail_budget:]
    return f"{head}\n\n[...middle omitted for markdown normalization...]\n\n{tail}"


# ── DB helpers ────────────────────────────────────────────────────────────


async def _store_chunks(
    db: AsyncSession,
    project_paper_id: UUID,
    chunks: list[dict],
) -> None:
    from sqlalchemy import delete

    await db.execute(
        delete(PaperChunk).where(
            PaperChunk.project_paper_id == project_paper_id,
            PaperChunk.chunk_type == "full_text",
        )
    )

    for c in chunks:
        embedding_json = json.dumps(c["embedding"]) if c.get("embedding") else None
        section = c.get("section_label")
        if section and len(section) > 60:
            section = section[:60]
        db.add(
            PaperChunk(
                project_paper_id=project_paper_id,
                chunk_text=c["text"],
                chunk_type=c.get("chunk_type", "full_text"),
                section_label=section,
                section_path=c.get("section_path"),
                chunk_index=c.get("chunk_index"),
                page_start=c.get("page_start"),
                page_end=c.get("page_end"),
                content_type=c.get("content_type"),
                pipeline_version=c.get("pipeline_version"),
                content_hash=c.get("content_hash"),
                embedding=embedding_json,
                embedding_model=c.get("embedding_model"),
                embedding_dimension=c.get("embedding_dimension"),
            )
        )
    await db.commit()


async def _update_status(
    db: AsyncSession,
    project_paper_id: UUID,
    status: str,
) -> None:
    result = await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    pp = result.scalar_one_or_none()
    if pp is not None:
        pp.full_text_status = status
        await db.commit()
