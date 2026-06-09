# Status Snapshot (2026-06-09)

## Backend — FastAPI

### Working

| Feature | Files | Notes |
|---------|-------|-------|
| Auth (register, login, me) | `app/routers/auth.py`, `app/services/auth.py` | JWT tokens, bcrypt passwords |
| Project CRUD | `app/routers/project.py`, `app/services/project.py` | Create, list, get, update, delete with ownership checks |
| Paper search | `app/routers/paper.py`, `app/services/paper_search.py` | Semantic Scholar only, PDF download |
| Paper save/dedup | `app/services/project.py` | Unique constraint on (project_id, paper_id) |
| PDF download | `app/services/pdf_downloader.py` | arXiv CDN + Semantic Scholar open access |
| PDF ingestion | `app/services/pdf_ingestion.py` | Extract text, chunk, store in `paper_chunks` |
| PDF normalization | `app/services/pdf_normalizer.py` | LLM-based cleanup of extracted text |
| Search sessions | `app/routers/search_session.py`, `app/services/search_session.py` | Pagination, session history |
| AI screening | `app/routers/paper.py` | LLM relevance scoring (high/medium/low) |
| AI query suggestions | `app/routers/paper.py` | LLM-generated search queries |
| Hybrid retrieval | `app/services/hybrid_retrieval.py` | Keyword + vector scoring over chunks |
| LangGraph workflow | `app/agents/graph.py`, `app/agents/nodes.py` | 7 nodes: query_planner → search → save_screened → matrix → gaps → review → citation_validator |
| AI provider | `app/ai/provider.py` | Anthropic, OpenAI, DeepSeek adapters |
| Embeddings | `app/core/embeddings.py` | Gemini embedding-2, 768 dimensions |
| DB models | `app/db/models.py` | 17 tables fully defined |

### Not Started

- OpenAlex source adapter
- arXiv source adapter
- Exa source adapter
- Firecrawl source adapter
- Matrix CRUD endpoints (only agent-based generation exists)
- Gap CRUD endpoints (only agent-based generation exists)
- Report CRUD endpoints (only agent-based generation exists)
- Knowledge graph endpoint
- Language bias service
- Research enrichment service (beyond PDF normalization)
- Admin endpoints
- Ragas evaluation

## Frontend — Next.js 16

### Working

| Feature | Files | Notes |
|---------|-------|-------|
| Login page | `frontend/app/(auth)/login/page.tsx` | Email/password form |
| Register page | `frontend/app/(auth)/login/register/page.tsx` | Email/password form |
| Projects dashboard | `frontend/app/(app)/projects/page.tsx` | List, filter (all/active/archived), create |
| Project detail | `frontend/app/(app)/projects/[id]/page.tsx` | Papers list, PDF download, remove, full text view |
| Search page | `frontend/app/(app)/search/page.tsx` | Search, save, AI screen, AI suggest, pagination, sessions |
| App shell | `frontend/app/(app)/layout.tsx` | Sidebar navigation |

### Not Started

- Literature matrix editor
- Knowledge map visualization (react-force-graph-2d)
- Research gaps page
- Review export page
- Agent run audit page
- Admin page

## Infrastructure

### Working

- Docker Compose: PostgreSQL 16 + pgvector (`docker-compose.yml`)
- Makefile: setup, dev, backend, frontend, test, lint, format, typecheck

### Not Started

- Backend Dockerfile
- Frontend Dockerfile
- GitHub Actions CI/CD
- Coolify deployment config

## Tests

| Test | File | Status |
|------|------|--------|
| Health check | `tests/test_health.py` | Passing |
| Hybrid retrieval | `tests/test_hybrid_retrieval.py` | Passing |
| Log hook | `tests/test_log_hook.py` | Passing |
| PDF normalizer | `tests/test_pdf_normalizer.py` | Passing |
