# AI Suggest Context + Exa & Firecrawl Integration

## Problem

### AI Suggest Is Too Generic

The `POST /api/papers/suggest-queries` endpoint currently receives only a
`topic` string from the frontend. The LLM generates 4–6 search queries based
solely on this one field. The project's `title` and `research_question` are
available in the frontend but never sent to the backend. This produces
suggestions that are less relevant than they could be.

### Exa and Firecrawl Are Defined But Not Wired

The search fan-out in `app/services/paper_search.py` generates per-source
query variants via the language bias service for `exa` and `firecrawl`, but
the fan-out only instantiates `PaperHubSource` for academic sources. Exa and
Firecrawl fall through to a `"not implemented"` diagnostic. No source adapter
files exist.

### PaperHub Often Lacks PDF Download Links

Many papers returned by PaperHub have no `pdf_url` in `source_specific`. The
PDF downloader falls back through arXiv CDN → Semantic Scholar OA → PaperHub
DOI lookup, but many papers still end up without a PDF. Crawling the paper's
web page via Firecrawl could extract direct PDF links.

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| AI Suggest input | Send title + topic + research_question | Richer context → more relevant suggestions |
| Exa role | Independent paper source | Semantic web search finds research pages PaperHub misses |
| Firecrawl role | PDF link extractor (post-search) | Crawls each paper URL after search to find direct PDF links |
| Exa search timing | Parallel with PaperHub | Both fan out at search time |
| Firecrawl timing | After search, before PDF download | Enriches papers with crawl-found PDF URLs |
| Source failure | Partial results + diagnostic | Same pattern as existing source handling |
| API keys | `EXA_API_KEY`, `FIRECRAWL_API_KEY` in env | Follow existing config pattern |

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Language bias → detect language + generate variants     │
│     Variants mapped to canonical sources:                   │
│       semantic_scholar → PaperHubSource                     │
│       exa → ExaSource                                       │
│       firecrawl → (handled separately post-search)          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Fan-out search (parallel):                              │
│     ├── PaperHubSource.search() → RawPaper[]                │
│     └── ExaSource.search() → RawPaper[]                     │
│  3. Merge + deduplicate all results                         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Firecrawl crawl_pdf_links(all_raw_papers):              │
│     - Filter papers with URL but no source_specific.pdf_url │
│     - Crawl each URL via Firecrawl /v1/scrape (concurrency 5)│
│     - Extract .pdf links from page content                  │
│     - Set paper.source_specific["pdf_url"] if found         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  5. PDF downloader (enhanced priority):                     │
│     arXiv CDN → S2 OA → Firecrawl-enrich URL → PaperHub DOI│
└─────────────────────────────────────────────────────────────┘
```

### AI Suggest Flow

```
Frontend: selectedProject.title + .topic + .research_question
    │
    ▼
POST /api/papers/suggest-queries
{ title: "...", topic: "...", research_question: "..." }
    │
    ▼
LLM prompt:
  "Research project title: {title}
   Research topic: {topic}
   Research question: {research_question}
   Suggest 4–6 targeted academic search queries..."
    │
    ▼
Response: { queries: ["query1", "query2", ...] }
```

## Exa Source Adapter

### API

- Endpoint: `https://api.exa.ai/search`
- Method: POST
- Headers: `x-api-key: {EXA_API_KEY}`, `Content-Type: application/json`
- Body: `{"query": "...", "type": "paper", "numResults": 25, "startPublishedDate": "2020-01-01", "endPublishedDate": "2026-12-31"}`
- Response: `{"results": [{"title": "...", "url": "...", "author": "...", "publishedDate": "...", "text": "..."}]}`

### Mapping Exa → RawPaper

| Exa field | RawPaper field | Notes |
|-----------|---------------|-------|
| `title` | `title` | Direct |
| `text` | `abstract` | Snippet from page |
| `publishedDate` | `year` | Parse year from date |
| `url` | `url` | Direct |
| `author` | `authors` | Wrap in `[{"name": ..., "author_id": ""}]` |
| — | `source_name` | `"exa"` |
| full result | `source_specific` | Raw API response |

Exa does not provide DOI, arXiv ID, citation count, or venue. These stay null.

### Implementation

`app/sources/exa.py`:
```python
class ExaSource(PaperSource):
    name = "exa"

    async def search(self, query, limit, year_from, year_to) -> list[RawPaper]:
        body = {"query": query, "type": "paper", "numResults": limit}
        if year_from:
            body["startPublishedDate"] = f"{year_from}-01-01"
        if year_to:
            body["endPublishedDate"] = f"{year_to}-12-31"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                json=body,
                headers={
                    "x-api-key": settings.exa_api_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return [_exa_to_raw(r) for r in data.get("results", [])]
```

## Firecrawl Adapter

### API

- Endpoint: `https://api.firecrawl.dev/v1/scrape`
- Method: POST
- Headers: `Authorization: Bearer {FIRECRAWL_API_KEY}`
- Body: `{"url": "...", "formats": ["markdown"]}`
- Response: `{"success": true, "data": {"markdown": "...", "metadata": {"ogTitle": "...", ...}}}`

### Function (not a PaperSource — Firecrawl does not search)

`app/sources/firecrawl.py`:
```python
async def crawl_pdf_links(
    papers: list[RawPaper],
    concurrency: int = 5,
    timeout: float = 15.0,
) -> list[RawPaper]:
    """Crawl paper URLs to find direct PDF download links.

    For each paper that has a URL but no pdf_url in source_specific,
    crawl the page and extract .pdf links from the content.
    Modifies paper.source_specific["pdf_url"] in-place.
    Returns the (modified) list.
    """
```

PDF link extraction: regex `https?://[^\s"'<>]+\.pdf` on the markdown content.
Priority: first `.pdf` link found on the page. Returns early if found.

## Search Fan-Out Changes

`app/services/paper_search.py:95-109` — replace the if/else block:

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

        papers = await source.search(query=src_query, ...)
        all_raw.extend(papers)
        source_diagnostics.append(...)
    except Exception as exc:
        ...
```

After the fan-out (after dedup, before PDF download), add:

```python
# 3. Enrich PDF links via Firecrawl
all_raw = await crawl_pdf_links(all_raw)
```

## PDF Downloader Enhancement

`app/services/pdf_downloader.py:47-63` — `resolve_pdf_url()` priority order:

1. arXiv CDN (if `arxiv_id`)
2. Semantic Scholar OA (`source_specific["pdf_url"]` from PaperHub)
3. **Firecrawl-enriched URL** (`source_specific["pdf_url"]` from crawl)
4. PaperHub DOI lookup fallback

The existing code already checks `source_specific["pdf_url"]` at step 2.
Since Firecrawl also writes to that field, step 3 is handled automatically
— no code change needed in the downloader. Firecrawl runs before PDF download
in the search flow, so the enriched URL is available when the downloader runs.

## Config

Add to `app/core/config.py`:

```python
# Exa
exa_api_key: str = ""

# Firecrawl
firecrawl_api_key: str = ""
```

Required env vars: `EXA_API_KEY`, `FIRECRAWL_API_KEY`.

## AI Suggest Schema Changes

### Schema (`app/schemas/paper.py:120-123`)

```python
class SuggestQueriesRequest(BaseModel):
    title: str = Field(default="", description="Project title")
    topic: str = Field(..., description="Research topic", min_length=2, max_length=500)
    research_question: str = Field(default="", description="Specific research question")
```

### Prompt (`app/ai/prompts.py:49-53`)

```python
SEARCH_SUGGEST_USER = """\
Research project title: {title}
Research topic: {topic}
Research question: {research_question}

Suggest 4–6 targeted academic search queries for this project.
"""
```

### Router (`app/routers/paper.py:64`)

```python
user_msg = SEARCH_SUGGEST_USER.format(
    title=request.title,
    topic=request.topic,
    research_question=request.research_question or request.topic,
)
```

### Frontend (`search/page.tsx:221-223`)

```typescript
const data = await apiFetch<SuggestQueriesResponse>("/papers/suggest-queries", {
    method: "POST",
    body: JSON.stringify({
        title: selectedProject?.title || "",
        topic: suggestTopic,
        research_question: selectedProject?.research_question || "",
    }),
    headers: { Authorization: `Bearer ${token}` },
});
```

## Files to Create

| File | Purpose |
|------|---------|
| `app/sources/exa.py` | Exa source adapter — search papers from web |
| `app/sources/firecrawl.py` | Firecrawl utility — crawl pages for PDF links |

## Files to Modify

| File | Change |
|------|--------|
| `app/core/config.py` | Add `exa_api_key`, `firecrawl_api_key` |
| `app/schemas/paper.py` | `SuggestQueriesRequest` — add `title`, `research_question` |
| `app/ai/prompts.py` | `SEARCH_SUGGEST_USER` — add title and research_question |
| `app/routers/paper.py` | Pass title + research_question to prompt |
| `app/services/paper_search.py` | Wire ExaSource + Firecrawl crawl into fan-out |
| `frontend/app/(app)/search/page.tsx` | Send full project fields on suggest |
| `frontend/lib/types.ts` | Update `SuggestQueriesResponse` type if needed |

## Edge Cases

1. **No EXA_API_KEY**: Skip Exa search, log diagnostic `"skipped (no API key)"`
2. **No FIRECRAWL_API_KEY**: Skip crawl, PDF download falls through to other sources
3. **Exa returns 0 results**: Empty list, diagnostic `"ok"` with `result_count: 0`
4. **Firecrawl timeout on URL**: Skip that URL, continue with others
5. **Firecrawl returns no PDF link**: Paper unchanged, PDF downloader uses other sources
6. **Exa rate limited (429)**: Catch, log, diagnostic `"failed"` with message
7. **project has no research_question**: Falls back to topic in prompt
8. **project has no title**: Empty string in prompt (no harm)

## Non-Goals

- Exa + Firecrawl as enrichment service (saving crawled content to DB)
- Firecrawl as a paper search source
- Exa for citation/reference graph
- Frontend UI changes beyond the suggest-queries body
