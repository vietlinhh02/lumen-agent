# Status Snapshot (2026-06-11)

## Backend — FastAPI

### Working (13 routers, 16 services, 17+ DB tables)

| Feature | Files | Notes |
|---------|-------|-------|
| Auth (register, login, me, password change) | `app/routers/auth.py`, `app/services/auth.py` | JWT + bcrypt |
| Project CRUD | `app/routers/project.py`, `app/services/project.py` | Ownership checks, delete cascade |
| Paper search | `app/routers/paper.py`, `app/services/paper_search.py` | Semantic Scholar + PaperHub (OpenAlex, arXiv, EuropePMC, PMC) |
| Paper save/dedup | `app/services/project.py` | Unique constraint on (project_id, paper_id) |
| PDF download | `app/services/pdf_downloader.py` | arXiv CDN + S2 OA + PaperHub fallback |
| PDF ingestion | `app/services/pdf_ingestion.py` | pdfplumber, section detection, chunking |
| PDF normalization | `app/services/pdf_normalizer.py` | LLM cleanup, LLM section detection, embedding |
| Search sessions | `app/routers/search_session.py`, `app/services/search_session.py` | Pagination, screening, auto-save (background jobs) |
| AI screening | `app/routers/paper.py` | LLM relevance scoring (high/medium/low) |
| AI query suggestions | `app/routers/paper.py` | LLM-generated search queries |
| Language bias | `app/services/language_bias.py` | LLM detect + variants, audit computation |
| Hybrid retrieval | `app/services/hybrid_retrieval.py` | Keyword + vector + section boosts + reranker |
| Reranker | `app/services/reranker.py` | NVIDIA Nemotron reranking API (free, no local model) |
| Embeddings | `app/core/embeddings.py` | NVIDIA Nemotron via OpenRouter API (free, no local model) |
| LangGraph workflow | `app/agents/graph.py`, `app/agents/nodes.py` | 9 nodes: query_planner → search → language_bias → save_screened → matrix → gaps → conflicts → review → citation_validator |
| AI provider | `app/ai/provider.py` | Anthropic, OpenAI-compatible (DeepSeek), embedder |
| Matrix CRUD | `app/routers/matrix.py`, `app/services/literature_matrix.py` | List, update cells, delete, generate (background job) |
| Gap CRUD | `app/routers/gaps.py`, `app/services/gap_detection.py` | List, delete, generate with evidence validation (background job) |
| Conflict detection | `app/routers/conflicts.py`, `app/services/conflict_detection.py` | LLM-based, groups by shared method/dataset (background job) |
| Report CRUD | `app/routers/reports.py`, `app/services/report_generation.py` | RAG + citation guardrail + retry + Markdown export (background job) |
| Knowledge graph | `app/routers/knowledge_graph.py`, `app/services/knowledge_graph.py` | 4 node types, 5 edge types, filters |
| Admin | `app/routers/admin.py` | List users, activate/deactivate |
| Dashboard stats | `app/routers/stats.py` | Project counts, paper counts, recent activity |
| DB models | `app/db/models.py` | 17 tables with relationships, constraints, indexes |

### Not Implemented

- Dedicated OpenAlex/arXiv source adapters (handled through PaperHub)
- Exa source adapter
- Firecrawl source adapter
- Agent run audit persistence (models exist, no code writes to them)
- Ragas evaluation
- pgvector Vector type (embeddings stored as Text/JSON)

## Frontend — Next.js 16

### Working (14 pages)

| Feature | Files | Notes |
|---------|-------|-------|
| Landing page | `frontend/app/page.tsx` | Hero, workflow steps, pain points, features |
| Login | `frontend/app/(auth)/login/page.tsx` | BrandPanel + LoginForm |
| Register | `frontend/app/(auth)/login/register/page.tsx` | BrandPanel + RegisterForm |
| Dashboard | `frontend/app/(app)/dashboard/page.tsx` | Stats cards, quick actions, recent projects |
| Project list | `frontend/app/(app)/projects/page.tsx` | Filter (all/active/archived), create |
| Project detail | `frontend/app/(app)/projects/[id]/page.tsx` | Papers list, PDF download, remove, full text view |
| Search | `frontend/app/(app)/search/page.tsx` | Sessions, pagination, AI screen, auto-save, language audit |
| Saved papers | `frontend/app/(app)/papers/page.tsx` | Table across all projects |
| Literature matrix | `frontend/app/(app)/matrix/page.tsx` | Generate, editable cells, confidence badges, stats |
| Knowledge map | `frontend/app/(app)/map/page.tsx` | Cytoscape graph, 5 layouts, filters, node detail panel |
| Research gaps | `frontend/app/(app)/gaps/page.tsx` | Gap cards with evidence, conflict cards |
| Reports | `frontend/app/(app)/reports/page.tsx` | Split-view, Markdown export, citation audit |
| Settings | `frontend/app/(app)/settings/page.tsx` | Profile + admin user management |
| App shell | `frontend/app/(app)/layout.tsx` | Sidebar (desktop icons, mobile drawer), header |

### Key Components

| Component | Files | Notes |
|-----------|-------|-------|
| Auth | `components/LoginForm.tsx`, `components/RegisterForm.tsx`, `lib/auth.tsx` | Context-based, localStorage token |
| Search | `components/search/PaperCard.tsx`, `LanguageAudit.tsx`, `Pagination.tsx` | Source badges, score, save/unsave |
| Matrix | `components/matrix/MatrixTable.tsx`, `EditableCell.tsx`, `ConfidenceBadge.tsx` | Card-based, click-to-edit |
| Gaps | `components/gaps/GapCard.tsx`, `ConflictCard.tsx` | Expandable with evidence panels |
| Reports | `components/reports/ReportList.tsx`, `ReportContent.tsx`, `ReportToolbar.tsx` | Markdown rendering, citation pills |
| Knowledge map | `components/knowledge-map/KnowledgeGraph.tsx`, `GraphToolbar.tsx`, `NodeDetailPanel.tsx` | Cytoscape.js, 4 node types |
| Settings | `components/settings/index.tsx` | Theme, password, admin user table |

## Infrastructure

### Working

- Docker Compose: PostgreSQL 16 + pgvector (`docker-compose.yml`)
- Makefile: setup, dev, backend, frontend, test, lint, format, typecheck

### Not Started

- Backend Dockerfile
- Frontend Dockerfile
- GitHub Actions CI/CD
- Coolify deployment config

## Tests (12 files)

| Test | File | Status |
|------|------|--------|
| Health check | `tests/test_health.py` | Passing |
| Hybrid retrieval | `tests/test_hybrid_retrieval.py` | Passing |
| Log hook | `tests/test_log_hook.py` | Passing |
| PDF normalizer | `tests/test_pdf_normalizer.py` | Passing |
| Matrix extraction | `tests/test_matrix_extraction.py` | Passing |
| Gap analysis | `tests/test_gap_analysis.py` | Passing |
| Conflict detection | `tests/test_conflict_detection.py` | Passing |
| Review writer | `tests/test_review_writer.py` | Passing |
| Language bias | `tests/test_language_bias.py` | Passing |
| Background jobs | `tests/test_background_jobs.py` | Passing |
| Embedding quality | `tests/test_embedding_quality.py` | Passing |
| Reranker | `tests/test_reranker.py` | Passing |
