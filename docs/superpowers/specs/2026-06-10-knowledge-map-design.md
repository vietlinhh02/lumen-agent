# Knowledge Map — Design Spec

## Problem

The knowledge map feature is specified in docs (frontend-architecture.md,
api-design.md, mvp.md) but 0% implemented. No visualization library is
installed, no `/map` route exists, no backend service or router exists. The
product needs an interactive knowledge graph that lets researchers explore
relationships between papers, methods, datasets, and limitations from their
saved project corpus.

## Goal

Build an interactive knowledge map page at `projects/[id]/map` that:

1. Displays saved papers and their matrix-extracted concepts as a graph.
2. Supports 4 node types: Paper, Method, Dataset, Limitation.
3. Offers multiple layout algorithms the user can switch between.
4. Shows rich detail in a side panel when a node is clicked.
5. Supports filtering by node type, search, zoom/pan, and hover highlighting.

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| Library | Cytoscape.js | Most mature graph library, richest built-in layouts (fcose, cose-bilkent, breadthfirst, concentric, circle, grid), used in academic research, canvas rendering handles 10-100 nodes trivially |
| Rich node detail | Side panel (not canvas overlay) | Cleaner separation — graph stays focused on relationships, panel shows full details. Uses existing shadcn/ui components. |
| Layouts | 6 built-in Cytoscape layouts | fcose (default force-directed), cose-bilkent (clustered force), breadthfirst (hierarchical), concentric, circle, grid |
| Node rendering | Canvas with labels + colors | Cytoscape's native canvas rendering. Custom shapes per type. Labels on nodes. |
| Detail panel | React side panel component | Click node → panel slides in with full metadata. Click background → panel closes. |
| API | GET /api/projects/{id}/knowledge-graph | Already designed in api-design.md. Computed on request from DB. |

## Architecture

### Page Layout

```
┌─────────────────────────────────────────────────┐
│  [Layout: fcose ▼] [Filter: All ▼] [Search]    │ ← Toolbar
├───────────────────────────────┬─────────────────┤
│                               │                 │
│                               │  Node Detail    │
│    Cytoscape Graph Canvas     │  Panel (30%)    │
│    (70% width)                │                 │
│                               │  Paper title    │
│                               │  Abstract...    │
│                               │  Method: RAG    │
│                               │  Dataset: ...   │
│                               │                 │
└───────────────────────────────┴─────────────────┘
```

### Data Flow

```
Backend                         Frontend
─────────                       ──────────
GET /api/projects/{id}/         useSWR() fetches
  knowledge-graph          →    { nodes, links, stats }
                                    │
                                    ▼
                             Transform to Cytoscape elements:
                             nodes → { data: { id, label, type, ... }, classes: 'paper' }
                             links → { data: { source, target, relation } }
                                    │
                                    ▼
                             <CytoscapeComponent elements={...} />
```

Graph is computed on request from matrix rows + paper metadata.
No separate graph storage needed.

### Backend Service (`app/services/knowledge_graph.py`)

Builds graph from DB:

1. Load all saved project_papers with their matrix rows.
2. Extract unique methods, datasets, limitations as concept nodes.
3. Create edges: paper → concept, paper ↔ paper (shared concept).
4. Return `{ nodes: [...], links: [...], stats: {...} }`.

### Backend Router (`app/routers/knowledge_graph.py`)

```
GET /api/projects/{project_id}/knowledge-graph
  ?node_types=paper,method,dataset,limitation  (optional filter)
  &min_connections=1                            (optional, hide isolated)
```

Response per api-design.md contract.

## Node Types

| Type | Color | Shape | Size | Label |
|------|-------|-------|------|-------|
| Paper | `#3b82f6` (blue) | ellipse | `12 + sqrt(connections) * 6`, max 50px | Truncated title |
| Method | `#22c55e` (green) | round-rectangle | Fixed 30px | Method name |
| Dataset | `#f97316` (orange) | diamond | Fixed 28px | Dataset name |
| Limitation | `#ef4444` (red) | triangle | Fixed 26px | Limitation text |

## Edge Types

| Relation | Style | Color |
|----------|-------|-------|
| paper → uses_method | Solid | `#22c55e` (green) |
| paper → evaluates_dataset | Dashed | `#f97316` (orange) |
| paper → has_limitation | Dotted | `#ef4444` (red) |
| paper ↔ paper (shared method) | Solid, thin | `#94a3b8` (gray) |
| paper ↔ paper (shared dataset) | Solid, medium | `#94a3b8` (gray) |

## Layout Options

User can switch via dropdown:

| Layout | Cytoscape name | When to use |
|--------|---------------|-------------|
| Force-Directed (default) | `fcose` | Best for discovering relationships |
| Clustered Force | `cose-bilkent` | Better for clustered data |
| Hierarchical | `breadthfirst` | Papers top, concepts below |
| Concentric | `concentric` | High-connectivity nodes centered |
| Circle | `circle` | Equal-weight overview |
| Grid | `grid` | Clean tabular view |

## Interactions

| Action | Behavior |
|--------|----------|
| Click node | Open side panel with full details |
| Click background | Close side panel |
| Hover node | Highlight node + direct neighbors, dim rest |
| Scroll | Zoom in/out |
| Drag canvas | Pan |
| Drag node | Reposition (physics updates in force layouts) |
| Layout dropdown | Switch layout algorithm, animate transition |
| Filter dropdown | Toggle node type visibility (paper/method/dataset/limitation) |
| Search box | Find node by label text, zoom to it |

## Node Detail Panel

### Paper Node

- Title, authors (comma-separated), year, venue
- Abstract (truncated to 200 chars, expandable)
- Matrix row fields: method, dataset_or_context, key_result, limitation
- Connected concepts list (clickable)
- Link to paper URL

### Method Node

- Method name
- All papers using this method (clickable list)
- Connection count

### Dataset Node

- Dataset name
- All papers evaluating it (clickable list)

### Limitation Node

- Limitation text
- All papers sharing this limitation (clickable list)
- "Potential research gap" indicator if ≥3 papers share it

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/knowledge_graph.py` | Graph builder service (DB → nodes/links) |
| `app/routers/knowledge_graph.py` | GET endpoint |
| `app/schemas/knowledge_graph.py` | Pydantic response models |
| `frontend/app/(app)/projects/[id]/map/page.tsx` | Knowledge map page |
| `frontend/components/knowledge-map/KnowledgeGraph.tsx` | Cytoscape wrapper component |
| `frontend/components/knowledge-map/GraphToolbar.tsx` | Layout/filter/search controls |
| `frontend/components/knowledge-map/NodeDetailPanel.tsx` | Side panel component |
| `frontend/lib/api/knowledge-graph.ts` | API client function |
| `tests/test_knowledge_graph.py` | Backend tests |

## Files to Modify

| File | Change |
|------|--------|
| `frontend/package.json` | Add `cytoscape` dependency |
| `frontend/lib/types/api.ts` | Add knowledge graph types |
| `app/main.py` | Register knowledge_graph router |

## Edge Cases

1. **No matrix rows**: Show empty state with message "Generate a literature matrix first to see the knowledge map."
2. **Few papers (<3)**: Graph still renders but may look sparse. Show all 4 node types.
3. **Many papers (>50)**: Canvas handles it fine. Consider hiding labels on small zoom.
4. **No connections**: Show isolated paper nodes. User can filter to hide them.
5. **Paper with missing matrix fields**: Skip missing concept nodes/edges gracefully.

## Dependencies

```bash
npm install cytoscape
```

No extra layout extensions needed — fcose, cose-bilkent, breadthfirst,
concentric, circle, grid are all built into Cytoscape.js core.

## Non-Goals

- 3D visualization (react-force-graph-3d) — stretch, not MVP.
- Real-time collaborative editing of the graph.
- Exporting the graph as image (stretch).
- Graph algorithms (shortest path, centrality) — not needed for MVP.
- LightRAG or graph-RAG integration — stretch per docs.
