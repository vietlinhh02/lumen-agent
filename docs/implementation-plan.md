# Implementation Plan

## Modules to Build/Complete

### 1. Source Adapters (OpenAlex, arXiv)

**What**: Implement `PaperSource` interface for OpenAlex and arXiv academic APIs.

- OpenAlex adapter: query works endpoint, normalize to `RawPaper`
- arXiv adapter: query Atom API, normalize to `RawPaper`
- Wire into `search_agent_node` and `paper_search` service
- Handle rate limits, timeouts, and partial failures
- Source diagnostics in search response

**Files**: `app/sources/openalex.py`, `app/sources/arxiv.py`, `app/agents/nodes.py`

### 2. Literature Matrix CRUD

**What**: Full matrix lifecycle — generate, list, edit, delete.

- `POST /api/projects/{id}/matrix:generate` — AI extraction for saved papers
- `GET /api/projects/{id}/matrix` — list matrix rows
- `PATCH /api/projects/{id}/matrix/{row_id}` — edit cells
- Frontend: table editor with editable cells, confidence badges
- Validate AI output (required fields: research_problem, method, key_result)

**Files**: `app/routers/matrix.py`, `app/services/literature_matrix.py`, `frontend/app/(app)/projects/[id]/matrix/`

### 3. Research Gaps + Conflicting Findings

**What**: Evidence-based gap detection and conflict flagging.

- `POST /api/projects/{id}/gaps:generate` — generate gaps from matrix
- `GET /api/projects/{id}/gaps` — list gaps with evidence
- `DELETE /api/projects/{id}/gaps/{gap_id}` — remove low-quality gaps
- `POST /api/projects/{id}/conflicts:generate` — detect opposing findings
- Reject gaps with empty evidence_paper_ids
- Frontend: gap cards with evidence panels, conflict cards

**Files**: `app/routers/gaps.py`, `app/services/gap_detection.py`, `frontend/app/(app)/projects/[id]/gaps/`

### 4. Report Generation + Citation Guardrail

**What**: Citation-safe literature review export.

- `POST /api/projects/{id}/reports` — generate review with citation IDs
- `GET /api/projects/{id}/reports` — list reports
- `GET /api/projects/{id}/reports/{id}` — get report with references
- `GET /api/projects/{id}/reports/{id}/export` — download Markdown
- Citation validation: reject if any ID not in `project_papers`
- Reference list built from DB metadata, not model text
- Frontend: report preview, citation status, export button

**Files**: `app/routers/reports.py`, `app/services/citation_guardrail.py`, `app/services/report_generation.py`, `frontend/app/(app)/projects/[id]/reports/`

### 5. Knowledge Graph

**What**: Interactive force-directed graph from matrix rows.

- `GET /api/projects/{id}/knowledge-graph` — build graph payload
- Extract methods, datasets, limitations as concept nodes
- Create edges: paper→method, paper→dataset, paper→limitation, paper↔paper (shared concept)
- Frontend: react-force-graph-2d with filters, click-to-inspect, zoom/pan

**Files**: `app/services/knowledge_graph.py`, `app/routers/knowledge_graph.py`, `frontend/app/(app)/projects/[id]/knowledge-map/`

### 6. Enrichment Service

**What**: Backend enrichment after papers are saved.

- Merge metadata from all available sources
- Extract research facets with DeepSeek V4 (method_family, domain, dataset, metric, limitation_type)
- Store in `paper_enrichments` and `paper_facets` tables
- Wire into save flow and agent workflow

**Files**: `app/services/research_enrichment.py`, `app/agents/nodes.py`

### 7. Language Bias Service

**What**: Multilingual search with bias detection.

- Detect query language
- Generate English + original-language query variants
- Language coverage audit in search response
- Frontend: language audit display

**Files**: `app/services/language_bias.py`, `app/agents/nodes.py`

### 8. CI/CD + Deployment

**What**: Automated builds and Coolify deployment.

- Backend Dockerfile
- Frontend Dockerfile
- GitHub Actions: build + push to GHCR on main push
- Coolify deployment config
- Environment variable management

**Files**: `Dockerfile`, `frontend/Dockerfile`, `.github/workflows/build.yml`

### 9. Tests

**What**: Focused tests for core business logic.

- Paper deduplication
- Project ownership checks
- Citation validation (valid + invalid)
- Matrix schema validation
- Gap evidence rejection
- Source adapter error handling
- Frontend: login, project creation, search, save

**Files**: `tests/`, `frontend/__tests__/`

### 10. Polish + Admin

**What**: Error states, loading states, admin endpoints.

- `GET /api/admin/users` — list users
- `PATCH /api/admin/users/{id}` — activate/deactivate
- Agent run audit timeline UI
- Error and loading states for all screens

**Files**: `app/routers/admin.py`, `frontend/app/(app)/admin/`

## Dependency Order

```
1. Source Adapters (no deps)
2. Enrichment Service (no deps)
3. Language Bias Service (no deps)
4. Literature Matrix CRUD (depends on 2)
5. Research Gaps (depends on 4)
6. Knowledge Graph (depends on 4)
7. Report + Citation Guardrail (depends on 4, 5)
8. Tests (depends on 4, 5, 7)
9. CI/CD + Deployment (no code deps)
10. Polish + Admin (depends on all above)
```

## Demo Flow (target: 5-6 minutes)

1. Log in (~15s)
2. Open seeded project (~20s)
3. Search with Semantic Scholar + OpenAlex + arXiv (~30s)
4. Save 10-15 papers (~30s)
5. Generate literature matrix (~60s)
6. Edit one matrix row (~20s)
7. Generate research gaps (~30s)
8. Open gap and show evidence (~20s)
9. Generate literature review (~60s)
10. Show citation validation (~15s)
11. Export Markdown (~10s)
12. Click citation → show saved paper (~15s)
