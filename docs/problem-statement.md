# Problem Statement

## Current State

AI Literature Review Assistant is an early-stage web application. The
documentation is thorough but the implementation is approximately 10-15%
complete. Only the login page, auth flow, app shell with sidebar, and
health check endpoint exist. All business logic — project management, paper
search, literature matrix, knowledge map, research gap detection, citation
guardrails, and report generation — remains unimplemented.

## Pain Point

Literature review is the most time-consuming phase of academic research.
A full systematic review averages 1,000 to 2,000 person-hours. Researchers
lose weeks searching across academic sources, scanning irrelevant papers,
manually building comparison tables, and worrying about missing important
work. Existing AI tools either generate fluent but fabricated citations
(30-72% hallucination rates across benchmarks) or only solve one stage of
the workflow, forcing researchers to cobble together 5+ disconnected tools.

The core failure chain:

```
Can't find right papers → Don't know if sources are good →
Can't organize what was found → Can't synthesize across papers →
AI invents citations → Can't verify output → Don't trust final product
```

## Proposed Solution

A single integrated web application that covers the full research workflow:
login → create project → search papers from academic APIs → save and screen
papers → generate editable literature matrix → detect evidence-based research
gaps → export citation-safe literature review drafts. The key differentiator
is a citation guardrail: the backend validates every citation ID against
saved project papers before export.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind v4, shadcn/ui |
| Backend | FastAPI (Python 3.13), SQLAlchemy async, JWT auth |
| Database | PostgreSQL 16 + pgvector (Docker) |
| AI Provider | DeepSeek V4 via opencode-go adapter |
| Agent Orchestration | LangGraph (fixed workflow graph) |
| Paper Sources | Semantic Scholar, OpenAlex, arXiv, Exa, Firecrawl |
| RAG | Custom Hybrid RAG (full-text + pgvector + metadata filters) |
| Evaluation | Ragas |
| Deployment | Coolify + Docker, GitHub Actions, GHCR |

## MVP Scope (8 Capabilities)

1. Login and user management
2. Create research project
3. Search papers from academic sources + Exa + Firecrawl
4. Save and screen papers into project corpus
5. Generate editable literature matrix from saved papers
6. Knowledge map visualization (force-directed graph)
7. Evidence-based research gap detection
8. Citation-safe literature review export (Markdown)

## Current Implementation Status

| Module | Status | Completeness |
|--------|--------|-------------|
| Auth (login, register) | Login works, no register | ~40% |
| App shell + navigation | Working | ~90% |
| Project CRUD | Not started | 0% |
| Paper search | Not started | 0% |
| Paper save/dedup | Not started | 0% |
| Literature matrix | Not started | 0% |
| Knowledge map | Not started | 0% |
| Research gaps | Not started | 0% |
| Report generation | Not started | 0% |
| Citation guardrail | Not started | 0% |
| Hybrid RAG | Not started | 0% |
| LangGraph workflow | Not started | 0% |
| Source adapters | Not started | 0% |
| AI provider | Not started | 0% |
| Docker deployment | PostgreSQL only | ~30% |
| CI/CD (GHCR) | Not started | 0% |
| Tests | Health check only | ~5% |

## Team Dependency Flow

The 3-person team follows a strict dependency chain:

```
A builds first → B layers AI on top → C tests and deploys
```

- **Member A (Full-stack Lead, ~45%):** Builds DB models, Pydantic schemas,
  CRUD APIs, auth, all frontend pages, integration. A is the critical path —
  B cannot start AI work until A delivers models and schemas.
- **Member B (AI/ML Engineer, ~30%):** Builds on A's foundation — source
  adapters, LangGraph, matrix extraction, gap detection, citation guardrails,
  hybrid RAG, knowledge graph.
- **Member C (DevOps + QA, ~25%):** Docker, CI/CD, Coolify, testing, demo
  prep, documentation.

## Key Risks for 3-Person Team

1. **Scope vs time** — 8 weeks with 3 people is tight for the full MVP.
   Prioritize search → save → matrix → gaps → export over knowledge map.
2. **AI output quality** — LLM extraction may be incomplete or wrong.
   Matrix must be editable. Gaps must require evidence.
3. **Citation trust** — The backend must reject invalid citation IDs.
   This is the core differentiator.
4. **API source reliability** — Academic APIs may be rate-limited or
   return inconsistent data. Use partial results and seeded demo data.
5. **A bottleneck risk** — A is on the critical path. If A is delayed,
   B and C are blocked. A must deliver DB models by Week 2.
6. **Integration latency** — With 3 people working in parallel,
   API contract changes must be communicated immediately.

## Demo Strategy

Use a seeded project with real papers for reliable demo. Live search can
supplement but should not be the only path. Target topic: "Retrieval-Augmented
Generation for medical question answering." Demo flow: login → open project →
search → save 10-15 papers → matrix → gaps → export → click citation →
show saved paper metadata. Target: 5-6 minutes.
