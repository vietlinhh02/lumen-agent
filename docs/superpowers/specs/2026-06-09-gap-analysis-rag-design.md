# Gap Analysis + Conflict Detection with RAG

## Problem

The current `gap_analysis_node` (`app/agents/nodes.py:348-386`) only uses `state.matrix_rows` as input — no RAG chunks, no DB persistence, no evidence validation. Gaps are returned in-memory and never stored. `evidence_paper_ids` are LLM-generated but never verified against actual `project_papers`. Conflict detection (contradiction flagging) is not implemented at all.

## Current State

- `gap_analysis_node`: takes matrix rows from state, sends JSON to LLM, returns in-memory gaps
- No DB session — node can't persist or load from DB
- No RAG — no `retrieve_project_evidence` call for gap-relevant chunks
- No evidence validation — `evidence_paper_ids` not checked against project_papers
- No conflict detection node exists
- `ResearchGap`, `GapEvidence`, `ConflictingFinding` models exist in `app/db/models.py`
- `GapOutput`, `GapListOutput`, `ConflictOutput`, `ConflictListOutput` schemas exist in `app/ai/structured_outputs.py`
- `CONTRADICTION_DETECTION_*` prompts exist in `app/ai/prompts.py`
- No gap or conflict routers exist

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| Gap node DB access | Pass `db` session | Same pattern as matrix_extraction_node |
| RAG for gaps | Single broad `retrieve_project_evidence` call | Matches matrix_extraction pattern; query = "research gaps limitations missing {topic}" |
| RAG for conflicts | Not needed | Conflicts compare matrix rows directly (method, dataset, key_result) |
| Gap persistence | Delete old gaps for project, insert fresh | Simple; supports regeneration without duplicates |
| Conflict persistence | Same delete-then-insert pattern | Consistent with gaps |
| Evidence validation | Check each evidence_paper_id exists in project_papers with status='saved' | Prevents hallucinated IDs from persisting |
| Minimum matrix rows | 5 for gaps, 4 for conflicts | Per api-design.md INSUFFICIENT_MATRIX error |
| Graph order | matrix_extraction → gap_analysis → conflict_detection → review_writer | Conflicts need matrix rows; review needs gaps |

## Architecture

### Data Flow

```
matrix_rows (DB) ──┐
                   ├──→ gap_analysis_node ──→ research_gaps + gap_evidence (DB)
RAG chunks ────────┘

matrix_rows (DB) ──→ conflict_detection_node ──→ conflicting_findings (DB)
```

### Graph Topology

```
query_planner → search_agent → save_screened → matrix_extraction
→ gap_analysis → conflict_detection → review_writer → citation_validator → END
```

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/gap_detection.py` | CRUD: upsert_gaps, get_by_project, delete_gap |
| `app/services/conflict_detection.py` | CRUD: detect_and_persist_conflicts, get_by_project |
| `app/routers/gaps.py` | POST /gaps:generate, GET /gaps, DELETE /gaps/{gap_id} |
| `app/routers/conflicts.py` | POST /conflicts:generate, GET /conflicts |
| `app/schemas/gaps.py` | Pydantic request/response models for gap endpoints |
| `app/schemas/conflicts.py` | Pydantic request/response models for conflict endpoints |
| `tests/test_gap_analysis.py` | Unit tests for gap_analysis_node |
| `tests/test_conflict_detection.py` | Unit tests for conflict_detection_node |

## Files to Modify

| File | Change |
|------|--------|
| `app/agents/nodes.py:348-386` | Rewrite gap_analysis_node: add db param, RAG, DB persistence |
| `app/agents/nodes.py` | Add conflict_detection_node after gap_analysis_node |
| `app/ai/prompts.py:217-244` | Add GAP_ANALYSIS_CHUNK_SYSTEM/USER prompts |
| `app/agents/graph.py:59` | Add conflict_detection node, update edge chain |
| `app/main.py` | Register gaps and conflicts routers |

## Detailed Design

### 1. Gap Detection Service (`app/services/gap_detection.py`)

```python
async def upsert_gaps(db: AsyncSession, project_id: UUID, gaps: list[dict]) -> int:
    """Delete existing gaps for project, insert new ones with evidence.

    Each dict in `gaps` must have:
        - title, description, suggested_direction, evidence_summary: str
        - confidence: 'high' | 'medium' | 'low'
        - evidence: list[{project_paper_id: UUID, evidence_type: str, note: str}]
    Returns count of gaps inserted.
    """

async def get_by_project(db: AsyncSession, project_id: UUID) -> list[ResearchGap]:
    """Load gaps with evidence_entries and project_paper.paper eager-loaded."""

async def delete_gap(db: AsyncSession, project_id: UUID, gap_id: UUID) -> bool:
    """Delete single gap. Returns True if deleted."""
```

### 2. Conflict Detection Service (`app/services/conflict_detection.py`)

```python
async def detect_and_persist_conflicts(db: AsyncSession, project_id: UUID, topic: str) -> list[dict]:
    """Load matrix rows, group by shared method/dataset, detect conflicts via LLM,
    validate paper IDs, persist to conflicting_findings table.
    Returns list of conflict dicts for state.
    """

async def get_by_project(db: AsyncSession, project_id: UUID) -> list[ConflictingFinding]:
    """Load conflicts for a project."""
```

### 3. Gap Analysis Node (rewrite)

```python
async def gap_analysis_node(state: ResearchState, db) -> dict:
    # 1. Load matrix rows from DB
    stmt = select(LiteratureMatrixRow).where(LiteratureMatrixRow.project_id == state.project_id)
    matrix_rows = (await db.execute(stmt)).scalars().all()

    # 2. Validate minimum rows
    if len(matrix_rows) < 5:
        return { "gap_status": "failed", "errors": ["INSUFFICIENT_MATRIX: need >= 5 matrix rows"] }

    # 3. RAG retrieval
    query = f"research gaps limitations missing {state.user_topic}"
    chunks = await retrieve_project_evidence(db, state.project_id, query, limit=30)

    # 4. Group chunks by project_paper_id
    chunks_by_paper = defaultdict(list)
    for chunk in chunks:
        chunks_by_paper[chunk.project_paper_id].append(chunk)

    # 5. Build enriched prompt with matrix rows + chunk context
    # 6. LLM generates gaps
    # 7. Validate evidence_paper_ids against project_papers (status='saved')
    # 8. Remove gaps with no valid evidence
    # 9. Upsert to research_gaps + gap_evidence
    # 10. Return {gaps, gap_status}
```

### 4. Conflict Detection Node (new)

```python
async def conflict_detection_node(state: ResearchState, db) -> dict:
    # 1. Load matrix rows from DB
    # 2. If < 4 rows → skip (return empty, not error)
    # 3. Group rows by shared method or dataset_or_context
    # 4. For groups with 2+ rows: send to LLM with CONTRADICTION_DETECTION_* prompts
    # 5. LLM returns conflicts with paper_a_id, paper_b_id, shared_context, claims
    # 6. Validate both paper_ids exist in project_papers
    # 7. Persist to conflicting_findings table
    # 8. Return {conflicts, conflict_status}
```

### 5. Prompts

Add to `app/ai/prompts.py`:

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

### 6. Graph Update

```python
# In build_research_graph():
graph.add_node("conflict_detection", _wrap(conflict_detection_node))

# Update edges:
graph.add_edge("gap_analysis", "conflict_detection")
graph.add_edge("conflict_detection", "review_writer")
# Remove: graph.add_edge("gap_analysis", "review_writer")
```

### 7. API Endpoints

#### Gaps Router (`app/routers/gaps.py`)

```python
@router.post("/{project_id}/gaps:generate")
async def generate_gaps(project_id, db, user):
    # Verify ownership
    # Check matrix row count >= 5
    # Build state from DB
    # Call gap_analysis_node(state, db)
    # Return gaps

@router.get("/{project_id}/gaps")
async def list_gaps(project_id, db, user):
    # Verify ownership
    # Return get_by_project(db, project_id)

@router.delete("/{project_id}/gaps/{gap_id}")
async def remove_gap(project_id, gap_id, db, user):
    # Verify ownership
    # Return delete_gap(db, project_id, gap_id)
```

#### Conflicts Router (`app/routers/conflicts.py`)

```python
@router.post("/{project_id}/conflicts:generate")
async def generate_conflicts(project_id, db, user):
    # Verify ownership
    # Check matrix row count >= 4
    # Call detect_and_persist_conflicts(db, project_id, topic)
    # Return conflicts

@router.get("/{project_id}/conflicts")
async def list_conflicts(project_id, db, user):
    # Verify ownership
    # Return get_by_project(db, project_id)
```

### 8. Schemas

#### `app/schemas/gaps.py`

```python
class GenerateGapsRequest(BaseModel):
    max_gaps: int = Field(default=5, ge=1, le=10)
    include_low_confidence: bool = False

class GapEvidenceResponse(BaseModel):
    project_paper_id: str
    title: str
    evidence_type: str
    note: str

class GapResponse(BaseModel):
    id: str
    title: str
    description: str
    suggested_direction: str
    evidence_summary: str
    confidence: str
    evidence: list[GapEvidenceResponse]

class GapListResponse(BaseModel):
    items: list[GapResponse]
    total: int
```

#### `app/schemas/conflicts.py`

```python
class ConflictResponse(BaseModel):
    id: str
    title: str
    description: str
    paper_a_id: str
    paper_a_title: str
    paper_b_id: str
    paper_b_title: str
    shared_context: str | None
    claim_a: str | None
    claim_b: str | None
    possible_explanation: str | None
    confidence: str

class ConflictListResponse(BaseModel):
    items: list[ConflictResponse]
    total: int
```

### 9. Tests

#### `tests/test_gap_analysis.py`

- No matrix rows → returns failed status
- Insufficient matrix rows (< 5) → returns INSUFFICIENT_MATRIX error
- With chunks → generates gaps and persists to DB
- Invalid evidence_paper_ids → filtered out
- Partial LLM failure → graceful degradation
- Gap with empty evidence after validation → removed from result

#### `tests/test_conflict_detection.py`

- Too few rows (< 4) → returns empty list, skips
- Shared method with opposing results → detects conflict
- Invalid paper_ids → filtered out
- No shared context → no conflicts generated

## Edge Cases

1. **No matrix rows**: Return `gap_status: "failed"` with `errors: ["No matrix rows for gap analysis"]`
2. **< 5 matrix rows**: Return `gap_status: "failed"` with `errors: ["INSUFFICIENT_MATRIX"]`
3. **No chunks from RAG**: Fall back to matrix-only prompt (like matrix_extraction_node)
4. **LLM returns gaps with invalid evidence_paper_ids**: Filter out those gaps; log warning
5. **All gaps filtered out**: Return `gap_status: "completed"` with empty gaps list
6. **Conflicts: < 4 matrix rows**: Skip conflict detection, return empty (not an error)
7. **LLM timeout on conflict detection**: Return empty conflicts, don't fail the workflow
