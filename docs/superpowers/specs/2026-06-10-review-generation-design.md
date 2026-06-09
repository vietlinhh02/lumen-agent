# Review Generation with RAG + Citation Guardrail

## Problem

The current `review_writer_node` (`app/agents/nodes.py:545-585`) only uses
`state.matrix_rows` and `state.gaps` from in-memory LangGraph state. It has:

- No DB persistence — report is lost after workflow ends
- No RAG — never calls `retrieve_project_evidence()`, no full-text chunks
- No citation validation — citation IDs are LLM-generated but never verified
- No reference list — no DB metadata lookup
- No REST endpoints — no report router exists

The `ReviewReport` and `ReviewCitation` DB models are already defined. The
`ReviewOutput` Pydantic schema with `CitedParagraph` validators exists. The
hybrid retrieval function `retrieve_project_evidence()` works. None of these
are wired to the review writer.

## Current State

- `review_writer_node`: takes matrix + gaps from state, sends JSON to LLM,
  returns in-memory sections
- `ReviewReport` model: `review_reports` table with `validation_status`
- `ReviewCitation` model: `review_citations` table linking report → project_paper
- `RetrievalAudit` model: stores retrieval traces
- `retrieve_project_evidence()`: hybrid RAG returning chunks with `project_paper_id`
- `ReviewOutput` / `CitedParagraph`: Pydantic schemas with `must_cite_something` validator
- No report generation service, no citation guardrail service, no report router

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| RAG approach | Single broad query, top 50 chunks | Matches matrix/gap pattern, 1 DB call |
| Chunk grouping | By project_paper_id, top 5 per paper | Consistent with matrix_extraction_node |
| Citation validation | Check against `project_papers` where `status='saved'` | Per api-design.md guardrail contract |
| Invalid citation handling | Trim invalid IDs, retry once if >30% invalid | Full guardrail with pragmatic retry |
| Reference list | Built from DB `papers` table metadata | Never from model text |
| Persistence | `review_reports` + `review_citations` tables | Already defined in models.py |
| Export format | Markdown via `GET /reports/{id}/export` | Per api-design.md |
| Separate citation_guardrail service | No — inline in report_generation | Too simple to justify separate file |
| Report title | From request body, default to project title | User control |

## Architecture

### Data Flow

```
POST /projects/{id}/reports
  → Load saved project_papers + matrix_rows + gaps from DB
  → RAG: retrieve_project_evidence(db, project_id, topic, limit=50)
  → Group chunks by project_paper_id (top 5 per paper)
  → Build prompt: matrix + gaps + chunk context + allowed citation IDs
  → LLM generates structured ReviewOutput (sections + cited paragraphs)
  → Citation guardrail: validate each citation_paper_id against project_papers
  → If >30% invalid: retry once with stricter prompt
  → Build content_markdown from validated sections
  → Build reference list from DB paper metadata
  → Persist: review_reports + review_citations
  → Return report with validation_status + references + citation_audit
```

### Node Signature Change

Before:
```python
async def review_writer_node(state: ResearchState) -> dict:
```

After:
```python
async def review_writer_node(state: ResearchState, db: AsyncSession) -> dict:
```

The graph's `_wrap()` function already handles this pattern — it checks if
the second parameter is named `db` and passes an async session.

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/report_generation.py` | Report generation + citation validation + persistence |
| `app/routers/reports.py` | POST/GET/GET/:id/export endpoints |
| `app/schemas/reports.py` | Pydantic request/response models |
| `tests/test_review_writer.py` | Unit tests for node + service |

## Files to Modify

| File | Change |
|------|--------|
| `app/ai/prompts.py` | Add `REVIEW_WRITER_CHUNK_SYSTEM` / `REVIEW_WRITER_CHUNK_USER` |
| `app/agents/nodes.py:545-585` | Rewrite `review_writer_node` with RAG + DB |
| `app/main.py` | Register reports router |

## Detailed Design

### 1. Prompts (`app/ai/prompts.py`)

Add after existing `REVIEW_WRITER_USER`:

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

### 2. Report Generation Service (`app/services/report_generation.py`)

```python
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

async def _build_content_markdown(sections: list[dict], references: list[dict]) -> str:
    """Convert validated sections + references into Markdown."""

async def _build_references(db: AsyncSession, cited_paper_ids: set[UUID]) -> list[dict]:
    """Build reference list from DB paper metadata."""

async def _persist_report(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    content_markdown: str,
    validation_status: str,
    all_paragraphs: list[dict],
) -> ReviewReport:
    """Save report + citations to DB."""
```

### 3. Citation Validation Logic (inline in service)

```python
async def _validate_citations(
    db: AsyncSession,
    project_id: UUID,
    sections: list[dict],
) -> tuple[list[dict], dict]:
    """Validate citation IDs against project_papers.

    Returns (cleaned_sections, audit).
    - Removes paragraphs with zero valid citations.
    - Trims invalid IDs from paragraphs that have some valid IDs.
    - audit = {total_citations, invalid_citations, valid_citations, uncited_saved_papers}
    """
    # Load valid project_paper_ids
    stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(stmt)).scalars().all())

    total = 0
    invalid = 0
    valid_cited_ids = set()
    cleaned_sections = []

    for section in sections:
        cleaned_paras = []
        for para in section.get("paragraphs", []):
            raw_ids = para.get("citation_paper_ids", [])
            total += len(raw_ids)
            valid_ids = []
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
```

### 4. Retry Logic

```python
# After first LLM call + validation:
invalid_ratio = audit["invalid_citations"] / max(audit["total_citations"], 1)
if invalid_ratio > 0.3:
    # Retry with stricter prompt
    stricter_msg = REVIEW_WRITER_CHUNK_USER.format(
        ...
    ) + f"\n\nWARNING: Previous attempt had {audit['invalid_citations']} invalid citations. " \
        f"Use ONLY these paper IDs: {paper_ids_json}"
    # LLM call again
    # Validate again
    # Use second result if better
```

### 5. REST Endpoints (`app/routers/reports.py`)

```python
@router.post("/{project_id}/reports", response_model=ReportResponse)
async def create_report(project_id, request, db, user):
    # Verify ownership
    # Call generate_report()
    # Return report

@router.get("/{project_id}/reports", response_model=ReportListResponse)
async def list_reports(project_id, db, user):
    # Verify ownership
    # Return reports for project

@router.get("/{project_id}/reports/{report_id}", response_model=ReportDetailResponse)
async def get_report(project_id, report_id, db, user):
    # Verify ownership
    # Return report + references + citation_audit

@router.get("/{project_id}/reports/{report_id}/export")
async def export_report(project_id, report_id, db, user):
    # Verify ownership
    # Return Markdown file
```

### 6. Schemas (`app/schemas/reports.py`)

```python
class CreateReportRequest(BaseModel):
    title: str | None = None
    include_gap_section: bool = True
    selected_gap_ids: list[str] | None = None

class ReferenceResponse(BaseModel):
    citation_label: str
    project_paper_id: str
    title: str
    authors: list[str]
    year: int | None
    url: str | None

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
    references: list[ReferenceResponse]
    citation_audit: CitationAuditResponse

class ReportListResponse(BaseModel):
    items: list[ReportResponse]
    total: int

class ReportDetailResponse(BaseModel):
    id: str
    title: str
    validation_status: str
    content_markdown: str
    references: list[ReferenceResponse]
    citation_audit: CitationAuditResponse
    created_at: str
```

### 7. Graph Update (`app/agents/graph.py`)

No change needed — `_wrap()` already detects `db` parameter and passes it.
The `review_writer_node` signature change from `(state)` to `(state, db)` is
all that's needed.

### 8. Main.py Registration

```python
from app.routers.reports import router as reports_router
app.include_router(reports_router, prefix="/api/projects")
```

### 9. Markdown Export

```python
def _build_content_markdown(sections, references):
    parts = []
    for section in sections:
        parts.append(f"## {section['heading']}\n")
        for para in section['paragraphs']:
            cited_ids = para['citation_paper_ids']
            labels = [ref_map[pid] for pid in cited_ids if pid in ref_map]
            citation_str = ", ".join(labels)
            parts.append(f"{para['text']} ({citation_str})\n")
    parts.append("\n## References\n")
    for ref in references:
        authors = ", ".join(ref['authors'][:3])
        if len(ref['authors']) > 3:
            authors += " et al."
        parts.append(f"{ref['citation_label']} {authors} ({ref['year']}). {ref['title']}. {ref.get('url', '')}\n")
    return "\n".join(parts)
```

### 10. Tests (`tests/test_review_writer.py`)

- No matrix rows → returns failed status
- With matrix + gaps + chunks → generates sections with valid citations
- Invalid citation IDs → trimmed from paragraphs
- All citations invalid → retry triggered
- LLM failure → returns failed status
- No project_id → returns failed status
- DB persistence → report + citations stored correctly
- Export → returns valid Markdown with reference list

## Edge Cases

1. **No matrix rows**: Return `report_status: "failed"` with error
2. **No saved papers**: Return `report_status: "failed"` with error
3. **RAG returns 0 chunks**: Fall back to matrix-only prompt (like current behavior)
4. **LLM returns invalid JSON**: Return `report_status: "failed"` with error
5. **All citations invalid after retry**: Persist report with `validation_status: "invalid"`
6. **No gaps selected**: Generate review without gap section
7. **User provides custom title**: Use it; otherwise default to project title
