# Chunk-Aware Matrix Extraction

## Problem

The `matrix_extraction_node` in `app/agents/nodes.py:180-238` currently sends only `title` + `abstract` per paper to the LLM. For papers with ingested full-text PDFs, rich section-level chunks (method, results, limitation) exist in `paper_chunks` but are unused. This produces incomplete extractions, especially for `method`, `key_result`, and `limitation` fields.

## Current State

- Node uses `FACET_EXTRACTION_*` prompts (minimal: title, abstract, topic)
- `MATRIX_EXTRACTION_*` prompts exist at `app/ai/prompts.py:161-184` but are unused
- `MatrixRowOutput` Pydantic model exists at `app/ai/structured_outputs.py:47` but is bypassed
- Node operates on `state.raw_papers` (search results) with `paper_index`, not `project_paper_id` UUIDs
- `hybrid_retrieval.py` can query chunks by project with keyword + vector scoring
- No matrix CRUD endpoints exist; node returns in-memory dicts only

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| Chunk source | `retrieve_project_evidence()` | Uses existing hybrid retrieval with section boosts and relevance ranking |
| Prompt base | `MATRIX_EXTRACTION_*` | Includes authors, year, venue — richer than FACET prompts |
| Output model | `MatrixRowOutput` Pydantic | Has field validators, replaces inline JSON schema |
| Persistence | Auto-save to `literature_matrix_rows` | Node loads from DB, writes to DB — self-contained |
| DB access | Pass `db` session to node | Nodes don't currently use DB; first node to do so |

## Architecture

### Data Flow

```
1. Load saved project_papers from DB (project_id, status='saved')
2. For each paper: load paper metadata (title, authors, year, abstract, venue)
3. Call retrieve_project_evidence(db, project_id, user_topic, limit=40)
4. Group retrieved chunks by project_paper_id → {pp_id: [chunk, ...]}
5. For each paper (up to 20):
   a. Take top 3-5 chunks for this paper (sorted by score)
   b. Build prompt: MATRIX_EXTRACTION + chunk context
   c. Call provider.complete_structured() with MatrixRowOutput schema
   d. Build row dict with project_paper_id UUID
6. Upsert rows to literature_matrix_rows table
7. Return {matrix_rows, matrix_status, current_node}
```

### Prompt Design

```
Project topic: {project_topic}

Paper title: {title}
Authors: {authors}
Year: {year}
Abstract: {abstract}
Venue: {venue}

Relevant sections from the full text:
---method---
{chunk_text_1}

---results---
{chunk_text_2}

---limitation---
{chunk_text_3}

Extract the literature matrix row for this paper.
```

If no chunks are available for a paper, fall back to metadata-only (title + authors + year + abstract + venue).

### DB Schema

Uses existing `literature_matrix_rows` table:

```sql
CREATE TABLE literature_matrix_rows (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  project_paper_id UUID NOT NULL REFERENCES project_papers(id) ON DELETE CASCADE,
  research_problem TEXT,
  method TEXT,
  dataset_or_context TEXT,
  key_result TEXT,
  limitation TEXT,
  contribution TEXT,
  relevance TEXT,
  extraction_confidence TEXT NOT NULL DEFAULT 'medium',
  created_by TEXT NOT NULL CHECK (created_by IN ('ai', 'user')),
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_paper_id)
);
```

### Node Signature Change

Before:
```python
async def matrix_extraction_node(state: ResearchState) -> dict:
```

After:
```python
async def matrix_extraction_node(state: ResearchState, db: AsyncSession) -> dict:
```

This is the first node to receive a DB session. The graph runner (`graph.py`) needs to pass it.

## Files to Modify

| File | Change |
|------|--------|
| `app/agents/nodes.py:180-238` | Rewrite `matrix_extraction_node` |
| `app/ai/prompts.py:161-184` | Add `MATRIX_EXTRACTION_CHUNK_USER` prompt variant |
| `app/agents/graph.py` | Pass `db` session to matrix node |
| `app/agents/state.py` | No change needed (matrix_rows already has project_paper_id) |

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/literature_matrix.py` | CRUD service: get_by_project, upsert_rows, delete |

## Edge Cases

1. **Paper with no chunks**: Fall back to abstract-only extraction (current behavior)
2. **Paper with existing matrix row**: Skip unless `overwrite=True` (future parameter)
3. **Retrieval returns 0 chunks for all papers**: Use metadata-only for all, set `matrix_status='completed'`
4. **LLM extraction fails for one paper**: Log warning, continue with remaining papers
5. **project_paper_id mismatch**: Validate that retrieved chunk's project_paper_id belongs to the project

## Testing

- Unit test: mock `retrieve_project_evidence` + `provider.complete_structured`, verify rows contain `project_paper_id` UUIDs
- Unit test: paper with no chunks falls back to abstract-only
- Unit test: extraction failure for one paper doesn't fail the batch
- Integration test: end-to-end with real DB, verify rows persisted to `literature_matrix_rows`
