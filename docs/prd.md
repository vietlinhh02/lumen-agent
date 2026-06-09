# Product Requirements Document (PRD)

## Problem Statement

Researchers lose weeks searching across academic sources, scanning irrelevant papers, manually building comparison tables, and worrying about missing important work. Existing AI tools either generate fluent but fabricated citations (30-72% hallucination rates) or only solve one stage of the workflow, forcing researchers to cobble together 5+ disconnected tools.

The core failure chain:

```
Can't find right papers → Don't know if sources are good →
Can't organize what was found → Can't synthesize across papers →
AI invents citations → Can't verify output → Don't trust final product
```

## Solution

A single integrated web application that covers the full research workflow: login → create project → search papers from academic APIs → save and screen papers → generate editable literature matrix → detect evidence-based research gaps → export citation-safe literature review drafts.

The key differentiator is a **citation guardrail**: the backend validates every citation ID against saved project papers before export.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind v4, shadcn/ui, react-force-graph-2d |
| Backend | FastAPI (Python 3.13), SQLAlchemy async, JWT auth |
| Database | PostgreSQL 16 + pgvector (Docker) |
| AI Provider | DeepSeek V4 via opencode-go (primary), Anthropic Claude, OpenAI |
| Agent Orchestration | LangGraph (fixed workflow graph) |
| Paper Sources | Semantic Scholar (working), OpenAlex, arXiv, Exa, Firecrawl |
| RAG | Custom Hybrid RAG (full-text + pgvector + metadata filters) |
| Evaluation | Ragas |
| Deployment | Coolify + Docker, GitHub Actions → GHCR |

## MVP Scope (8 Capabilities)

1. Login and user management
2. Create research project
3. Search papers from academic sources
4. Save and screen papers into project corpus
5. Generate editable literature matrix from saved papers
6. Knowledge map visualization (force-directed graph)
7. Evidence-based research gap detection
8. Citation-safe literature review export (Markdown)

## Current Implementation Status

| Module | Status | Completeness |
|--------|--------|-------------|
| Auth (login, register) | Working | ~90% |
| App shell + sidebar | Working | ~90% |
| Project CRUD | Working | ~80% |
| Paper search (Semantic Scholar) | Working | ~70% |
| Paper save/dedup | Working | ~70% |
| PDF download + ingestion | Working | ~60% |
| Search sessions + pagination | Working | ~70% |
| AI screening + query suggestions | Working | ~60% |
| LangGraph agent workflow | Working (skeleton) | ~50% |
| Hybrid retrieval | Working | ~50% |
| AI provider (DeepSeek/Anthropic/OpenAI) | Working | ~80% |
| DB models (17 tables) | Working | ~95% |
| Literature matrix | Not started | 0% |
| Knowledge map | Not started | 0% |
| Research gaps UI | Not started | 0% |
| Report generation UI | Not started | 0% |
| Citation guardrail (backend validation) | Partial | ~30% |
| Source adapters (OpenAlex, arXiv, Exa, Firecrawl) | Not started | 0% |
| Language bias service | Not started | 0% |
| Research enrichment service | Partial | ~20% |
| CI/CD (GitHub Actions, GHCR) | Not started | 0% |
| Docker deployment (Coolify) | Not started | 0% |
| Tests | Health check only | ~10% |

## User Stories

1. As a researcher, I want to register and log in with email/password, so that my projects are private and persistent.
2. As a researcher, I want to create a research project with a title, topic, and optional research question, so that I have a workspace for my literature review.
3. As a researcher, I want to search papers from Semantic Scholar, OpenAlex, and arXiv, so that I can find relevant literature across multiple databases.
4. As a researcher, I want to see search results with title, authors, year, abstract, citation count, and source badges, so that I can quickly assess relevance.
5. As a researcher, I want to save relevant papers into my project corpus, so that I can build a controlled collection for analysis.
6. As a researcher, I want the system to deduplicate papers across sources, so that I don't have duplicate entries in my corpus.
7. As a researcher, I want to screen papers with AI-assisted relevance scoring (high/medium/low), so that I can quickly identify the most relevant papers.
8. As a researcher, I want to generate a structured literature matrix from saved papers, so that I can compare methods, datasets, results, and limitations across papers.
9. As a researcher, I want to edit matrix cells because AI extraction can be incomplete or wrong.
10. As a researcher, I want to see a knowledge map visualization of papers, methods, datasets, and limitations, so that I can see relationships and clusters in the literature.
11. As a researcher, I want to generate evidence-based research gaps from the matrix, so that I can identify underexplored areas with supporting evidence.
12. As a researcher, I want each gap to reference specific saved papers as evidence, so that gaps are defensible rather than generic.
13. As a researcher, I want to generate a literature review draft with inline citations, so that I have a starting point for my review.
14. As a researcher, I want the backend to validate all citation IDs against saved project papers, so that the review never cites non-existent papers.
15. As a researcher, I want to export the review as Markdown with a reference list, so that I can use it in my paper.
16. As a researcher, I want to see a language coverage audit in search results, so that I can detect English-language bias.
17. As a researcher, I want the system to generate query variants in my original language, so that non-English papers are not missed.
18. As a researcher, I want to see an agent run audit timeline, so that I can understand what the AI workflow did at each step.
19. As an admin, I want to list and manage users, so that I can control access to the system.
20. As a researcher, I want the system to be deployed online with a public URL, so that I can access it from anywhere.
