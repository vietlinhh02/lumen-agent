"""Generate and edit Markdown documents for the AI assistant chat."""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_provider
from app.db.models import (
    ChatDocument,
    LiteratureMatrixRow,
    ResearchGap,
)
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence

logger = logging.getLogger(__name__)

_MAX_RAG_CHUNKS = 30
_MAX_CHUNKS_PER_PAPER = 4
_MAX_CHUNK_CHARS = 8000


def parse_markdown_sections(markdown: str) -> list[dict]:
    """Split a Markdown document into a list of {heading, body} sections by H2.

    Sections are delimited by lines starting with '## '. A document with no
    headings is returned as a single section with empty heading.
    """
    if not markdown or not markdown.strip():
        return [{"heading": "", "body": ""}]
    parts = re.split(r"(?m)^## ", markdown)
    sections: list[dict] = []
    for i, part in enumerate(parts):
        if i == 0:
            preamble = part.strip()
            if preamble:
                sections.append({"heading": "", "body": preamble})
            continue
        lines = part.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections.append({"heading": heading, "body": body})
    if not sections:
        sections = [{"heading": "", "body": markdown.strip()}]
    return sections


def _sections_to_markdown(title: str, sections: list[dict]) -> str:
    parts = [f"# {title}\n"]
    for sec in sections:
        if sec["heading"]:
            parts.append(f"\n## {sec['heading']}\n")
        if sec["body"]:
            parts.append(sec["body"])
    parts.append("\n## References\n")
    parts.append("_(auto-generated, populated after citation guardrail)_\n")
    return "\n".join(parts)


async def _load_context(db: AsyncSession, project_id: UUID) -> tuple[list, list]:
    """Load matrix rows + gaps for a project."""
    mr_stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == project_id)
    matrix_rows = list((await db.execute(mr_stmt)).scalars().all())

    g_stmt = select(ResearchGap).where(ResearchGap.project_id == project_id)
    gaps = list((await db.execute(g_stmt)).scalars().all())
    return matrix_rows, gaps


def _rows_to_json_safe(rows: list) -> list[dict]:
    out = []
    for r in rows:
        out.append(
            {
                "project_paper_id": str(r.project_paper_id),
                "research_problem": r.research_problem,
                "method": r.method,
                "dataset_or_context": r.dataset_or_context,
                "key_result": r.key_result,
                "limitation": r.limitation,
                "contribution": r.contribution,
                "relevance": r.relevance,
            }
        )
    return out


def _build_chunk_context(chunks: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    total = 0
    for c in chunks:
        label = c.section_label or c.content_type or "section"
        block = f"---{label}---\n{c.chunk_text}"
        if total + len(block) > _MAX_CHUNK_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "No full-text sections available."


async def generate_markdown_for_project(
    db: AsyncSession,
    project_id: UUID,
    document_id: UUID,
    user_id: UUID,
    topic: str,
    research_question: str | None,
    include_gaps: bool = True,
) -> dict:
    """Generate a Markdown literature review and write it to chat_documents.

    Returns dict with keys: title, markdown, version, section_count.
    """
    matrix_rows, gaps = await _load_context(db, project_id)
    if not matrix_rows:
        return {
            "title": "Empty Report",
            "markdown": "",
            "version": 0,
            "section_count": 0,
            "error": "no_matrix_rows",
        }

    # RAG retrieval
    all_chunks: list[RetrievedChunk] = []
    try:
        all_chunks = await retrieve_project_evidence(db, project_id, topic, limit=_MAX_RAG_CHUNKS)
    except Exception as exc:
        logger.warning("RAG retrieval failed: %s", exc)
    chunk_context = _build_chunk_context(all_chunks)

    safe_rows = _rows_to_json_safe(matrix_rows)
    safe_gaps = [
        {"title": g.title, "description": g.description, "evidence_summary": g.evidence_summary}
        for g in gaps
    ]

    system = (
        "You are a literature review writer. Return structured JSON with "
        "'title' (string) and 'sections' (list of {heading, body}). "
        "Use clear academic prose. Each section should synthesize across papers, "
        "not summarize one. Group by theme, method, or chronology."
    )
    user = (
        f"Project topic: {topic}\n"
        f"Research question: {research_question or topic}\n\n"
        f"Matrix rows:\n{json.dumps(safe_rows, indent=2, default=str)}\n\n"
        f"Research gaps:\n{json.dumps(safe_gaps, indent=2, default=str)}\n\n"
        f"Relevant full-text sections:\n{chunk_context}\n"
    )

    provider = get_provider()
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": user}],
        schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["heading", "body"],
                    },
                },
            },
            "required": ["title", "sections"],
        },
        tool_name="generate_chat_report",
        system=system,
        max_tokens=4000,
    )

    title = result.get("title", f"Literature Review: {topic}")
    sections = result.get("sections", [])
    markdown = _sections_to_markdown(title, sections)

    # Persist to DB
    new_version = 1
    doc = (
        await db.execute(select(ChatDocument).where(ChatDocument.id == document_id))
    ).scalar_one_or_none()
    if doc is None:
        doc = ChatDocument(
            id=document_id,
            project_id=project_id,
            user_id=user_id,
            title=title,
            content_md=markdown,
            version=new_version,
        )
        db.add(doc)
    else:
        doc.title = title
        doc.content_md = markdown
        doc.version = doc.version + 1
        new_version = doc.version
    await db.commit()

    return {
        "title": title,
        "markdown": markdown,
        "version": new_version,
        "section_count": len(sections),
    }


async def edit_section(
    db: AsyncSession,
    document_id: UUID,
    project_id: UUID,
    section_index: int,
    instruction: str,
    current_markdown: str,
) -> dict:
    """Rewrite one section of the report. Other sections are preserved."""
    sections = parse_markdown_sections(current_markdown)
    if section_index < 0 or section_index >= len(sections):
        return {
            "markdown": current_markdown,
            "version": 0,
            "section_index": section_index,
            "error": f"section_index {section_index} out of range (0..{len(sections) - 1})",
        }

    target = sections[section_index]
    system = (
        "You are a literature review editor. Return JSON: "
        "{'section': {'heading': string, 'body': string}}. "
        "Rewrite the section according to the user's instruction. "
        "Preserve academic tone. Do not invent citations."
    )
    user = (
        f"Current section heading: {target['heading']}\n"
        f"Current body:\n{target['body']}\n\n"
        f"Instruction: {instruction}\n"
    )

    provider = get_provider()
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": user}],
        schema={
            "type": "object",
            "properties": {
                "section": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["heading", "body"],
                },
            },
            "required": ["section"],
        },
        tool_name="edit_chat_report_section",
        system=system,
        max_tokens=2000,
    )

    new_section = result.get("section", {})
    new_heading = (new_section.get("heading") or target["heading"]).strip()
    new_body = (new_section.get("body") or target["body"]).strip()
    sections[section_index] = {"heading": new_heading, "body": new_body}

    # Find title from preamble (first H1 or section with empty heading)
    title = "Literature Review"
    if sections and not sections[0]["heading"]:
        preamble = sections[0]["body"]
        title = preamble.split("\n", 1)[0].strip("# ").strip()[:120] or title
        sections = sections[1:]

    new_markdown = _sections_to_markdown(title, sections)

    # Persist
    doc = (
        await db.execute(select(ChatDocument).where(ChatDocument.id == document_id))
    ).scalar_one_or_none()
    new_version = 1
    if doc is not None:
        doc.content_md = new_markdown
        doc.version = doc.version + 1
        new_version = doc.version
        await db.commit()
    else:
        await db.rollback()

    return {
        "markdown": new_markdown,
        "version": new_version,
        "section_index": section_index,
        "section_preview": new_body[:300],
    }
