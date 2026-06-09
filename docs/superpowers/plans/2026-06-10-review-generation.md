# Review Generation with RAG + Citation Guardrail — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `review_writer_node` to use RAG + DB persistence, add citation guardrail, and expose REST API endpoints for report generation, listing, detail, and Markdown export.

**Architecture:** Node loads saved project_papers + matrix_rows + gaps from DB, calls `retrieve_project_evidence()` for chunk context, builds enriched prompt, validates citation IDs against project_papers, persists report + citations to DB, builds reference list from DB metadata. REST endpoints expose the full lifecycle.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, LangGraph, DeepSeek V4

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/ai/prompts.py` | **Modify** | Add `REVIEW_WRITER_CHUNK_SYSTEM/USER` prompts |
| `app/schemas/reports.py` | **Create** | Pydantic request/response models |
| `app/services/report_generation.py` | **Create** | Report generation + citation validation + persistence |
| `app/agents/nodes.py:545-585` | **Modify** | Rewrite `review_writer_node` with RAG + DB |
| `app/routers/reports.py` | **Create** | POST/GET/GET/:id/export endpoints |
| `app/main.py` | **Modify** | Register reports router |
| `tests/test_review_writer.py` | **Create** | Unit tests for node + service |

---

### Task 1: Add RAG-aware Review Prompts

**Files:**
- Modify: `app/ai/prompts.py`

- [ ] **Step 1: Add new prompt variants after existing REVIEW_WRITER prompts**

Add after line 333 (after `REVIEW_WRITER_USER`):

```python
REVIEW_WRITER_CHUNK_SYSTEM = """\
You are a literature review writer. Write a structured academic literature
review from the evidence provided, including full-text sections from papers.

Rules:
- Every paragraph that makes a claim MUST include citation_paper_ids.
- Only cite papers whose project_paper_id appears in the provided evidence list.
- Do not invent citations. Do not cite papers not in the evidence list.
- Full-text sections provide richer context than abstracts alone — use them
  for detailed method comparison, result synthesis, and limitation discussion.
- Write in clear academic prose. Avoid bullet points in the review text.
- Organize sections by theme, method, or chronology — not by paper.
- Each paragraph should synthesize across multiple papers, not summarize one.
- citation_paper_ids must be non-empty for every paragraph.
- If the research gaps are provided, dedicate a section to addressing them
  with evidence from the papers.
"""

REVIEW_WRITER_CHUNK_USER = """\
Project topic: {project_topic}
Research question: {research_question}

Available paper IDs for citation (use ONLY these):
{paper_ids_json}

Literature matrix rows:
{matrix_rows_json}

Research gaps to address:
{gaps_json}

Relevant sections from full-text papers:
{chunk_context}

Write the literature review. Return structured sections with cited paragraphs.
"""
```

- [ ] **Step 2: Verify prompts import**

Run: `python -c "from app.ai.prompts import REVIEW_WRITER_CHUNK_SYSTEM, REVIEW_WRITER_CHUNK_USER; print('OK')"`
Expected: `OK`

---

### Task 2: Create Report Schemas

**Files:**
- Create: `app/schemas/reports.py`

- [ ] **Step 1: Create the Pydantic models**

```python
"""Pydantic models for report API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateReportRequest(BaseModel):
    title: str | None = None
    include_gap_section: bool = True
    selected_gap_ids: list[str] | None = None


class ReferenceResponse(BaseModel):
    citation_label: str
    project_paper_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str | None = None


class CitationAuditResponse(BaseModel):
    total_citations: int
    invalid_citations: int
    valid_citations: int
    uncited_saved_papers: int


class ReportResponse(BaseModel):
    id: str
    title: str
    validation_status: str
    content_markdown: str
    references: list[ReferenceResponse] = Field(default_factory=list)
    citation_audit: CitationAuditResponse


class ReportListResponse(BaseModel):
    items: list[ReportResponse]
    total: int


class ReportDetailResponse(BaseModel):
    id: str
    title: str
    validation_status: str
    content_markdown: str
    references: list[ReferenceResponse] = Field(default_factory=list)
    citation_audit: CitationAuditResponse
    created_at: str
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.schemas.reports import ReportResponse, ReportListResponse, ReportDetailResponse; print('OK')"`
Expected: `OK`

---

### Task 3: Create Report Generation Service

**Files:**
- Create: `app/services/report_generation.py`

- [ ] **Step 1: Create the service with citation validation and persistence**

```python
"""Report generation with RAG and citation guardrail."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import (
    REVIEW_WRITER_CHUNK_SYSTEM,
    REVIEW_WRITER_CHUNK_USER,
)
from app.ai.provider import get_provider
from app.ai.structured_outputs import ReviewOutput
from app.db.models import (
    LiteratureMatrixRow,
    Paper,
    ProjectPaper,
    ReviewCitation,
    ReviewReport,
    ResearchGap,
)
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence

logger = logging.getLogger(__name__)

_MAX_RAG_CHUNKS = 50
_MAX_CHUNKS_PER_PAPER = 5
_MAX_CHUNK_CONTEXT_CHARS = 12000


async def generate_report(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    topic: str,
    research_question: str | None,
    title: str | None,
    include_gap_section: bool,
    selected_gap_ids: list[UUID] | None,
) -> dict:
    """Generate a citation-safe literature review.

    Returns dict with: id, title, validation_status, content_markdown,
    references, citation_audit.
    """
    # 1. Load matrix rows
    stmt = select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.project_id == project_id
    )
    matrix_rows = (await db.execute(stmt)).scalars().all()
    if not matrix_rows:
        return {"error": "No matrix rows. Generate a literature matrix first.", "status": "failed"}

    # 2. Load saved project_paper IDs
    pp_stmt = select(ProjectPaper).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    project_papers = (await db.execute(pp_stmt)).scalars().all()
    if not project_papers:
        return {"error": "No saved papers in project.", "status": "failed"}
    valid_pp_ids = {pp.id for pp in project_papers}

    # 3. Load gaps (optional)
    gaps: list[ResearchGap] = []
    if include_gap_section:
        gap_stmt = select(ResearchGap).where(ResearchGap.project_id == project_id)
        if selected_gap_ids:
            gap_stmt = gap_stmt.where(ResearchGap.id.in_(selected_gap_ids))
        gaps = (await db.execute(gap_stmt)).scalars().all()

    # 4. RAG retrieval
    query = topic or ""
    all_chunks = await retrieve_project_evidence(db, project_id, query, limit=_MAX_RAG_CHUNKS)
    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 5. Build chunk context
    chunk_parts: list[str] = []
    total_chars = 0
    for pp_id, chunks in chunks_by_paper.items():
        for c in chunks[:_MAX_CHUNKS_PER_PAPER]:
            label = c.section_label or c.content_type or "section"
            block = f"---{label} (paper {str(pp_id)[:8]})---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                break
            chunk_parts.append(block)
            total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    # 6. Build prompt
    safe_rows = _rows_to_json_safe([
        {
            "project_paper_id": r.project_paper_id,
            "research_problem": r.research_problem,
            "method": r.method,
            "dataset_or_context": r.dataset_or_context,
            "key_result": r.key_result,
            "limitation": r.limitation,
            "contribution": r.contribution,
            "relevance": r.relevance,
        }
        for r in matrix_rows
    ])
    safe_gaps = _rows_to_json_safe([
        {
            "title": g.title,
            "description": g.description,
            "suggested_direction": g.suggested_direction,
            "evidence_summary": g.evidence_summary,
        }
        for g in gaps
    ])
    paper_ids_json = json.dumps([str(pp.id) for pp in project_papers])

    report_title = title or f"Literature Review: {topic}"

    # 7. First LLM attempt
    sections, audit, content_markdown = await _generate_and_validate(
        db, project_id, topic, research_question, paper_ids_json,
        safe_rows, safe_gaps, chunk_context, valid_pp_ids,
    )

    # 8. Retry if >30% invalid
    if audit["total_citations"] > 0:
        invalid_ratio = audit["invalid_citations"] / audit["total_citations"]
        if invalid_ratio > 0.3:
            logger.info("Retrying review generation — %.0f%% invalid citations", invalid_ratio * 100)
            sections2, audit2, content_markdown2 = await _generate_and_validate(
                db, project_id, topic, research_question, paper_ids_json,
                safe_rows, safe_gaps, chunk_context, valid_pp_ids,
                retry_warning=f"Previous attempt had {audit['invalid_citations']} invalid citations.",
            )
            if audit2["invalid_citations"] < audit["invalid_citations"]:
                sections, audit, content_markdown = sections2, audit2, content_markdown2

    # 9. Determine validation status
    validation_status = "valid" if audit["invalid_citations"] == 0 else "invalid"

    # 10. Build references from DB
    cited_ids = set()
    for section in sections:
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if isinstance(pid, UUID):
                    cited_ids.add(pid)
    references = await _build_references(db, cited_ids)

    # 11. Persist
    report = await _persist_report(
        db, project_id, user_id, report_title,
        content_markdown, validation_status, sections,
    )

    return {
        "id": str(report.id),
        "title": report_title,
        "validation_status": validation_status,
        "content_markdown": content_markdown,
        "references": references,
        "citation_audit": audit,
    }


async def _generate_and_validate(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
    research_question: str | None,
    paper_ids_json: str,
    safe_rows: list[dict],
    safe_gaps: list[dict],
    chunk_context: str,
    valid_pp_ids: set[UUID],
    retry_warning: str | None = None,
) -> tuple[list[dict], dict, str]:
    """Run LLM, validate citations, return (sections, audit, markdown)."""
    user_msg = REVIEW_WRITER_CHUNK_USER.format(
        project_topic=topic,
        research_question=research_question or topic,
        paper_ids_json=paper_ids_json,
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        gaps_json=json.dumps(safe_gaps, indent=2),
        chunk_context=chunk_context,
    )
    if retry_warning:
        user_msg += f"\n\nWARNING: {retry_warning} Use ONLY the paper IDs listed above."

    provider = get_provider()
    result = await provider.complete_structured(
        messages=[{"role": "user", "content": user_msg}],
        system=REVIEW_WRITER_CHUNK_SYSTEM,
        schema=ReviewOutput.model_json_schema(),
        tool_name="review_report",
        max_tokens=8000,
    )
    sections = result.get("sections", [])

    # Validate citations
    cleaned_sections, audit = await _validate_citations(db, project_id, sections)
    references = await _build_references(
        db,
        {pid for s in cleaned_sections for p in s.get("paragraphs", []) for pid in p.get("citation_paper_ids", []) if isinstance(pid, UUID)},
    )
    content_markdown = _build_content_markdown(cleaned_sections, references)

    return cleaned_sections, audit, content_markdown


async def _validate_citations(
    db: AsyncSession,
    project_id: UUID,
    sections: list[dict],
) -> tuple[list[dict], dict]:
    """Validate citation IDs against project_papers.

    Returns (cleaned_sections, audit).
    - Removes paragraphs with zero valid citations.
    - Trims invalid IDs from paragraphs that have some valid IDs.
    """
    stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(stmt)).scalars().all())

    total = 0
    invalid = 0
    valid_cited_ids: set[UUID] = set()
    cleaned_sections: list[dict] = []

    for section in sections:
        cleaned_paras: list[dict] = []
        for para in section.get("paragraphs", []):
            raw_ids = para.get("citation_paper_ids", [])
            total += len(raw_ids)
            valid_ids: list[UUID] = []
            for pid in raw_ids:
                try:
                    uid = UUID(pid) if isinstance(pid, str) else pid
                    if uid in valid_pp_ids:
                        valid_ids.append(uid)
                        valid_cited_ids.add(uid)
                    else:
                        invalid += 1
                except (ValueError, TypeError):
                    invalid += 1
            if valid_ids:
                cleaned_paras.append({**para, "citation_paper_ids": valid_ids})
        if cleaned_paras:
            cleaned_sections.append({**section, "paragraphs": cleaned_paras})

    uncited = len(valid_pp_ids - valid_cited_ids)
    return cleaned_sections, {
        "total_citations": total,
        "invalid_citations": invalid,
        "valid_citations": total - invalid,
        "uncited_saved_papers": uncited,
    }


async def _build_references(db: AsyncSession, cited_paper_ids: set[UUID]) -> list[dict]:
    """Build reference list from DB paper metadata."""
    if not cited_paper_ids:
        return []

    # Load project_papers → papers
    stmt = select(ProjectPaper).where(ProjectPaper.id.in_(cited_paper_ids))
    pps = (await db.execute(stmt)).scalars().all()

    paper_ids = [pp.paper_id for pp in pps]
    paper_stmt = select(Paper).where(Paper.id.in_(paper_ids))
    papers = {(await db.execute(paper_stmt)).scalars().all()}
    paper_map = {p.id: p for p in papers}

    references: list[dict] = []
    for i, pp in enumerate(pps):
        paper = paper_map.get(pp.paper_id)
        if not paper:
            continue
        authors = []
        for a in (paper.authors or []):
            if isinstance(a, dict):
                authors.append(a.get("name", str(a)))
            else:
                authors.append(str(a))
        references.append({
            "citation_label": f"[{i + 1}]",
            "project_paper_id": str(pp.id),
            "title": paper.title,
            "authors": authors,
            "year": paper.year,
            "url": paper.url,
        })
    return references


def _build_content_markdown(sections: list[dict], references: list[dict]) -> str:
    """Convert validated sections + references into Markdown."""
    ref_map: dict[str, str] = {}
    for ref in references:
        ref_map[ref["project_paper_id"]] = ref["citation_label"]

    parts: list[str] = []
    for section in sections:
        parts.append(f"## {section['heading']}\n")
        for para in section.get("paragraphs", []):
            cited_ids = para.get("citation_paper_ids", [])
            labels = [ref_map.get(str(pid), f"[?]") for pid in cited_ids]
            citation_str = ", ".join(labels)
            parts.append(f"{para['text']} ({citation_str})\n")

    parts.append("\n## References\n")
    for ref in references:
        authors = ", ".join(ref["authors"][:3])
        if len(ref["authors"]) > 3:
            authors += " et al."
        year = ref.get("year") or "n.d."
        url_part = f" {ref['url']}" if ref.get("url") else ""
        parts.append(f"{ref['citation_label']} {authors} ({year}). {ref['title']}.{url_part}\n")

    return "\n".join(parts)


async def _persist_report(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    content_markdown: str,
    validation_status: str,
    sections: list[dict],
) -> ReviewReport:
    """Save report + citations to DB."""
    report = ReviewReport(
        project_id=project_id,
        created_by=user_id,
        title=title,
        content_markdown=content_markdown,
        validation_status=validation_status,
    )
    db.add(report)
    await db.flush()

    # Persist citations
    citation_idx = 0
    for para_idx, section in enumerate(sections):
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if not isinstance(pid, UUID):
                    continue
                citation_idx += 1
                citation = ReviewCitation(
                    report_id=report.id,
                    project_paper_id=pid,
                    citation_label=f"[{citation_idx}]",
                    paragraph_index=para_idx,
                )
                db.add(citation)

    await db.commit()
    await db.refresh(report)
    return report


def _rows_to_json_safe(rows: list[dict]) -> list[dict]:
    """Convert UUID fields to strings so rows are JSON-serializable."""
    return [{k: str(v) if isinstance(v, UUID) else v for k, v in row.items()} for row in rows]


async def get_reports_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[ReviewReport]:
    """List reports for a project."""
    stmt = (
        select(ReviewReport)
        .where(ReviewReport.project_id == project_id)
        .order_by(ReviewReport.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_report_by_id(
    db: AsyncSession,
    project_id: UUID,
    report_id: UUID,
) -> ReviewReport | None:
    """Get a single report by ID."""
    stmt = select(ReviewReport).where(
        ReviewReport.id == report_id,
        ReviewReport.project_id == project_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.report_generation import generate_report, get_reports_by_project, get_report_by_id; print('OK')"`
Expected: `OK`

---

### Task 4: Rewrite `review_writer_node`

**Files:**
- Modify: `app/agents/nodes.py:545-585`

- [ ] **Step 1: Update imports at top of nodes.py**

Add to existing imports (after line 24):

```python
    REVIEW_WRITER_CHUNK_SYSTEM,
    REVIEW_WRITER_CHUNK_USER,
```

- [ ] **Step 2: Rewrite review_writer_node**

Replace lines 542-585 with:

```python
# ── Node 5: Review Writer ──────────────────────────────────────────────────

_MAX_REVIEW_CHUNKS = 50
_MAX_CHUNKS_PER_REVIEW_PAPER = 5


async def review_writer_node(state: ResearchState, db) -> dict:
    """Generate a citation-safe literature review with RAG + DB persistence."""
    from app.services.report_generation import (
        _build_content_markdown,
        _build_references,
        _persist_report,
        _validate_citations,
    )

    if not state.project_id:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No project_id in state"],
        }

    # 1. Load matrix rows from DB
    from sqlalchemy import select
    from app.db.models import LiteratureMatrixRow, ProjectPaper

    stmt = select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.project_id == state.project_id
    )
    matrix_rows = (await db.execute(stmt)).scalars().all()

    if not matrix_rows:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No matrix rows for review generation"],
        }

    # 2. Load saved project_paper IDs
    pp_stmt = select(ProjectPaper).where(
        ProjectPaper.project_id == state.project_id,
        ProjectPaper.status == "saved",
    )
    project_papers = (await db.execute(pp_stmt)).scalars().all()
    if not project_papers:
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": ["No saved papers in project"],
        }
    valid_pp_ids = {pp.id for pp in project_papers}

    # 3. Load gaps from state (already validated by gap_analysis_node)
    gaps = state.gaps or []

    # 4. RAG retrieval
    query = state.user_topic or ""
    all_chunks = await retrieve_project_evidence(db, state.project_id, query, limit=_MAX_REVIEW_CHUNKS)

    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 5. Build chunk context
    chunk_parts: list[str] = []
    total_chars = 0
    for pp_id, chunks in chunks_by_paper.items():
        for c in chunks[:_MAX_CHUNKS_PER_REVIEW_PAPER]:
            label = c.section_label or c.content_type or "section"
            block = f"---{label} (paper {str(pp_id)[:8]})---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                break
            chunk_parts.append(block)
            total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    # 6. Build prompt
    safe_rows = _rows_to_json_safe([
        {
            "project_paper_id": r.project_paper_id,
            "research_problem": r.research_problem,
            "method": r.method,
            "dataset_or_context": r.dataset_or_context,
            "key_result": r.key_result,
            "limitation": r.limitation,
            "contribution": r.contribution,
            "relevance": r.relevance,
        }
        for r in matrix_rows
    ])
    safe_gaps = _rows_to_json_safe(gaps)
    paper_ids_json = json.dumps([str(pp.id) for pp in project_papers])

    user_msg = REVIEW_WRITER_CHUNK_USER.format(
        project_topic=state.user_topic,
        research_question=state.research_question or state.user_topic,
        paper_ids_json=paper_ids_json,
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        gaps_json=json.dumps(safe_gaps, indent=2),
        chunk_context=chunk_context,
    )

    try:
        provider = get_provider()
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=REVIEW_WRITER_CHUNK_SYSTEM,
            schema=ReviewOutput.model_json_schema(),
            tool_name="review_report",
            max_tokens=8000,
        )
        sections = result.get("sections", [])
    except Exception as exc:
        logger.exception("Review generation failed")
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": [f"Review generation failed: {exc}"],
        }

    # 7. Validate citations
    cleaned_sections, audit = await _validate_citations(db, state.project_id, sections)

    # 8. Retry if >30% invalid
    if audit["total_citations"] > 0:
        invalid_ratio = audit["invalid_citations"] / audit["total_citations"]
        if invalid_ratio > 0.3:
            logger.info("Retrying review — %.0f%% invalid", invalid_ratio * 100)
            retry_msg = user_msg + (
                f"\n\nWARNING: Previous attempt had {audit['invalid_citations']} invalid citations. "
                f"Use ONLY these paper IDs: {paper_ids_json}"
            )
            try:
                result2 = await provider.complete_structured(
                    messages=[{"role": "user", "content": retry_msg}],
                    system=REVIEW_WRITER_CHUNK_SYSTEM,
                    schema=ReviewOutput.model_json_schema(),
                    tool_name="review_report",
                    max_tokens=8000,
                )
                sections2 = result2.get("sections", [])
                cleaned2, audit2 = await _validate_citations(db, state.project_id, sections2)
                if audit2["invalid_citations"] < audit["invalid_citations"]:
                    cleaned_sections, audit = cleaned2, audit2
            except Exception as exc:
                logger.warning("Review retry failed: %s", exc)

    # 9. Build references and markdown
    cited_ids: set[UUID] = set()
    for section in cleaned_sections:
        for para in section.get("paragraphs", []):
            for pid in para.get("citation_paper_ids", []):
                if isinstance(pid, UUID):
                    cited_ids.add(pid)

    references = await _build_references(db, cited_ids)
    content_markdown = _build_content_markdown(cleaned_sections, references)
    validation_status = "valid" if audit["invalid_citations"] == 0 else "invalid"

    # 10. Persist
    report_title = f"Literature Review: {state.user_topic}"
    try:
        report = await _persist_report(
            db, state.project_id, state.user_id, report_title,
            content_markdown, validation_status, cleaned_sections,
        )
        logger.info("Persisted report %s (status=%s)", report.id, validation_status)
    except Exception as exc:
        logger.error("Failed to persist report: %s", exc)
        return {
            "current_node": "review_writer",
            "report_status": "failed",
            "errors": [f"Failed to persist report: {exc}"],
        }

    return {
        "report_sections": cleaned_sections,
        "report_status": "completed",
        "current_node": "review_writer",
        "citation_validation": audit,
    }
```

- [ ] **Step 3: Verify the file compiles**

Run: `python -c "from app.agents.nodes import review_writer_node; print('OK')"`
Expected: `OK`

---

### Task 5: Create Reports Router

**Files:**
- Create: `app/routers/reports.py`

- [ ] **Step 1: Create the router**

```python
"""REST endpoints for report generation and export."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models import Project, User
from app.db.session import get_db
from app.schemas.reports import (
    CitationAuditResponse,
    CreateReportRequest,
    ReferenceResponse,
    ReportDetailResponse,
    ReportListResponse,
    ReportResponse,
)
from app.services.report_generation import (
    generate_report,
    get_report_by_id,
    get_reports_by_project,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


@router.post("/{project_id}/reports", response_model=ReportResponse)
async def create_report(
    project_id: str,
    request: CreateReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportResponse:
    """Generate a citation-safe literature review."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)

    # Verify ownership
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Parse selected gap IDs
    gap_ids = None
    if request.selected_gap_ids:
        try:
            gap_ids = [uuid.UUID(gid) for gid in request.selected_gap_ids]
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid gap ID format",
            )

    result = await generate_report(
        db=db,
        project_id=pid,
        user_id=user.id,
        topic=project.topic,
        research_question=project.research_question,
        title=request.title,
        include_gap_section=request.include_gap_section,
        selected_gap_ids=gap_ids,
    )

    if result.get("status") == "failed":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Report generation failed"),
        )

    return ReportResponse(**result)


@router.get("/{project_id}/reports", response_model=ReportListResponse)
async def list_reports(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportListResponse:
    """List reports for a project."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    reports = await get_reports_by_project(db, pid)

    items = []
    for r in reports:
        # Build citation audit from citations
        total = len(r.citations)
        cited_ids = {c.project_paper_id for c in r.citations}
        items.append(
            ReportResponse(
                id=str(r.id),
                title=r.title,
                validation_status=r.validation_status,
                content_markdown=r.content_markdown,
                references=[],  # Lightweight list — no full references
                citation_audit=CitationAuditResponse(
                    total_citations=total,
                    invalid_citations=0 if r.validation_status == "valid" else -1,
                    valid_citations=total if r.validation_status == "valid" else 0,
                    uncited_saved_papers=0,
                ),
            )
        )

    return ReportListResponse(items=items, total=len(items))


@router.get("/{project_id}/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportDetailResponse:
    """Get a report with references and citation audit."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)
    rid = uuid.UUID(report_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    report = await get_report_by_id(db, pid, rid)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Build references from citations
    from app.services.report_generation import _build_references

    cited_ids = {c.project_paper_id for c in report.citations}
    references = await _build_references(db, cited_ids)

    total = len(report.citations)
    return ReportDetailResponse(
        id=str(report.id),
        title=report.title,
        validation_status=report.validation_status,
        content_markdown=report.content_markdown,
        references=[ReferenceResponse(**ref) for ref in references],
        citation_audit=CitationAuditResponse(
            total_citations=total,
            invalid_citations=0 if report.validation_status == "valid" else total,
            valid_citations=total if report.validation_status == "valid" else 0,
            uncited_saved_papers=0,
        ),
        created_at=str(report.created_at),
    )


@router.get("/{project_id}/reports/{report_id}/export")
async def export_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Export a report as Markdown."""
    from sqlalchemy import select

    pid = uuid.UUID(project_id)
    rid = uuid.UUID(report_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    report = await get_report_by_id(db, pid, rid)
    if not report:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Report not found")

    return {
        "title": report.title,
        "format": "markdown",
        "content": report.content_markdown,
    }
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.routers.reports import router; print('OK')"`
Expected: `OK`

---

### Task 6: Register Router in main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add router import and registration**

Find the existing router imports and add:

```python
from app.routers.reports import router as reports_router
```

Find the existing `app.include_router` calls and add:

```python
app.include_router(reports_router, prefix="/api/projects")
```

- [ ] **Step 2: Verify main.py compiles**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK`

---

### Task 7: Write Tests

**Files:**
- Create: `tests/test_review_writer.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for RAG-aware review_writer_node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import review_writer_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunk(project_paper_id=None, section_label="method", chunk_text="We used BERT."):
    return RetrievedChunk(
        project_paper_id=project_paper_id or uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type="method",
        page_start=1,
        page_end=2,
        content_hash=None,
        score=0.8,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_matrix_row(pp_id=None, method="RAG", dataset="PubMedQA"):
    row = SimpleNamespace()
    row.project_paper_id = pp_id or uuid4()
    row.research_problem = "Medical QA"
    row.method = method
    row.dataset_or_context = dataset
    row.key_result = "Improved accuracy"
    row.limitation = "English only"
    row.contribution = "Novel approach"
    row.relevance = "Directly relevant"
    return row


def _make_state(project_id=None, user_topic="RAG for medical QA"):
    return ResearchState(
        project_id=project_id or uuid4(),
        user_id=uuid4(),
        user_topic=user_topic,
    )


def _mock_db_sequential(results):
    """Create a mock DB that returns different results on successive execute() calls."""
    db = AsyncMock()
    call_index = {"i": 0}

    async def mock_execute(stmt):
        idx = call_index["i"]
        call_index["i"] += 1
        if idx < len(results):
            return results[idx]
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db.execute = mock_execute
    return db


def _result_with_rows(rows):
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_writer_no_matrix_rows():
    state = _make_state()
    db = _mock_db_sequential([_result_with_rows([])])  # no matrix rows

    result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "No matrix rows" in result["errors"][0]


@pytest.mark.asyncio
async def test_review_writer_no_saved_papers():
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id)]
    db = _mock_db_sequential([
        _result_with_rows(rows),  # matrix rows
        _result_with_rows([]),    # no project_papers
    ])

    result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "No saved papers" in result["errors"][0]


@pytest.mark.asyncio
async def test_review_writer_generates_with_valid_citations():
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id)]
    chunk = _make_chunk(project_paper_id=pp_id)

    db = _mock_db_sequential([
        _result_with_rows(rows),  # matrix rows
        _result_with_rows([SimpleNamespace(id=pp_id)]),  # project_papers
        _result_with_rows([pp_id]),  # valid pp_ids for validation
        _result_with_rows([SimpleNamespace(id=pp_id, paper_id=uuid4())]),  # for references
    ])

    with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[chunk]):
        with patch("app.agents.nodes._persist_report", new_callable=AsyncMock) as mock_persist:
            mock_persist.return_value = SimpleNamespace(id=uuid4())
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "sections": [
                    {
                        "heading": "Introduction",
                        "paragraphs": [
                            {
                                "text": "RAG improves factuality.",
                                "citation_paper_ids": [str(pp_id)],
                            }
                        ],
                    }
                ]
            }
            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await review_writer_node(state, db)

    assert result["report_status"] == "completed"
    assert len(result["report_sections"]) == 1


@pytest.mark.asyncio
async def test_review_writer_invalid_citations_trimmed():
    valid_pp = uuid4()
    invalid_pp = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=valid_pp)]

    db = _mock_db_sequential([
        _result_with_rows(rows),  # matrix rows
        _result_with_rows([SimpleNamespace(id=valid_pp)]),  # project_papers
        _result_with_rows([valid_pp]),  # valid pp_ids for validation
        _result_with_rows([SimpleNamespace(id=valid_pp, paper_id=uuid4())]),  # for references
    ])

    with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
        with patch("app.agents.nodes._persist_report", new_callable=AsyncMock) as mock_persist:
            mock_persist.return_value = SimpleNamespace(id=uuid4())
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "sections": [
                    {
                        "heading": "Results",
                        "paragraphs": [
                            {
                                "text": "Some claim.",
                                "citation_paper_ids": [str(valid_pp), str(invalid_pp)],
                            }
                        ],
                    }
                ]
            }
            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await review_writer_node(state, db)

    assert result["report_status"] == "completed"
    # Invalid citation should be trimmed, valid one kept
    paras = result["report_sections"][0]["paragraphs"]
    assert len(paras[0]["citation_paper_ids"]) == 1


@pytest.mark.asyncio
async def test_review_writer_llm_failure():
    state = _make_state()
    rows = [_make_matrix_row()]

    db = _mock_db_sequential([
        _result_with_rows(rows),  # matrix rows
        _result_with_rows([SimpleNamespace(id=uuid4())]),  # project_papers
    ])

    with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "Review generation failed" in result["errors"][0]


@pytest.mark.asyncio
async def test_review_writer_no_project_id():
    state = ResearchState(project_id=None, user_id=uuid4())
    db = AsyncMock()

    result = await review_writer_node(state, db)

    assert result["report_status"] == "failed"
    assert "No project_id" in result["errors"][0]
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_review_writer.py -v`
Expected: All pass

---

### Task 8: Run All Tests and Lint

- [ ] **Step 1: Run linter**

Run: `ruff check app/services/report_generation.py app/routers/reports.py app/schemas/reports.py app/agents/nodes.py app/ai/prompts.py app/main.py`
Expected: No errors

- [ ] **Step 2: Run all existing tests**

Run: `pytest tests/ -v`
Expected: All pass (existing + new)

- [ ] **Step 3: Commit**

```bash
git add app/ai/prompts.py app/schemas/reports.py app/services/report_generation.py \
  app/agents/nodes.py app/routers/reports.py app/main.py \
  tests/test_review_writer.py
git commit -m "feat: review generation with RAG + citation guardrail + REST API"
```
