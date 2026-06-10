# Gap Analysis + Conflict Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite gap_analysis_node to use RAG + DB persistence, add conflict_detection_node, and expose both via REST API endpoints.

**Architecture:** Both nodes accept `db` session (same pattern as matrix_extraction_node). Gap node calls `retrieve_project_evidence()` for chunk context, validates evidence_paper_ids against project_papers, and persists to `research_gaps` + `gap_evidence`. Conflict node compares matrix rows by shared method/dataset and persists to `conflicting_findings`. Both exposed via FastAPI routers.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, LangGraph, DeepSeek V4

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/services/gap_detection.py` | **Create** | CRUD: upsert_gaps, get_by_project, delete_gap |
| `app/services/conflict_detection.py` | **Create** | CRUD: detect_and_persist_conflicts, get_by_project |
| `app/ai/prompts.py:217-244` | **Modify** | Add GAP_ANALYSIS_CHUNK_SYSTEM/USER prompts |
| `app/agents/nodes.py:348-386` | **Modify** | Rewrite gap_analysis_node with RAG + DB |
| `app/agents/nodes.py` | **Modify** | Add conflict_detection_node |
| `app/agents/graph.py:59-71` | **Modify** | Add conflict_detection node, update edges |
| `app/schemas/gaps.py` | **Create** | Pydantic request/response models |
| `app/schemas/conflicts.py` | **Create** | Pydantic request/response models |
| `app/routers/gaps.py` | **Create** | POST/GET/DELETE endpoints |
| `app/routers/conflicts.py` | **Create** | POST/GET endpoints |
| `app/main.py` | **Modify** | Register gaps and conflicts routers |
| `tests/test_gap_analysis.py` | **Create** | Unit tests for gap_analysis_node |
| `tests/test_conflict_detection.py` | **Create** | Unit tests for conflict_detection_node |

---

### Task 1: Create Gap Detection Service

**Files:**
- Create: `app/services/gap_detection.py`

- [ ] **Step 1: Create the CRUD service**

```python
# app/services/gap_detection.py
"""CRUD operations for research_gaps and gap_evidence tables."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import GapEvidence, ProjectPaper, ResearchGap

logger = logging.getLogger(__name__)


async def upsert_gaps(
    db: AsyncSession,
    project_id: UUID,
    gaps: list[dict],
) -> int:
    """Delete existing gaps for project, insert new ones with evidence.

    Each dict in ``gaps`` must have:
        - title, description, suggested_direction, evidence_summary: str
        - confidence: 'high' | 'medium' | 'low'
        - evidence: list[{project_paper_id: UUID, evidence_type: str, note: str}]
    Returns count of gaps inserted.
    """
    if not gaps:
        return 0

    # Delete old gaps (cascade deletes gap_evidence)
    await db.execute(delete(ResearchGap).where(ResearchGap.project_id == project_id))

    count = 0
    for gap_data in gaps:
        gap = ResearchGap(
            project_id=project_id,
            title=gap_data["title"],
            description=gap_data["description"],
            suggested_direction=gap_data["suggested_direction"],
            evidence_summary=gap_data["evidence_summary"],
            confidence=gap_data.get("confidence", "medium"),
        )
        db.add(gap)
        await db.flush()  # get gap.id

        for ev in gap_data.get("evidence", []):
            evidence = GapEvidence(
                gap_id=gap.id,
                project_paper_id=ev["project_paper_id"],
                evidence_type=ev["evidence_type"],
                note=ev["note"],
            )
            db.add(evidence)

        count += 1

    await db.commit()
    return count


async def get_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[ResearchGap]:
    """Load gaps with evidence_entries eager-loaded."""
    stmt = (
        select(ResearchGap)
        .options(selectinload(ResearchGap.evidence_entries))
        .where(ResearchGap.project_id == project_id)
        .order_by(ResearchGap.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def delete_gap(
    db: AsyncSession,
    project_id: UUID,
    gap_id: UUID,
) -> bool:
    """Delete single gap. Returns True if deleted."""
    stmt = select(ResearchGap).where(
        ResearchGap.id == gap_id,
        ResearchGap.project_id == project_id,
    )
    gap = (await db.execute(stmt)).scalar_one_or_none()
    if not gap:
        return False
    await db.delete(gap)
    await db.commit()
    return True


async def validate_evidence_ids(
    db: AsyncSession,
    project_id: UUID,
    evidence_paper_ids: list[UUID],
) -> set[UUID]:
    """Return the subset of evidence_paper_ids that are valid saved project_papers."""
    if not evidence_paper_ids:
        return set()
    stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
        ProjectPaper.id.in_(evidence_paper_ids),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return set(rows)
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.gap_detection import upsert_gaps, get_by_project, delete_gap, validate_evidence_ids; print('OK')"`
Expected: `OK`

---

### Task 2: Create Conflict Detection Service

**Files:**
- Create: `app/services/conflict_detection.py`

- [ ] **Step 1: Create the service**

```python
# app/services/conflict_detection.py
"""Conflict detection from literature matrix rows."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.prompts import CONTRADICTION_DETECTION_SYSTEM, CONTRADICTION_DETECTION_USER
from app.ai.provider import get_provider
from app.db.models import ConflictingFinding, LiteratureMatrixRow, ProjectPaper

logger = logging.getLogger(__name__)

_MIN_MATRIX_ROWS = 4


async def detect_and_persist_conflicts(
    db: AsyncSession,
    project_id: UUID,
    topic: str,
) -> list[dict]:
    """Load matrix rows, group by shared method/dataset, detect conflicts via LLM,
    validate paper IDs, persist to conflicting_findings table.

    Returns list of conflict dicts for state.
    """
    # 1. Load matrix rows
    stmt = (
        select(LiteratureMatrixRow)
        .where(LiteratureMatrixRow.project_id == project_id)
    )
    rows = (await db.execute(stmt)).scalars().all()

    if len(rows) < _MIN_MATRIX_ROWS:
        logger.info("Too few matrix rows (%d) for conflict detection", len(rows))
        return []

    # 2. Load valid project_paper_ids
    pp_stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(pp_stmt)).scalars().all())

    # 3. Group rows by shared method or dataset
    by_method: dict[str, list] = defaultdict(list)
    by_dataset: dict[str, list] = defaultdict(list)

    for row in rows:
        method = (row.method or "").strip().lower()
        dataset = (row.dataset_or_context or "").strip().lower()
        if method and method != "not specified":
            by_method[method].append(row)
        if dataset and dataset != "not specified":
            by_dataset[dataset].append(row)

    # 4. Collect candidate groups (2+ rows with same method or dataset)
    candidate_groups: list[tuple[str, list]] = []
    for key, group in by_method.items():
        if len(group) >= 2:
            candidate_groups.append((f"method: {key}", group))
    for key, group in by_dataset.items():
        if len(group) >= 2:
            candidate_groups.append((f"dataset: {key}", group))

    if not candidate_groups:
        logger.info("No shared method/dataset groups found for conflict detection")
        return []

    # 5. Detect conflicts via LLM
    provider = get_provider()
    conflicts: list[dict] = []

    for shared_context, group in candidate_groups[:10]:  # limit groups
        paper_ids_json = json.dumps([str(r.project_paper_id) for r in group])
        rows_json = json.dumps(
            [
                {
                    "project_paper_id": str(r.project_paper_id),
                    "method": r.method,
                    "dataset_or_context": r.dataset_or_context,
                    "key_result": r.key_result,
                    "limitation": r.limitation,
                }
                for r in group
            ],
            indent=2,
        )

        try:
            user_msg = CONTRADICTION_DETECTION_USER.format(
                project_topic=topic,
                paper_ids_json=paper_ids_json,
                matrix_rows_json=rows_json,
            )
            result = await provider.complete_structured(
                messages=[{"role": "user", "content": user_msg}],
                system=CONTRADICTION_DETECTION_SYSTEM,
                schema={"type": "object", "properties": {"conflicts": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "paper_a_id": {"type": "string"},
                        "paper_b_id": {"type": "string"},
                        "shared_context": {"type": "string"},
                        "claim_a": {"type": "string"},
                        "claim_b": {"type": "string"},
                        "possible_explanation": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["title", "description", "paper_a_id", "paper_b_id"],
                }}}},
                tool_name="conflict_detection",
                max_tokens=2000,
            )
            detected = result.get("conflicts", [])
        except Exception as exc:
            logger.warning("Conflict detection failed for group '%s': %s", shared_context[:40], exc)
            continue

        # 6. Validate paper IDs and persist
        for c in detected:
            try:
                pa_id = UUID(c["paper_a_id"])
                pb_id = UUID(c["paper_b_id"])
            except (ValueError, KeyError):
                logger.warning("Invalid paper IDs in conflict: %s", c)
                continue

            if pa_id not in valid_pp_ids or pb_id not in valid_pp_ids:
                logger.warning("Conflict references invalid project_paper IDs, skipping")
                continue

            conflicts.append({
                "title": c.get("title", "Potential conflict"),
                "description": c.get("description", ""),
                "paper_a_id": pa_id,
                "paper_b_id": pb_id,
                "shared_context": c.get("shared_context", shared_context),
                "claim_a": c.get("claim_a"),
                "claim_b": c.get("claim_b"),
                "possible_explanation": c.get("possible_explanation"),
                "confidence": c.get("confidence", "medium"),
            })

    # 7. Persist to DB
    if conflicts:
        await _persist_conflicts(db, project_id, conflicts)

    return _serialize_conflicts(conflicts)


async def _persist_conflicts(
    db: AsyncSession,
    project_id: UUID,
    conflicts: list[dict],
) -> None:
    """Delete old conflicts for project, insert new ones."""
    await db.execute(
        delete(ConflictingFinding).where(ConflictingFinding.project_id == project_id)
    )
    for c in conflicts:
        finding = ConflictingFinding(
            project_id=project_id,
            title=c["title"],
            description=c["description"],
            paper_a_id=c["paper_a_id"],
            paper_b_id=c["paper_b_id"],
            shared_context=c.get("shared_context"),
            claim_a=c.get("claim_a"),
            claim_b=c.get("claim_b"),
            possible_explanation=c.get("possible_explanation"),
            confidence=c.get("confidence", "medium"),
        )
        db.add(finding)
    await db.commit()


def _serialize_conflicts(conflicts: list[dict]) -> list[dict]:
    """Convert UUID fields to strings for JSON serialization."""
    return [
        {k: str(v) if isinstance(v, UUID) else v for k, v in c.items()}
        for c in conflicts
    ]


async def get_by_project(
    db: AsyncSession,
    project_id: UUID,
) -> list[ConflictingFinding]:
    """Load conflicts for a project."""
    stmt = (
        select(ConflictingFinding)
        .where(ConflictingFinding.project_id == project_id)
        .order_by(ConflictingFinding.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.services.conflict_detection import detect_and_persist_conflicts, get_by_project; print('OK')"`
Expected: `OK`

---

### Task 3: Add RAG-aware Gap Prompts

**Files:**
- Modify: `app/ai/prompts.py:217-244`

- [ ] **Step 1: Add new prompt variants after existing GAP_ANALYSIS prompts**

Add after line 244 (after `GAP_ANALYSIS_USER`):

```python
GAP_ANALYSIS_CHUNK_SYSTEM = """\
You are a research gap analyst. Identify genuine research gaps by comparing
the literature matrix rows AND the relevant full-text sections provided.

Rules:
- A gap must be supported by specific papers from the matrix. Empty evidence is not allowed.
- Full-text sections provide richer context for identifying limitations and missing work.
- Compare methods, datasets, domains, results, and limitations across papers.
- Do not produce generic "future work" gaps. Each gap must explain what specific
  papers reveal about the absence or limitation.
- Look for: datasets not studied, languages not covered, methods not compared,
  populations not included, metrics not reported.
- Return between 2 and 5 gaps. Quality over quantity.
- evidence_paper_ids must contain only project_paper_ids from the input list.
"""

GAP_ANALYSIS_CHUNK_USER = """\
Project topic: {project_topic}

Saved paper IDs available for evidence (use only these):
{paper_ids_json}

Literature matrix rows:
{matrix_rows_json}

Relevant sections from full-text papers:
{chunk_context}

Identify evidence-backed research gaps.
"""
```

- [ ] **Step 2: Verify prompts import**

Run: `python -c "from app.ai.prompts import GAP_ANALYSIS_CHUNK_SYSTEM, GAP_ANALYSIS_CHUNK_USER; print('OK')"`
Expected: `OK`

---

### Task 4: Rewrite gap_analysis_node

**Files:**
- Modify: `app/agents/nodes.py:348-386`

- [ ] **Step 1: Update imports at top of nodes.py**

Add to the existing imports (after line 33):

```python
from app.services.gap_detection import upsert_gaps, validate_evidence_ids
```

Add to the prompt imports (after line 18):

```python
    GAP_ANALYSIS_CHUNK_SYSTEM,
    GAP_ANALYSIS_CHUNK_USER,
```

- [ ] **Step 2: Rewrite gap_analysis_node**

Replace lines 348-386 with:

```python
# ── Node 4: Gap Analysis ───────────────────────────────────────────────────

_MAX_GAP_CHUNKS = 30
_MAX_CHUNKS_PER_GAP_PAPER = 5
_MIN_MATRIX_ROWS_FOR_GAPS = 5


async def gap_analysis_node(state: ResearchState, db) -> dict:
    """Detect research gaps from matrix rows + RAG chunks, persist to DB."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db.models import LiteratureMatrixRow, ProjectPaper

    if not state.project_id:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": ["No project_id in state"],
        }

    # 1. Load matrix rows from DB
    stmt = select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.project_id == state.project_id
    )
    matrix_rows = (await db.execute(stmt)).scalars().all()

    if not matrix_rows:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": ["No matrix rows for gap analysis"],
        }

    if len(matrix_rows) < _MIN_MATRIX_ROWS_FOR_GAPS:
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": [
                f"INSUFFICIENT_MATRIX: need >= {_MIN_MATRIX_ROWS_FOR_GAPS} matrix rows, got {len(matrix_rows)}"
            ],
        }

    # 2. RAG retrieval for gap-relevant chunks
    query = f"research gaps limitations missing {state.user_topic or ''}"
    all_chunks = await retrieve_project_evidence(db, state.project_id, query, limit=_MAX_GAP_CHUNKS)

    chunks_by_paper: dict[UUID, list[RetrievedChunk]] = {}
    for chunk in all_chunks:
        chunks_by_paper.setdefault(chunk.project_paper_id, []).append(chunk)

    # 3. Load valid project_paper_ids for evidence validation
    pp_stmt = select(ProjectPaper.id).where(
        ProjectPaper.project_id == state.project_id,
        ProjectPaper.status == "saved",
    )
    valid_pp_ids = set((await db.execute(pp_stmt)).scalars().all())

    # 4. Build prompt
    safe_rows = _rows_to_json_safe(
        [
            {
                "project_paper_id": r.project_paper_id,
                "research_problem": r.research_problem,
                "method": r.method,
                "dataset_or_context": r.dataset_or_context,
                "key_result": r.key_result,
                "limitation": r.limitation,
            }
            for r in matrix_rows
        ]
    )
    paper_ids_json = json.dumps([str(r.project_paper_id) for r in matrix_rows])

    # Build chunk context from all retrieved chunks
    chunk_parts: list[str] = []
    total_chars = 0
    for pp_id, chunks in chunks_by_paper.items():
        for c in chunks[:_MAX_CHUNKS_PER_GAP_PAPER]:
            label = c.section_label or c.content_type or "section"
            block = f"---{label} (paper {str(pp_id)[:8]})---\n{c.chunk_text}"
            if total_chars + len(block) > _MAX_CHUNK_CONTEXT_CHARS:
                break
            chunk_parts.append(block)
            total_chars += len(block)
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text sections available."

    try:
        user_msg = GAP_ANALYSIS_CHUNK_USER.format(
            project_topic=state.user_topic,
            paper_ids_json=paper_ids_json,
            matrix_rows_json=json.dumps(safe_rows, indent=2),
            chunk_context=chunk_context,
        )
        provider = get_provider()
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=GAP_ANALYSIS_CHUNK_SYSTEM,
            schema=GapListOutput.model_json_schema(),
            tool_name="gap_analysis",
            max_tokens=4000,
        )
        raw_gaps = result.get("gaps", [])
    except Exception as exc:
        logger.exception("Gap analysis failed")
        return {
            "current_node": "gap_analysis",
            "gap_status": "failed",
            "errors": [f"Gap analysis failed: {exc}"],
        }

    # 5. Validate evidence_paper_ids and filter gaps
    validated_gaps: list[dict] = []
    for gap in raw_gaps:
        raw_ids = gap.get("evidence_paper_ids", [])
        try:
            ev_ids = [UUID(i) if isinstance(i, str) else i for i in raw_ids]
        except (ValueError, TypeError):
            logger.warning("Gap '%s' has invalid evidence IDs, skipping", gap.get("title", ""))
            continue

        valid_ids = [eid for eid in ev_ids if eid in valid_pp_ids]
        if not valid_ids:
            logger.warning("Gap '%s' has no valid evidence after filtering, skipping", gap.get("title", ""))
            continue

        validated_gaps.append({
            "title": gap.get("title", "Untitled gap"),
            "description": gap.get("description", ""),
            "suggested_direction": gap.get("suggested_direction", ""),
            "evidence_summary": gap.get("evidence_summary", ""),
            "confidence": gap.get("confidence", "medium"),
            "evidence": [
                {
                    "project_paper_id": eid,
                    "evidence_type": "limitation",
                    "note": gap.get("evidence_summary", ""),
                }
                for eid in valid_ids
            ],
        })

    # 6. Persist to DB
    gap_status = "completed"
    if validated_gaps:
        try:
            saved_count = await upsert_gaps(db, state.project_id, validated_gaps)
            logger.info("Persisted %d gaps for project %s", saved_count, state.project_id)
        except Exception as exc:
            logger.error("Failed to persist gaps: %s", exc)
            gap_status = "failed"

    return {
        "gaps": _rows_to_json_safe(validated_gaps),
        "gap_status": gap_status,
        "current_node": "gap_analysis",
    }
```

- [ ] **Step 3: Verify the file compiles**

Run: `python -c "from app.agents.nodes import gap_analysis_node; print('OK')"`
Expected: `OK`

---

### Task 5: Add conflict_detection_node

**Files:**
- Modify: `app/agents/nodes.py` (add after gap_analysis_node)

- [ ] **Step 1: Add the conflict_detection_node**

Add after the `gap_analysis_node` function (after the new Task 4 code):

```python
# ── Node 4b: Conflict Detection ────────────────────────────────────────────


async def conflict_detection_node(state: ResearchState, db) -> dict:
    """Detect potential conflicting findings from matrix rows."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    if not state.project_id:
        return {
            "current_node": "conflict_detection",
            "conflict_status": "failed",
            "errors": ["No project_id in state"],
        }

    try:
        conflicts = await detect_and_persist_conflicts(
            db, state.project_id, state.user_topic or ""
        )
    except Exception as exc:
        logger.exception("Conflict detection failed")
        return {
            "current_node": "conflict_detection",
            "conflict_status": "failed",
            "errors": [f"Conflict detection failed: {exc}"],
        }

    return {
        "conflicts": conflicts,
        "conflict_status": "completed",
        "current_node": "conflict_detection",
    }
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.agents.nodes import conflict_detection_node; print('OK')"`
Expected: `OK`

---

### Task 6: Update Graph

**Files:**
- Modify: `app/agents/graph.py`

- [ ] **Step 1: Add import for conflict_detection_node**

Update the imports at line 15-23:

```python
from app.agents.nodes import (
    citation_validator_node,
    conflict_detection_node,
    gap_analysis_node,
    matrix_extraction_node,
    query_planner_node,
    review_writer_node,
    save_screened_node,
    search_agent_node,
)
```

- [ ] **Step 2: Add node and update edges**

In `build_research_graph()`, add the node (after line 59):

```python
    graph.add_node("conflict_detection", _wrap(conflict_detection_node))
```

Update edges (replace lines 68-70):

```python
    graph.add_edge("matrix_extraction", "gap_analysis")
    graph.add_edge("gap_analysis", "conflict_detection")
    graph.add_edge("conflict_detection", "review_writer")
```

(Remove the old `graph.add_edge("gap_analysis", "review_writer")` line.)

- [ ] **Step 3: Verify graph compiles**

Run: `python -c "from app.agents.graph import build_research_graph; print('OK')"`
Expected: `OK`

---

### Task 7: Create Gap Schemas and Router

**Files:**
- Create: `app/schemas/gaps.py`
- Create: `app/routers/gaps.py`

- [ ] **Step 1: Create gap schemas**

```python
# app/schemas/gaps.py
"""Pydantic models for gap API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateGapsRequest(BaseModel):
    max_gaps: int = Field(default=5, ge=1, le=10)
    include_low_confidence: bool = False


class GapEvidenceResponse(BaseModel):
    project_paper_id: str
    title: str = ""
    evidence_type: str
    note: str


class GapResponse(BaseModel):
    id: str
    title: str
    description: str
    suggested_direction: str
    evidence_summary: str
    confidence: str
    evidence: list[GapEvidenceResponse] = Field(default_factory=list)


class GapListResponse(BaseModel):
    items: list[GapResponse]
    total: int
```

- [ ] **Step 2: Create gaps router**

```python
# app/routers/gaps.py
"""REST endpoints for research gap analysis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.nodes import gap_analysis_node
from app.agents.state import ResearchState
from app.core.security import get_current_user
from app.db.models import LiteratureMatrixRow, Project, ProjectPaper, ResearchGap, User
from app.db.session import get_db
from app.schemas.gaps import GapEvidenceResponse, GapListResponse, GapResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gaps"])


@router.post("/{project_id}/gaps:generate", response_model=GapListResponse)
async def generate_gaps(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GapListResponse:
    """Generate research gaps from matrix rows."""
    import uuid

    pid = uuid.UUID(project_id)

    # Verify ownership
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check matrix row count
    matrix_count = (
        await db.execute(
            select(func.count()).select_from(LiteratureMatrixRow).where(
                LiteratureMatrixRow.project_id == pid
            )
        )
    ).scalar()
    if matrix_count < 5:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_MATRIX",
                "message": f"Need >= 5 matrix rows, got {matrix_count}",
                "details": {"current_matrix_rows": matrix_count},
            },
        )

    # Build state and run node
    state = ResearchState(
        project_id=pid,
        user_id=user.id,
        user_topic=project.topic,
        research_question=project.research_question,
    )

    result = await gap_analysis_node(state, db)

    if result.get("gap_status") == "failed":
        errors = result.get("errors", [])
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "GAP_GENERATION_FAILED", "message": "; ".join(errors)},
        )

    # Load persisted gaps with evidence
    gaps = await _load_gaps_with_evidence(db, pid)
    return GapListResponse(items=gaps, total=len(gaps))


@router.get("/{project_id}/gaps", response_model=GapListResponse)
async def list_gaps(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GapListResponse:
    """List gaps for a project."""
    import uuid

    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    gaps = await _load_gaps_with_evidence(db, pid)
    return GapListResponse(items=gaps, total=len(gaps))


@router.delete("/{project_id}/gaps/{gap_id}")
async def remove_gap(
    project_id: str,
    gap_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Delete a single gap."""
    import uuid

    pid = uuid.UUID(project_id)
    gid = uuid.UUID(gap_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    from app.services.gap_detection import delete_gap

    deleted = await delete_gap(db, pid, gid)
    if not deleted:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Gap not found")

    return {"deleted": True}


async def _load_gaps_with_evidence(db: AsyncSession, project_id) -> list[GapResponse]:
    """Load gaps and format as GapResponse with evidence."""
    from app.db.models import GapEvidence, Paper

    stmt = (
        select(ResearchGap)
        .options(selectinload(ResearchGap.evidence_entries))
        .where(ResearchGap.project_id == project_id)
        .order_by(ResearchGap.created_at.desc())
    )
    gaps = (await db.execute(stmt)).scalars().all()

    result = []
    for gap in gaps:
        evidence = []
        for ev in gap.evidence_entries:
            # Load paper title for evidence
            pp = (
                await db.execute(
                    select(ProjectPaper)
                    .where(ProjectPaper.id == ev.project_paper_id)
                )
            ).scalar_one_or_none()
            paper_title = ""
            if pp:
                paper = (
                    await db.execute(select(Paper).where(Paper.id == pp.paper_id))
                ).scalar_one_or_none()
                if paper:
                    paper_title = paper.title

            evidence.append(
                GapEvidenceResponse(
                    project_paper_id=str(ev.project_paper_id),
                    title=paper_title,
                    evidence_type=ev.evidence_type,
                    note=ev.note,
                )
            )

        result.append(
            GapResponse(
                id=str(gap.id),
                title=gap.title,
                description=gap.description,
                suggested_direction=gap.suggested_direction,
                evidence_summary=gap.evidence_summary,
                confidence=gap.confidence,
                evidence=evidence,
            )
        )

    return result
```

- [ ] **Step 3: Verify files compile**

Run: `python -c "from app.schemas.gaps import GapListResponse; from app.routers.gaps import router; print('OK')"`
Expected: `OK`

---

### Task 8: Create Conflict Schemas and Router

**Files:**
- Create: `app/schemas/conflicts.py`
- Create: `app/routers/conflicts.py`

- [ ] **Step 1: Create conflict schemas**

```python
# app/schemas/conflicts.py
"""Pydantic models for conflict API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConflictResponse(BaseModel):
    id: str
    title: str
    description: str
    paper_a_id: str
    paper_a_title: str = ""
    paper_b_id: str
    paper_b_title: str = ""
    shared_context: str | None = None
    claim_a: str | None = None
    claim_b: str | None = None
    possible_explanation: str | None = None
    confidence: str


class ConflictListResponse(BaseModel):
    items: list[ConflictResponse]
    total: int
```

- [ ] **Step 2: Create conflicts router**

```python
# app/routers/conflicts.py
"""REST endpoints for conflict detection."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.nodes import conflict_detection_node
from app.agents.state import ResearchState
from app.core.security import get_current_user
from app.db.models import ConflictingFinding, LiteratureMatrixRow, Paper, Project, ProjectPaper, User
from app.db.session import get_db
from app.schemas.conflicts import ConflictListResponse, ConflictResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conflicts"])


@router.post("/{project_id}/conflicts:generate", response_model=ConflictListResponse)
async def generate_conflicts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConflictListResponse:
    """Generate potential conflicting findings from matrix rows."""
    import uuid

    pid = uuid.UUID(project_id)

    # Verify ownership
    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check matrix row count
    matrix_count = (
        await db.execute(
            select(func.count()).select_from(LiteratureMatrixRow).where(
                LiteratureMatrixRow.project_id == pid
            )
        )
    ).scalar()
    if matrix_count < 4:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_MATRIX",
                "message": f"Need >= 4 matrix rows for conflict detection, got {matrix_count}",
                "details": {"current_matrix_rows": matrix_count},
            },
        )

    # Build state and run node
    state = ResearchState(
        project_id=pid,
        user_id=user.id,
        user_topic=project.topic,
        research_question=project.research_question,
    )

    result = await conflict_detection_node(state, db)

    if result.get("conflict_status") == "failed":
        errors = result.get("errors", [])
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "CONFLICT_DETECTION_FAILED", "message": "; ".join(errors)},
        )

    # Load persisted conflicts
    conflicts = await _load_conflicts(db, pid)
    return ConflictListResponse(items=conflicts, total=len(conflicts))


@router.get("/{project_id}/conflicts", response_model=ConflictListResponse)
async def list_conflicts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConflictListResponse:
    """List conflicts for a project."""
    import uuid

    pid = uuid.UUID(project_id)

    project = (
        await db.execute(select(Project).where(Project.id == pid, Project.owner_id == user.id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Project not found")

    conflicts = await _load_conflicts(db, pid)
    return ConflictListResponse(items=conflicts, total=len(conflicts))


async def _load_conflicts(db: AsyncSession, project_id) -> list[ConflictResponse]:
    """Load conflicts and format as ConflictResponse."""
    stmt = (
        select(ConflictingFinding)
        .where(ConflictingFinding.project_id == project_id)
        .order_by(ConflictingFinding.created_at.desc())
    )
    findings = (await db.execute(stmt)).scalars().all()

    result = []
    for f in findings:
        # Load paper titles
        pa_title = await _get_paper_title(db, f.paper_a_id)
        pb_title = await _get_paper_title(db, f.paper_b_id)

        result.append(
            ConflictResponse(
                id=str(f.id),
                title=f.title,
                description=f.description,
                paper_a_id=str(f.paper_a_id),
                paper_a_title=pa_title,
                paper_b_id=str(f.paper_b_id),
                paper_b_title=pb_title,
                shared_context=f.shared_context,
                claim_a=f.claim_a,
                claim_b=f.claim_b,
                possible_explanation=f.possible_explanation,
                confidence=f.confidence,
            )
        )

    return result


async def _get_paper_title(db: AsyncSession, project_paper_id) -> str:
    """Get paper title from project_paper_id."""
    pp = (
        await db.execute(select(ProjectPaper).where(ProjectPaper.id == project_paper_id))
    ).scalar_one_or_none()
    if not pp:
        return ""
    paper = (await db.execute(select(Paper).where(Paper.id == pp.paper_id))).scalar_one_or_none()
    return paper.title if paper else ""
```

- [ ] **Step 3: Verify files compile**

Run: `python -c "from app.schemas.conflicts import ConflictListResponse; from app.routers.conflicts import router; print('OK')"`
Expected: `OK`

---

### Task 9: Register Routers in main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add router imports and registration**

Add imports (check existing imports first):

```python
from app.routers.gaps import router as gaps_router
from app.routers.conflicts import router as conflicts_router
```

Add router registration (after existing `app.include_router` calls):

```python
app.include_router(gaps_router, prefix="/api/projects")
app.include_router(conflicts_router, prefix="/api/projects")
```

- [ ] **Step 2: Verify main.py compiles**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK`

---

### Task 10: Write Tests for Gap Analysis

**Files:**
- Create: `tests/test_gap_analysis.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for RAG-aware gap_analysis_node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import gap_analysis_node
from app.agents.state import ResearchState
from app.services.hybrid_retrieval import RetrievedChunk


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_chunk(project_paper_id=None, section_label="limitation", chunk_text="English only evaluation."):
    return RetrievedChunk(
        project_paper_id=project_paper_id or uuid4(),
        paper_id=uuid4(),
        chunk_id=uuid4(),
        title="Test Paper",
        chunk_text=chunk_text,
        section_label=section_label,
        section_path=None,
        chunk_index=0,
        content_type="limitation",
        page_start=1,
        page_end=2,
        content_hash=None,
        score=0.8,
        keyword_score=0.4,
        vector_score=0.4,
    )


def _make_matrix_row(pp_id=None, method="RAG", dataset="PubMedQA", limitation="English only"):
    row = SimpleNamespace()
    row.project_paper_id = pp_id or uuid4()
    row.research_problem = "Medical QA"
    row.method = method
    row.dataset_or_context = dataset
    row.key_result = "Improved accuracy"
    row.limitation = limitation
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
        # Fallback: empty result
        r = MagicMock()
        r.scalars.return_value.all.return_value = []
        return r

    db.execute = mock_execute
    return db


def _result_with_rows(rows):
    """Create a mock DB result that returns `rows` from scalars().all()."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gap_analysis_no_matrix_rows():
    state = _make_state()
    db = _mock_db_sequential([_result_with_rows([])])

    result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "No matrix rows" in result["errors"][0]


@pytest.mark.asyncio
async def test_gap_analysis_insufficient_matrix_rows():
    state = _make_state()
    rows = [_make_matrix_row() for _ in range(3)]  # < 5
    db = _mock_db_sequential([_result_with_rows(rows)])

    result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "INSUFFICIENT_MATRIX" in result["errors"][0]


@pytest.mark.asyncio
async def test_gap_analysis_generates_and_persists():
    pp_id = uuid4()
    state = _make_state()
    rows = [_make_matrix_row(pp_id=pp_id) for _ in range(5)]
    chunk = _make_chunk(project_paper_id=pp_id)

    # 1st call: matrix rows, 2nd call: valid project_paper_ids
    db = _mock_db_sequential([
        _result_with_rows(rows),
        _result_with_rows([pp_id]),
    ])

    with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[chunk]):
        with patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=2):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "gaps": [
                    {
                        "title": "Low-resource language evaluation",
                        "description": "Most papers evaluate English only.",
                        "evidence_paper_ids": [str(pp_id)],
                        "evidence_summary": "Papers report English-only evaluation.",
                        "suggested_direction": "Evaluate on Vietnamese datasets.",
                        "confidence": "medium",
                    }
                ]
            }
            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "completed"
    assert len(result["gaps"]) == 1
    assert "Low-resource" in result["gaps"][0]["title"]


@pytest.mark.asyncio
async def test_gap_analysis_filters_invalid_evidence():
    state = _make_state()
    valid_pp_id = uuid4()
    invalid_pp_id = uuid4()
    rows = [_make_matrix_row(pp_id=valid_pp_id) for _ in range(5)]

    # 1st call: matrix rows, 2nd call: only valid_pp_id is a saved project_paper
    db = _mock_db_sequential([
        _result_with_rows(rows),
        _result_with_rows([valid_pp_id]),
    ])

    with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
        with patch("app.agents.nodes.upsert_gaps", new_callable=AsyncMock, return_value=1):
            mock_provider = AsyncMock()
            mock_provider.complete_structured.return_value = {
                "gaps": [
                    {
                        "title": "Gap with valid evidence",
                        "description": "Test",
                        "evidence_paper_ids": [str(valid_pp_id)],
                        "evidence_summary": "Valid",
                        "suggested_direction": "Test",
                        "confidence": "medium",
                    },
                    {
                        "title": "Gap with invalid evidence",
                        "description": "Test",
                        "evidence_paper_ids": [str(invalid_pp_id)],
                        "evidence_summary": "Invalid",
                        "suggested_direction": "Test",
                        "confidence": "medium",
                    },
                ]
            }
            with patch("app.agents.nodes.get_provider", return_value=mock_provider):
                result = await gap_analysis_node(state, db)

    # Gap with invalid evidence should be filtered out; only valid one remains
    assert result["gap_status"] == "completed"
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["title"] == "Gap with valid evidence"


@pytest.mark.asyncio
async def test_gap_analysis_llm_failure():
    state = _make_state()
    rows = [_make_matrix_row() for _ in range(5)]
    # 1st call: matrix rows, 2nd call: valid project_paper_ids
    db = _mock_db_sequential([
        _result_with_rows(rows),
        _result_with_rows([]),
    ])

    with patch("app.agents.nodes.retrieve_project_evidence", new_callable=AsyncMock, return_value=[]):
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        with patch("app.agents.nodes.get_provider", return_value=mock_provider):
            result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "Gap analysis failed" in result["errors"][0]


@pytest.mark.asyncio
async def test_gap_analysis_no_project_id():
    state = ResearchState(project_id=None, user_id=uuid4())
    db = AsyncMock()

    result = await gap_analysis_node(state, db)

    assert result["gap_status"] == "failed"
    assert "No project_id" in result["errors"][0]
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_gap_analysis.py -v`
Expected: All tests pass

---

### Task 11: Write Tests for Conflict Detection

**Files:**
- Create: `tests/test_conflict_detection.py`

- [ ] **Step 1: Create test file**

```python
"""Tests for conflict_detection_node."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.nodes import conflict_detection_node
from app.agents.state import ResearchState


def _make_matrix_row(pp_id=None, method="RAG", dataset="PubMedQA", key_result="Improved accuracy"):
    row = SimpleNamespace()
    row.project_paper_id = pp_id or uuid4()
    row.research_problem = "Medical QA"
    row.method = method
    row.dataset_or_context = dataset
    row.key_result = key_result
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
    """Create a mock DB result that returns `rows` from scalars().all()."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


@pytest.mark.asyncio
async def test_conflict_detection_too_few_rows():
    """Skip conflict detection when < 4 matrix rows."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    state = _make_state()
    rows = [_make_matrix_row() for _ in range(3)]
    db = _mock_db_sequential([_result_with_rows(rows)])

    result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []


@pytest.mark.asyncio
async def test_conflict_detection_shared_method():
    """Detect conflict when two papers share same method but opposing results."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG", key_result="Improved accuracy by 10%"),
        _make_matrix_row(pp_id=pp_b, method="RAG", key_result="No significant improvement"),
        _make_matrix_row(method="BM25", key_result="Baseline results"),
        _make_matrix_row(method="Dense retrieval", key_result="Moderate improvement"),
    ]

    # 1st call: matrix rows, 2nd call: valid project_paper_ids
    db = _mock_db_sequential([
        _result_with_rows(rows),
        _result_with_rows([pp_a, pp_b]),
    ])

    with patch("app.services.conflict_detection.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.return_value = {
            "conflicts": [
                {
                    "title": "Opposing findings on RAG accuracy",
                    "description": "Paper A reports improvement while Paper B reports no improvement.",
                    "paper_a_id": str(pp_a),
                    "paper_b_id": str(pp_b),
                    "shared_context": "RAG method",
                    "claim_a": "Improved accuracy by 10%",
                    "claim_b": "No significant improvement",
                    "possible_explanation": "Different evaluation settings",
                    "confidence": "medium",
                }
            ]
        }
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert len(result) == 1
    assert "Opposing" in result[0]["title"]


@pytest.mark.asyncio
async def test_conflict_detection_no_shared_context():
    """No conflicts when no papers share method or dataset."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    state = _make_state()
    rows = [
        _make_matrix_row(method="RAG", dataset="PubMedQA"),
        _make_matrix_row(method="BM25", dataset="Natural Questions"),
        _make_matrix_row(method="Dense retrieval", dataset="SQuAD"),
        _make_matrix_row(method="Sparse retrieval", dataset="MS MARCO"),
    ]

    # 1st call: matrix rows, 2nd call: valid project_papers (empty)
    db = _mock_db_sequential([
        _result_with_rows(rows),
        _result_with_rows([]),
    ])

    result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []


@pytest.mark.asyncio
async def test_conflict_detection_llm_failure_graceful():
    """LLM failure doesn't crash the workflow."""
    from app.services.conflict_detection import detect_and_persist_conflicts

    pp_a = uuid4()
    pp_b = uuid4()
    state = _make_state()

    rows = [
        _make_matrix_row(pp_id=pp_a, method="RAG"),
        _make_matrix_row(pp_id=pp_b, method="RAG"),
        _make_matrix_row(method="BM25"),
        _make_matrix_row(method="Dense"),
    ]

    # 1st call: matrix rows, 2nd call: valid project_papers
    db = _mock_db_sequential([
        _result_with_rows(rows),
        _result_with_rows([pp_a, pp_b]),
    ])

    with patch("app.services.conflict_detection.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.complete_structured.side_effect = Exception("LLM timeout")
        mock_get_provider.return_value = mock_provider

        result = await detect_and_persist_conflicts(db, state.project_id, state.user_topic)

    assert result == []  # graceful empty result
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_conflict_detection.py -v`
Expected: All tests pass

---

### Task 12: Run All Tests and Lint

- [ ] **Step 1: Run linter**

Run: `ruff check app/services/gap_detection.py app/services/conflict_detection.py app/agents/nodes.py app/agents/graph.py app/ai/prompts.py app/routers/gaps.py app/routers/conflicts.py app/schemas/gaps.py app/schemas/conflicts.py`
Expected: No errors

- [ ] **Step 2: Run all existing tests**

Run: `pytest tests/ -v`
Expected: All pass (existing + new)

- [ ] **Step 3: Commit**

```bash
git add app/services/gap_detection.py app/services/conflict_detection.py \
  app/ai/prompts.py app/agents/nodes.py app/agents/graph.py \
  app/schemas/gaps.py app/schemas/conflicts.py \
  app/routers/gaps.py app/routers/conflicts.py app/main.py \
  tests/test_gap_analysis.py tests/test_conflict_detection.py
git commit -m "feat: gap analysis with RAG + conflict detection with DB persistence"
```
