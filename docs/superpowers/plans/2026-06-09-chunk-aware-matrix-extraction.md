# Chunk-Aware Matrix Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `matrix_extraction_node` to use hybrid-retrieved chunks from full-text PDFs instead of only title+abstract, and persist results to `literature_matrix_rows`.

**Architecture:** Node loads saved project_papers from DB, calls `retrieve_project_evidence()` to get relevant chunks grouped by paper, builds enriched prompts using `MATRIX_EXTRACTION_*` templates + chunk context, validates output with `MatrixRowOutput` Pydantic model, and upserts rows to DB.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, LangGraph, DeepSeek V4

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/services/literature_matrix.py` | **Create** | CRUD service: get_by_project, upsert_rows, get_existing_paper_ids |
| `app/ai/prompts.py:161-184` | **Modify** | Add `MATRIX_EXTRACTION_CHUNK_SYSTEM` and `MATRIX_EXTRACTION_CHUNK_USER` prompt variants |
| `app/agents/nodes.py:180-238` | **Modify** | Rewrite `matrix_extraction_node` to use DB, chunks, new prompts, Pydantic model |
| `app/agents/graph.py:64-71` | **Modify** | Update `_wrap()` to pass `db` session to nodes that accept it |
| `tests/test_matrix_extraction.py` | **Create** | Unit tests for the rewritten node |

---

### Task 1: Create Literature Matrix CRUD Service

**Files:**
- Create: `app/services/literature_matrix.py`
- Test: `tests/test_matrix_extraction.py` (tests in Task 5)

- [ ] **Step 1: Create the CRUD service**

```python
# app/services/literature_matrix.py
"""CRUD operations for literature_matrix_rows."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LiteratureMatrixRow, ProjectPaper

logger = logging.getLogger(__name__)


async def get_existing_paper_ids(
    db: AsyncSession,
    project_id: UUID,
) -> set[UUID]:
    """Return project_paper_ids that already have matrix rows."""
    stmt = (
        select(LiteratureMatrixRow.project_paper_id)
        .where(LiteratureMatrixRow.project_id == project_id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return set(rows)


async def upsert_rows(
    db: AsyncSession,
    project_id: UUID,
    rows: list[dict],
) -> int:
    """Upsert matrix rows. Returns count of rows inserted/updated.

    Each dict in `rows` must have:
        - project_paper_id: UUID
        - research_problem, method, dataset_or_context, key_result,
          limitation, contribution, relevance: str | None
        - extraction_confidence: str ('high', 'medium', 'low')
    """
    if not rows:
        return 0

    count = 0
    for row in rows:
        stmt = (
            pg_insert(LiteratureMatrixRow)
            .values(
                project_id=project_id,
                project_paper_id=row["project_paper_id"],
                research_problem=row.get("research_problem"),
                method=row.get("method"),
                dataset_or_context=row.get("dataset_or_context"),
                key_result=row.get("key_result"),
                limitation=row.get("limitation"),
                contribution=row.get("contribution"),
                relevance=row.get("relevance"),
                extraction_confidence=row.get("extraction_confidence", "medium"),
                created_by="ai",
            )
            .on_conflict_do_update(
                index_elements=["project_paper_id"],
                set_={
                    "research_problem": row.get("research_problem"),
                    "method": row.get("method"),
                    "dataset_or_context": row.get("dataset_or_context"),
                    "key_result": row.get("key_result"),
                    "limitation": row.get("limitation"),
                    "contribution": row.get("contribution"),
                    "relevance": row.get("relevance"),
                    "extraction_confidence": row.get("extraction_confidence", "medium"),
                    "created_by": "ai",
                },
            )
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    return count


async def get_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[LiteratureMatrixRow]:
    """Return all matrix rows for a project, ordered by creation."""
    stmt = (
        select(LiteratureMatrixRow)
        .where(LiteratureMatrixRow.project_id == project_id)
        .order_by(LiteratureMatrixRow.updated_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_row(
    db: AsyncSession,
    project_id: UUID,
    row_id: UUID,
) -> bool:
    """Delete a matrix row. Returns True if deleted."""
    stmt = (
        select(LiteratureMatrixRow)
        .where(
            LiteratureMatrixRow.id == row_id,
            LiteratureMatrixRow.project_id == project_id,
        )
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.literature_matrix import upsert_rows, get_by_project, get_existing_paper_ids; print('OK')"`
Expected: `OK`

---

### Task 2: Add Chunk-Aware Matrix Extraction Prompts

**Files:**
- Modify: `app/ai/prompts.py:161-184`

- [ ] **Step 1: Add new prompt variants after existing MATRIX_EXTRACTION prompts**

Add after line 184 (after `MATRIX_EXTRACTION_USER`):

```python
MATRIX_EXTRACTION_CHUNK_SYSTEM = """\
You are a systematic literature review assistant. Extract structured information
from the paper metadata and relevant full-text sections provided.

Rules:
- Use only the information given. Do not invent details.
- Full-text sections provide richer context than the abstract alone — use them
  for method, dataset, key_result, and limitation fields.
- If a field cannot be determined from the available text, return "not specified".
- Set confidence to "high" only if the abstract AND sections clearly support all fields.
- Set confidence to "low" if critical fields like method or result are missing.
- Keep each field concise: 1 to 3 sentences maximum.
- The relevance field must connect the paper to the specific project topic.
"""

MATRIX_EXTRACTION_CHUNK_USER = """\
Project topic: {project_topic}

Paper title: {title}
Authors: {authors}
Year: {year}
Abstract: {abstract}
Venue: {venue}

Relevant sections from the full text:
{chunk_context}

Extract the literature matrix row for this paper.
"""
```

- [ ] **Step 2: Verify prompts import**

Run: `python -c "from app.ai.prompts import MATRIX_EXTRACTION_CHUNK_SYSTEM, MATRIX_EXTRACTION_CHUNK_USER; print('OK')"`
Expected: `OK`

---

### Task 3: Rewrite matrix_extraction_node

**Files:**
- Modify: `app/agents/nodes.py:1-30` (imports)
- Modify: `app/agents/nodes.py:177-238` (matrix_extraction_node)

- [ ] **Step 1: Update imports at top of nodes.py**

Replace the imports section (lines 16-28) to add the new prompts and DB imports:

```python
from app.agents.state import ResearchState
from app.ai.prompts import (
    FACET_EXTRACTION_SYSTEM,
    FACET_EXTRACTION_USER,
    GAP_ANALYSIS_SYSTEM,
    GAP_ANALYSIS_USER,
    MATRIX_EXTRACTION_CHUNK_SYSTEM,
    MATRIX_EXTRACTION_CHUNK_USER,
    QUERY_PLANNER_SYSTEM,
    QUERY_PLANNER_USER,
    REVIEW_WRITER_SYSTEM,
    REVIEW_WRITER_USER,
)
from app.ai.provider import get_provider
from app.ai.structured_outputs import MatrixRowOutput, QueryPlanOutput
from app.services.hybrid_retrieval import RetrievedChunk, retrieve_project_evidence
from app.services.literature_matrix import get_existing_paper_ids, upsert_rows
```

- [ ] **Step 2: Rewrite matrix_extraction_node**

Replace lines 177-238 with:

```python
# ── Node 3: Matrix Extraction ──────────────────────────────────────────────

_MAX_CHUNKS_PER_PAPER = 5
_MAX_PAPERS = 20


def _build_chunk_context(chunks: list[RetrievedChunk]) -> str:
    """Format chunks into prompt-ready section blocks."""
    if not chunks:
        return "No full-text sections available."
    parts: list[str] = []
    for c in chunks:
        label = c.section_label or c.content_type or "section"
        parts.append(f"---{label}---\n{c.chunk_text}")
    return "\n\n".join(parts)


async def matrix_extraction_node(state: ResearchState, db) -> dict:
    """Generate literature matrix rows using metadata + retrieved chunks."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.db.models import Paper, ProjectPaper

    if not state.project_id:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "failed",
            "errors": ["No project_id in state"],
        }

    # 1. Load saved project_papers with paper metadata
    stmt = (
        select(ProjectPaper)
        .options(selectinload(ProjectPaper.paper))
        .where(
            ProjectPaper.project_id == state.project_id,
            ProjectPaper.status == "saved",
        )
        .limit(_MAX_PAPERS)
    )
    project_papers = (await db.execute(stmt)).scalars().all()

    if not project_papers:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "failed",
            "errors": ["No saved papers to extract matrix from"],
        }

    # 2. Skip papers that already have matrix rows
    existing_ids = await get_existing_paper_ids(db, state.project_id)
    papers_to_process = [pp for pp in project_papers if pp.id not in existing_ids]

    if not papers_to_process:
        return {
            "current_node": "matrix_extraction",
            "matrix_status": "completed",
            "matrix_rows": [],
        }

    # 3. Retrieve chunks for the whole project
    query = state.user_topic or ""
    all_chunks = await retrieve_project_evidence(
        db, state.project_id, query, limit=40
    )

    # 4. Group chunks by project_paper_id
    chunks_by_paper: dict = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 5. Extract matrix rows
    provider = get_provider()
    rows: list[dict] = []

    for pp in papers_to_process:
        paper = pp.paper
        paper_chunks = chunks_by_paper.get(pp.id, [])[:_MAX_CHUNKS_PER_PAPER]
        chunk_context = _build_chunk_context(paper_chunks)

        try:
            user_msg = MATRIX_EXTRACTION_CHUNK_USER.format(
                project_topic=state.user_topic,
                title=paper.title,
                authors=", ".join(
                    a.get("name", str(a)) if isinstance(a, dict) else str(a)
                    for a in (paper.authors or [])
                ),
                year=paper.year or "unknown",
                abstract=paper.abstract or "No abstract available",
                venue=paper.venue or "not specified",
                chunk_context=chunk_context,
            )
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                system=MATRIX_EXTRACTION_CHUNK_SYSTEM,
                schema=MatrixRowOutput.model_json_schema(),
                tool_name="matrix_row",
                max_tokens=2000,
            )
            rows.append({
                "project_paper_id": pp.id,
                "research_problem": result.get("research_problem", "not specified"),
                "method": result.get("method", "not specified"),
                "dataset_or_context": result.get("dataset_or_context", "not specified"),
                "key_result": result.get("key_result", "not specified"),
                "limitation": result.get("limitation", "not specified"),
                "contribution": result.get("contribution", "not specified"),
                "relevance": result.get("relevance", "not specified"),
                "extraction_confidence": result.get("confidence", "medium"),
            })
        except Exception as exc:
            logger.warning(
                "Matrix extraction failed for paper '%s': %s",
                paper.title[:60], exc,
            )

    # 6. Persist to DB
    if rows:
        try:
            saved_count = await upsert_rows(db, state.project_id, rows)
            logger.info("Persisted %d matrix rows for project %s", saved_count, state.project_id)
        except Exception as exc:
            logger.error("Failed to persist matrix rows: %s", exc)

    return {
        "matrix_rows": rows,
        "matrix_status": "completed" if rows else "failed",
        "current_node": "matrix_extraction",
    }
```

- [ ] **Step 3: Verify the file compiles**

Run: `python -c "from app.agents.nodes import matrix_extraction_node; print('OK')"`
Expected: `OK`

---

### Task 4: Update Graph to Pass DB Session

**Files:**
- Modify: `app/agents/graph.py:64-71` (_wrap function)
- Modify: `app/agents/graph.py:79-113` (run_research_workflow)

- [ ] **Step 1: Update _wrap to pass db to nodes that accept it**

Replace the `_wrap` function (lines 64-71):

```python
def _wrap(node_fn):
    """Wrap an async node so LangGraph can invoke it.

    LangGraph nodes receive ``state`` and return a dict of partial updates.
    Nodes that accept a second ``db`` parameter receive an async session.
    """
    import inspect

    sig = inspect.signature(node_fn)
    params = list(sig.parameters.keys())
    needs_db = len(params) >= 2 and params[1] == "db"

    if needs_db:
        async def wrapper(state: ResearchState) -> dict[str, Any]:
            async with async_session_factory() as db:
                return await node_fn(state, db)
    else:
        async def wrapper(state: ResearchState) -> dict[str, Any]:
            return await node_fn(state)
    return wrapper
```

- [ ] **Step 2: Add import for async_session_factory**

Add at the top of graph.py (after existing imports):

```python
from app.db.session import async_session_factory
```

- [ ] **Step 3: Verify graph compiles**

Run: `python -c "from app.agents.graph import build_research_graph; print('OK')"`
Expected: `OK`

---

### Task 5: Write Tests

**Files:**
- Create: `tests/test_matrix_extraction.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for chunk-aware matrix extraction node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import _build_chunk_context, matrix_extraction_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunk(
    project_paper_id=None,
    section_label="method",
    content_type="method",
    chunk_text="We used BERT for encoding.",
    score=0.8,
):
    return RetrievedChunk(
        project_paper_id=project_paper_id or uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type=content_type,
        page_start=1,
        page_end=2,
        content_hash=None,
        score=score,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_project_paper(pp_id=None, title="Test Paper", abstract="Test abstract"):
    pp = SimpleNamespace()
    pp.id = pp_id or uuid4()
    pp.status = "saved"
    pp.paper = SimpleNamespace()
    pp.paper.title = title
    pp.paper.abstract = abstract
    pp.paper.authors=["Author A"]
    pp.paper.year=2024
    pp.paper.venue="Test Venue"
    return pp


def _make_state(project_id=None, user_topic="RAG for medical QA"):
    return ResearchState(
        project_id=project_id or uuid4(),
        user_id=uuid4(),
        user_topic=user_topic,
    )


# ── _build_chunk_context tests ───────────────────────────────────────────────


def test_build_chunk_context_with_chunks():
    chunks = [
        _make_chunk(section_label="method", chunk_text="We used BERT."),
        _make_chunk(section_label="results", chunk_text="Accuracy improved 5%."),
    ]
    result = _build_chunk_context(chunks)
    assert "---method---" in result
    assert "---results---" in result
    assert "We used BERT." in result
    assert "Accuracy improved 5%." in result


def test_build_chunk_context_empty():
    result = _build_chunk_context([])
    assert result == "No full-text sections available."


def test_build_chunk_context_missing_label():
    chunk = _make_chunk(section_label=None, content_type="narrative")
    result = _build_chunk_context([chunk])
    assert "---narrative---" in result


# ── matrix_extraction_node tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_matrix_extraction_no_saved_papers():
    state = _make_state()
    db = AsyncMock()

    with patch("app.agents.nodes.get_existing_paper_ids", new_callable=AsyncMock, return_value=set()):
        with patch("app.agents.nodes.select") as mock_select:
            mock_execute = AsyncMock()
            mock_execute.return_value.scalars.return_value.all.return_value = []
            db.execute = mock_execute

            result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "failed"
    assert "No saved papers" in result["errors"][0]


@pytest.mark.asyncio
async def test_matrix_extraction_skips_existing_rows():
    pp_id = uuid4()
    state = _make_state()
    db = AsyncMock()

    with patch("app.agents.nodes.get_existing_paper_ids", new_callable=AsyncMock, return_value={pp_id}):
        pp = _make_project_paper(pp_id=pp_id)
        mock_execute = AsyncMock()
        mock_execute.return_value.scalars.return_value.all.return_value = [pp]
        db.execute = mock_execute

        result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert result["matrix_rows"] == []


@pytest.mark.asyncio
async def test_matrix_extraction_with_chunks():
    pp_id = uuid4()
    state = _make_state()
    db = AsyncMock()

    chunk = _make_chunk(project_paper_id=pp_id, section_label="method", chunk_text="We used dense retrieval.")

    with patch("app.agents.nodes.get_existing_paper_ids", new_callable=AsyncMock, return_value=set()):
        with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[chunk]):
            with patch("app.agents.nodes.upsert_rows", new_callable=AsyncMock, return_value=1):
                pp = _make_project_paper(pp_id=pp_id)
                mock_execute = AsyncMock()
                mock_execute.return_value.scalars.return_value.all.return_value = [pp]
                db.execute = mock_execute

                mock_provider = AsyncMock()
                mock_provider.complete_structured.return_value = {
                    "research_problem": "Medical QA accuracy",
                    "method": "Dense retrieval with BERT",
                    "dataset_or_context": "PubMedQA",
                    "key_result": "Improved accuracy by 5%",
                    "limitation": "English only",
                    "contribution": "Novel RAG pipeline",
                    "relevance": "Directly relevant",
                    "confidence": "high",
                }

                with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                    result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1
    assert result["matrix_rows"][0]["project_paper_id"] == pp_id
    assert "Dense retrieval" in result["matrix_rows"][0]["method"]


@pytest.mark.asyncio
async def test_matrix_extraction_no_chunks_falls_back():
    pp_id = uuid4()
    state = _make_state()
    db = AsyncMock()

    with patch("app.agents.nodes.get_existing_paper_ids", new_callable=AsyncMock, return_value=set()):
        with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
            with patch("app.agents.nodes.upsert_rows", new_callable=AsyncMock, return_value=1):
                pp = _make_project_paper(pp_id=pp_id)
                mock_execute = AsyncMock()
                mock_execute.return_value.scalars.return_value.all.return_value = [pp]
                db.execute = mock_execute

                mock_provider = AsyncMock()
                mock_provider.complete_structured.return_value = {
                    "research_problem": "Test problem",
                    "method": "Test method",
                    "dataset_or_context": "Test context",
                    "key_result": "Test result",
                    "limitation": "not specified",
                    "contribution": "Test contribution",
                    "relevance": "Test relevance",
                    "confidence": "medium",
                }

                with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                    result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1


@pytest.mark.asyncio
async def test_matrix_extraction_partial_failure():
    """One paper fails extraction, others succeed."""
    pp_id_1 = uuid4()
    pp_id_2 = uuid4()
    state = _make_state()
    db = AsyncMock()

    with patch("app.agents.nodes.get_existing_paper_ids", new_callable=AsyncMock, return_value=set()):
        with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
            with patch("app.agents.nodes.upsert_rows", new_callable=AsyncMock, return_value=1) as mock_upsert:
                pp1 = _make_project_paper(pp_id=pp_id_1, title="Paper A")
                pp2 = _make_project_paper(pp_id=pp_id_2, title="Paper B")
                mock_execute = AsyncMock()
                mock_execute.return_value.scalars.return_value.all.return_value = [pp1, pp2]
                db.execute = mock_execute

                call_count = 0
                async def mock_complete(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        raise Exception("LLM timeout")
                    return {
                        "research_problem": "Test",
                        "method": "Test",
                        "dataset_or_context": "Test",
                        "key_result": "Test",
                        "limitation": "not specified",
                        "contribution": "Test",
                        "relevance": "Test",
                        "confidence": "medium",
                    }

                mock_provider = AsyncMock()
                mock_provider.complete_structured = mock_complete

                with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                    result = await matrix_extraction_node(state, db)

    assert result["matrix_status"] == "completed"
    assert len(result["matrix_rows"]) == 1  # only second paper succeeded
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_matrix_extraction.py -v`
Expected: All tests pass

---

### Task 6: Integration Verification

- [ ] **Step 1: Run linter**

Run: `ruff check app/agents/nodes.py app/agents/graph.py app/services/literature_matrix.py app/ai/prompts.py`
Expected: No errors

- [ ] **Step 2: Run type checker**

Run: `ty check app/agents/nodes.py app/agents/graph.py app/services/literature_matrix.py`
Expected: No errors (or only pre-existing issues)

- [ ] **Step 3: Run all existing tests**

Run: `pytest tests/ -v`
Expected: All pass (existing + new)

- [ ] **Step 4: Commit**

```bash
git add app/services/literature_matrix.py app/ai/prompts.py app/agents/nodes.py app/agents/graph.py tests/test_matrix_extraction.py
git commit -m "feat: chunk-aware matrix extraction with DB persistence"
```
