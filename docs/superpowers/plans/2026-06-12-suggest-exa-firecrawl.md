# AI Suggest Context + Exa & Firecrawl Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich AI Suggest with full project context and wire Exa + Firecrawl sources into the paper search flow.

**Architecture:** ExaSource runs in parallel with PaperHubSource at search time; Firecrawl `crawl_pdf_links()` runs after search to enrich papers with direct PDF URLs. AI Suggest gets `title` + `topic` + `research_question` from project.

**Tech Stack:** Python 3.13, FastAPI, httpx, Next.js 16, TypeScript

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/core/config.py` | **Modify** | Add `exa_api_key`, `firecrawl_api_key` |
| `app/schemas/paper.py` | **Modify** | `SuggestQueriesRequest` — add `title`, `research_question` |
| `app/ai/prompts.py` | **Modify** | `SEARCH_SUGGEST_USER` — add title and research_question |
| `app/routers/paper.py` | **Modify** | Pass title + research_question to prompt |
| `app/sources/exa.py` | **Create** | Exa source adapter — search papers from web |
| `app/sources/firecrawl.py` | **Create** | Firecrawl utility — crawl pages for PDF links |
| `app/services/paper_search.py` | **Modify** | Wire ExaSource + Firecrawl crawl into fan-out |
| `frontend/app/(app)/search/page.tsx` | **Modify** | Send full project fields on suggest |

---

### Task 1: Add Exa and Firecrawl Config

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Add API key fields**

Add after line 62 (`paper_pdf_dir`):

```python
    # Exa
    exa_api_key: str = ""

    # Firecrawl
    firecrawl_api_key: str = ""
```

- [ ] **Step 2: Verify config compiles**

Run: `python -c "from app.core.config import get_settings; s = get_settings(); print(s.exa_api_key); print(s.firecrawl_api_key)"`
Expected: Prints two empty strings (keys loaded from .env at runtime)

- [ ] **Step 3: Commit**

```bash
git add app/core/config.py
git commit -m "feat: add exa_api_key and firecrawl_api_key config fields"
```

---

### Task 2: Update AI Suggest Schema

**Files:**
- Modify: `app/schemas/paper.py:120-123`

- [ ] **Step 1: Add title and research_question fields**

Replace lines 120-123 with:

```python
class SuggestQueriesRequest(BaseModel):
    """Request body for query suggestion endpoint."""

    title: str = Field(default="", description="Project title")
    topic: str = Field(..., description="Research topic", min_length=2, max_length=500)
    research_question: str = Field(default="", description="Specific research question")
```

- [ ] **Step 2: Verify schemas compile**

Run: `python -c "from app.schemas.paper import SuggestQueriesRequest; r = SuggestQueriesRequest(topic='test', title='My Project', research_question='How does X work?'); print(r.model_dump())"`
Expected: `{'title': 'My Project', 'topic': 'test', 'research_question': 'How does X work?'}`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/paper.py
git commit -m "feat: add title and research_question to SuggestQueriesRequest"
```

---

### Task 3: Update AI Suggest Prompt

**Files:**
- Modify: `app/ai/prompts.py:49-53`

- [ ] **Step 1: Rewrite SEARCH_SUGGEST_USER**

Replace lines 49-53 with:

```python
SEARCH_SUGGEST_USER = """\
Research project title: {title}
Research topic: {topic}
Research question: {research_question}

Suggest 4–6 targeted academic search queries for this project.
```

- [ ] **Step 2: Verify prompts import**

Run: `python -c "from app.ai.prompts import SEARCH_SUGGEST_USER; print(SEARCH_SUGGEST_USER.format(title='T', topic='X', research_question='RQ'))"`
Expected: Prints the prompt with all three fields filled in

- [ ] **Step 3: Commit**

```bash
git add app/ai/prompts.py
git commit -m "feat: add title and research_question to SEARCH_SUGGEST_USER prompt"
```

---

### Task 4: Update AI Suggest Router

**Files:**
- Modify: `app/routers/paper.py:56-91`

- [ ] **Step 1: Pass new fields to prompt**

Replace line 64 (`user_msg = ...`) with:

```python
    user_msg = SEARCH_SUGGEST_USER.format(
        title=request.title,
        topic=request.topic,
        research_question=request.research_question or request.topic,
    )
```

- [ ] **Step 2: Verify router compiles**

Run: `python -c "from app.routers.paper import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/routers/paper.py
git commit -m "feat: pass title and research_question to suggest-queries LLM call"
```

---

### Task 5: Update AI Suggest Frontend

**Files:**
- Modify: `frontend/app/(app)/search/page.tsx:217-228`

- [ ] **Step 1: Send full project fields**

Replace lines 217-228 with:

```typescript
  async function handleSuggestQueries() {
    if (!suggestTopic) { toast.error("Set a research question in your project first"); return; }
    setSuggestingLabels(true);
    try {
      const data = await apiFetch<SuggestQueriesResponse>("/papers/suggest-queries", {
        method: "POST",
        body: JSON.stringify({
          title: selectedProject?.title || "",
          topic: suggestTopic,
          research_question: selectedProject?.research_question || "",
        }),
        headers: { Authorization: `Bearer ${token}` },
      });
      setSuggestedQueries(data.queries);
    } catch (err) { toast.error(err instanceof Error ? err.message : "Failed to generate suggestions"); }
    finally { setSuggestingLabels(false); }
  }
```

- [ ] **Step 2: Verify frontend typecheck**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No new errors from this change

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(app\)/search/page.tsx
git commit -m "feat: send title and research_question to AI suggest endpoint"
```

---

### Task 6: Create Exa Source Adapter

**Files:**
- Create: `app/sources/exa.py`

- [ ] **Step 1: Create the adapter**

```python
"""Exa semantic web search source adapter."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.sources.base import PaperSource, RawPaper

logger = logging.getLogger(__name__)

_EXA_SEARCH_URL = "https://api.exa.ai/search"


class ExaSource(PaperSource):
    """Search for research papers using Exa semantic web search."""

    name = "exa"

    async def search(
        self,
        query: str,
        limit: int = 25,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[RawPaper]:
        settings = get_settings()
        if not settings.exa_api_key:
            logger.warning("EXA_API_KEY not set, skipping Exa search")
            return []

        body: dict = {"query": query, "type": "paper", "numResults": min(limit, 25)}
        if year_from:
            body["startPublishedDate"] = f"{year_from}-01-01"
        if year_to:
            body["endPublishedDate"] = f"{year_to}-12-31"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _EXA_SEARCH_URL,
                json=body,
                headers={
                    "x-api-key": settings.exa_api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        return [_exa_to_raw(r) for r in results]


def _exa_to_raw(result: dict) -> RawPaper:
    """Map an Exa search result to a canonical RawPaper."""
    published = result.get("publishedDate", "")
    year = _parse_year(published)

    return RawPaper(
        title=result.get("title", ""),
        abstract=result.get("text") or None,
        year=year,
        url=result.get("url") or None,
        authors=_parse_exa_author(result.get("author")),
        source_name="exa",
        source_specific={"exa_raw": result},
    )


def _parse_year(date_str: str) -> int | None:
    """Extract year from an Exa publishedDate string."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(date_str.strip()[:10], fmt).year
        except (ValueError, IndexError):
            continue
    return None


def _parse_exa_author(author: str | None) -> list[dict[str, str]]:
    """Parse Exa author string into canonical author list."""
    if not author:
        return []
    return [{"name": a.strip(), "author_id": ""} for a in author.split(",") if a.strip()]
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.sources.exa import ExaSource; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/sources/exa.py
git commit -m "feat: add Exa source adapter for semantic web paper search"
```

---

### Task 7: Create Firecrawl PDF Link Crawler

**Files:**
- Create: `app/sources/firecrawl.py`

- [ ] **Step 1: Create the adapter**

```python
"""Firecrawl utility — crawl paper pages to find direct PDF download links."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.core.config import get_settings
from app.sources.base import RawPaper

logger = logging.getLogger(__name__)

_FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
_PDF_LINK_RE = re.compile(r'https?://[^\s"\'<>]+\.pdf(?:/[^\s"\'<>]*)?', re.IGNORECASE)
_CONCURRENCY = 5
_SCRAPE_TIMEOUT = 15.0


async def crawl_pdf_links(
    papers: list[RawPaper],
    concurrency: int = _CONCURRENCY,
    timeout: float = _SCRAPE_TIMEOUT,
) -> list[RawPaper]:
    """Crawl paper URLs to find direct PDF download links.

    For each paper that has a URL but no ``pdf_url`` in ``source_specific``,
    scrape the page and extract .pdf links from the content.

    Modifies ``paper.source_specific["pdf_url"]`` in-place on success.
    Returns the (possibly modified) list.
    """
    settings = get_settings()
    if not settings.firecrawl_api_key:
        logger.warning("FIRECRAWL_API_KEY not set, skipping Firecrawl crawl")
        return papers

    # Filter papers that need crawling: have a URL but no existing pdf_url
    targets = [
        p for p in papers
        if p.url and not p.source_specific.get("pdf_url")
    ]
    if not targets:
        return papers

    sem = asyncio.Semaphore(concurrency)

    async def _crawl_one(paper: RawPaper) -> None:
        async with sem:
            try:
                pdf = await _scrape_pdf_url(paper.url, settings.firecrawl_api_key, timeout)
                if pdf:
                    paper.source_specific["pdf_url"] = pdf
                    logger.info("Firecrawl found PDF: %s", pdf[:100])
            except Exception as exc:
                logger.debug("Firecrawl scrape failed for %s: %s", paper.url, exc)

    await asyncio.gather(*(_crawl_one(p) for p in targets), return_exceptions=True)
    return papers


async def _scrape_pdf_url(
    url: str,
    api_key: str,
    timeout: float,
) -> str | None:
    """Scrape a single URL via Firecrawl to find a direct PDF link."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            _FIRECRAWL_SCRAPE_URL,
            json={"url": url, "formats": ["markdown"]},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("success"):
        return None

    markdown = data.get("data", {}).get("markdown", "")
    if not markdown:
        return None

    match = _PDF_LINK_RE.search(markdown)
    return match.group(0) if match else None
```

- [ ] **Step 2: Verify the file compiles**

Run: `python -c "from app.sources.firecrawl import crawl_pdf_links; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/sources/firecrawl.py
git commit -m "feat: add Firecrawl PDF link crawler utility"
```

---

### Task 8: Wire Exa + Firecrawl into Search Fan-Out

**Files:**
- Modify: `app/services/paper_search.py:95-109`

- [ ] **Step 1: Update imports**

Add after line 31 (`from app.sources.paperhub import PaperHubSource`):

```python
from app.sources.exa import ExaSource
from app.sources.firecrawl import crawl_pdf_links
```

- [ ] **Step 2: Replace the fan-out logic**

Replace lines 95-109 with:

```python
    for src_name, src_query in source_query_map.items():
        try:
            if src_name in ("semantic_scholar", "arxiv", "openalex"):
                source = PaperHubSource()
            elif src_name == "exa":
                source = ExaSource()
            else:
                # firecrawl handled separately after search
                continue

            papers = await source.search(
                query=src_query,
                limit=min(request.limit, 100),
                year_from=request.year_from,
                year_to=request.year_to,
            )
            all_raw.extend(papers)
            source_diagnostics.append(
                {
                    "source": src_name,
                    "status": "ok",
                    "result_count": len(papers),
                }
            )
        except Exception as exc:
            logger.warning("Source %s failed: %s", src_name, exc)
            source_diagnostics.append(
                {
                    "source": src_name,
                    "status": "failed",
                    "result_count": 0,
                    "message": str(exc)[:200],
                }
            )
```

- [ ] **Step 3: Add Firecrawl crawl after dedup, before PDF download**

Add after line 138 (`raw_papers = raw_papers[: request.limit]`):

```python
    # ── 2.5. Enrich PDF links via Firecrawl ─────────────────────────────
    try:
        all_raw = await crawl_pdf_links(all_raw)
    except Exception as exc:
        logger.warning("Firecrawl crawl failed: %s", exc)
```

- [ ] **Step 4: Verify the file compiles**

Run: `python -c "from app.services.paper_search import search_and_download; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Run existing tests**

Run: `pytest tests/ -v -x`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add app/services/paper_search.py
git commit -m "feat: wire ExaSource and Firecrawl into search fan-out"
```

---

### Task 9: Integration Verification

- [ ] **Step 1: Run all backend tests**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 2: Run backend linter**

Run: `ruff check app/core/config.py app/schemas/paper.py app/ai/prompts.py app/routers/paper.py app/sources/exa.py app/sources/firecrawl.py app/services/paper_search.py`
Expected: No errors

- [ ] **Step 3: Run frontend typecheck**

Run: `cd frontend && npx tsc --noEmit --pretty`
Expected: No new errors

- [ ] **Step 4: Start backend and test**

Run: `make backend`
Then test the suggest-queries endpoint with:
```bash
curl -s -X POST http://localhost:8010/api/papers/suggest-queries \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "RAG for Medical QA", "topic": "Retrieval-Augmented Generation", "research_question": "How do RAG systems improve factuality?"}' | python -m json.tool
```
Expected: Returns `{"queries": [...]}` with 4-6 queries
