# Language Bias Service — Design Spec

## Problem

The search flow (`POST /api/papers/search`) sends the user's query directly to
academic sources without considering language. If a researcher searches in
Vietnamese ("RAG hỏi đáp y khoa"), the system sends that raw query to Semantic
Scholar and arXiv — both primarily index English papers. The results will be
poor. There is no query variant generation, no language detection, and no
language coverage audit. The `LanguageBiasAgent` node in the LangGraph workflow
is specified in docs but not implemented.

## Goal

Build a Language Bias Service that:

1. Detects the query language via LLM.
2. Generates English + original-language query variants via LLM.
3. Distributes per-source variants to academic APIs.
4. Computes a language coverage audit from source diagnostics.
5. Returns `language_bias_audit` and `query_variants` in the search response.
6. Displays language coverage badges in the frontend search results.

## Scope Reduction

Per-paper language detection (`detect_paper_language()`) is **out of scope**.
Most academic papers are in English; calling LLM per paper has high cost with
low value. The audit is computed from source diagnostics (which query variant
was sent, how many results per source) rather than per-paper language detection.

## Decision

| Area | Choice | Rationale |
|------|--------|-----------|
| Approach | Standalone service + search integration + LangGraph node | Reusable, testable, matches existing patterns |
| Language detection | LLM-based (DeepSeek V4) | Accurate for all languages, handles short queries |
| Query variant generation | LLM-generated | Natural academic variants, not just translation |
| Per-paper language detection | **Out of scope** | High cost, low value for MVP |
| Audit computation | From source diagnostics | Which variant sent, result counts per source |
| Frontend display | Inline badges | Compact, doesn't clutter search results |
| Variant distribution | Per-source variants | Each source gets the most appropriate query |

## Architecture

### Data Flow

```
User query: "RAG y khoa tiếng Việt"
    │
    ▼
language_bias.detect_language(query) → "vi"
    │
    ▼
language_bias.generate_query_variants(query, "vi", ["en", "vi"])
    → [
        {source: "semantic_scholar", query: "RAG medical question answering", language: "en"},
        {source: "arxiv", query: "RAG medical question answering", language: "en"},
        {source: "exa", query: "RAG y khoa tiếng Việt", language: "vi"}
      ]
    │
    ▼
Fan-out: each source gets its assigned variant
    │
    ▼
Results come back → source diagnostics collected
    │
    ▼
language_bias.compute_bias_audit(source_diagnostics, "balanced")
    → {
        policy: "balanced",
        candidate_counts_by_language: {"en": 18, "vi": 7},
        english_dominance_score: 0.72,
        adjustments_applied: ["included_original_language_query"]
      }
    │
    ▼
Response: { items, language_bias_audit, query_variants, source_diagnostics }
```

### Integration Points

1. **`app/services/language_bias.py`** — standalone service (new file)
2. **`app/services/paper_search.py`** — call language bias before/after fan-out
3. **`app/schemas/paper.py`** — add `QueryVariant`, `LanguageBiasAudit` models
4. **`app/ai/prompts.py`** — add `LANGUAGE_BIAS_*` prompts
5. **`app/agents/nodes.py`** — implement `language_bias_agent_node`
6. **`app/agents/state.py`** — add `query_variants`, `language_bias_audit` to state
7. **`app/agents/graph.py`** — wire node into graph
8. **`frontend/app/(app)/search/page.tsx`** — render audit badges

## Files to Create

| File | Purpose |
|------|---------|
| `app/services/language_bias.py` | Core service: detect, generate variants, compute audit |
| `tests/test_language_bias.py` | Unit tests |

## Files to Modify

| File | Change |
|------|--------|
| `app/ai/prompts.py` | Add `LANGUAGE_BIAS_SYSTEM`, `LANGUAGE_BIAS_USER` |
| `app/schemas/paper.py` | Add `QueryVariant`, `LanguageBiasAudit`; update `PaperSearchRequest`, `PaperSearchResponse` |
| `app/services/paper_search.py` | Call language bias service in search flow |
| `app/agents/nodes.py` | Add `language_bias_agent_node` |
| `app/agents/state.py` | Add `query_variants`, `language_bias_audit` fields |
| `app/agents/graph.py` | Wire `language_bias` node |
| `frontend/app/(app)/search/page.tsx` | Render language audit badges + query variants |
| `frontend/lib/types.ts` | Add `QueryVariant`, `LanguageBiasAudit` types |

## Detailed Design

### 1. Prompts (`app/ai/prompts.py`)

Add after existing prompts:

```python
LANGUAGE_BIAS_SYSTEM = """\
You are a multilingual research search specialist. Your job is to detect the
language of a research query and generate optimized search variants for
different academic sources.

Rules:
- Detect the primary language of the query (ISO 639-1 code).
- Always generate an English variant optimized for academic APIs.
- If the query is not in English, also generate a variant in the original
  language for sources that may have non-English coverage.
- Each variant should include the target source and language.
- Academic APIs (Semantic Scholar, arXiv, OpenAlex) work best with English.
- Exa and Firecrawl can handle original-language queries for broader discovery.
- Keep queries specific and academic in tone.
"""

LANGUAGE_BIAS_USER = """\
Research query: {query}
Detected language: {detected_language}
Target languages: {target_languages}

Generate optimized search variants for each source.
"""
```

### 2. Service (`app/services/language_bias.py`)

```python
from dataclasses import dataclass

@dataclass
class QueryVariant:
    source: str          # "semantic_scholar", "arxiv", "exa", etc.
    query: str           # the actual query text
    language: str        # ISO 639-1

@dataclass
class LanguageBiasAudit:
    policy: str                                          # "balanced", "original_first", "english_first"
    candidate_counts_by_language: dict[str, int]         # {"en": 18, "vi": 7}
    english_dominance_score: float                       # 0.0-1.0
    adjustments_applied: list[str]                       # list of adjustments


async def detect_language(text: str) -> str:
    """Detect primary language of text via LLM. Returns ISO 639-1 code."""


async def generate_query_variants(
    query: str,
    detected_language: str,
    target_languages: list[str],
) -> list[QueryVariant]:
    """Generate per-source query variants via LLM.

    Returns list of QueryVariant with source, query, language.
    Each academic source gets the variant most likely to produce good results.
    """


def assign_variants_to_sources(
    variants: list[QueryVariant],
    enabled_sources: list[str],
) -> dict[str, str]:
    """Map each source to its best query variant.

    Academic APIs → English variant.
    Exa/Firecrawl → original-language variant (if available).
    """


def compute_bias_audit(
    source_diagnostics: list[dict],
    policy: str,
    query_variants: list[QueryVariant],
) -> LanguageBiasAudit:
    """Compute language coverage audit from source diagnostics.

    Uses source result counts and the language of the query variant sent
    to each source. Does NOT detect per-paper language (out of scope).
    """
```

### 3. Schemas (`app/schemas/paper.py`)

Add:

```python
class QueryVariant(BaseModel):
    source: str
    query: str
    language: str

class LanguageBiasAudit(BaseModel):
    policy: str
    candidate_counts_by_language: dict[str, int]
    english_dominance_score: float
    adjustments_applied: list[str]
```

Update `PaperSearchRequest`:

```python
class PaperSearchRequest(BaseModel):
    # ... existing fields ...
    target_languages: list[str] = Field(
        default_factory=list,
        description="Preferred languages for query variants, e.g. ['en', 'vi']",
    )
    language_policy: str = Field(
        default="balanced",
        description="Language bias policy: 'balanced', 'original_first', or 'english_first'",
    )
```

Update `PaperSearchResponse`:

```python
class PaperSearchResponse(BaseModel):
    # ... existing fields ...
    detected_language: str | None = None
    query_variants: list[QueryVariant] = Field(default_factory=list)
    language_bias_audit: LanguageBiasAudit | None = None
```

### 4. Search Integration (`app/services/paper_search.py`)

Update `search_and_download()`:

```python
async def search_and_download(request: PaperSearchRequest) -> SearchOutcome:
    # 1. Detect language
    detected_lang = await detect_language(request.query)

    # 2. Generate variants
    target_langs = request.target_languages or [detected_lang, "en"]
    variants = await generate_query_variants(
        request.query, detected_lang, target_langs
    )

    # 3. Assign variants to sources
    source_query_map = assign_variants_to_sources(variants, enabled_sources)

    # 4. Fan-out with per-source queries
    # (existing fan-out code, but use source_query_map instead of raw query)

    # 5. Compute audit from source diagnostics
    audit = compute_bias_audit(source_diagnostics, request.language_policy, variants)

    # 6. Build response with audit fields
    return SearchOutcome(
        response=PaperSearchResponse(
            ...,
            detected_language=detected_lang,
            query_variants=[QueryVariant(...) for v in variants],
            language_bias_audit=audit,
        ),
        ...
    )
```

### 5. LangGraph Node (`app/agents/nodes.py`)

```python
async def language_bias_node(state: ResearchState) -> dict:
    """Detect language and generate query variants for the research workflow."""
    if not state.user_query:
        return {"current_node": "language_bias", "errors": ["No query in state"]}

    detected_lang = await detect_language(state.user_query)
    target_langs = [detected_lang, "en"]
    if detected_lang == "en":
        target_langs = ["en"]

    variants = await generate_query_variants(
        state.user_query, detected_lang, target_langs
    )

    return {
        "detected_language": detected_lang,
        "query_variants": [asdict(v) for v in variants],
        "current_node": "language_bias",
    }
```

### 6. State Update (`app/agents/state.py`)

Add fields:

```python
class ResearchState(TypedDict, total=False):
    # ... existing fields ...
    detected_language: str
    query_variants: list[dict]
    language_bias_audit: dict
```

### 7. Graph Update (`app/agents/graph.py`)

```python
graph.add_node("language_bias", _wrap(language_bias_node))
graph.add_edge("search_agent", "language_bias")
graph.add_edge("language_bias", "crawl_enrichment")
```

### 8. Frontend (`frontend/app/(app)/search/page.tsx`)

Add after search bar, before results:

```tsx
{sessionData?.language_bias_audit && (
  <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
    <span className="px-2 py-0.5 rounded bg-surface-bone">
      Language: {sessionData.detected_language}
    </span>
    <span className="px-2 py-0.5 rounded bg-surface-bone">
      Policy: {sessionData.language_bias_audit.policy}
    </span>
    {Object.entries(sessionData.language_bias_audit.candidate_counts_by_language).map(([lang, count]) => (
      <span key={lang} className="px-2 py-0.5 rounded bg-surface-bone">
        {lang.toUpperCase()}: {count}
      </span>
    ))}
    <span className={`px-2 py-0.5 rounded ${
      sessionData.language_bias_audit.english_dominance_score < 0.7 ? "bg-green-100 text-green-800" :
      sessionData.language_bias_audit.english_dominance_score < 0.85 ? "bg-yellow-100 text-yellow-800" :
      "bg-red-100 text-red-800"
    }`}>
      EN: {Math.round(sessionData.language_bias_audit.english_dominance_score * 100)}%
    </span>
  </div>
)}
```

Query variants (collapsible):

```tsx
{sessionData?.query_variants && sessionData.query_variants.length > 0 && (
  <details className="mb-3">
    <summary className="text-xs text-muted-foreground cursor-pointer">
      Query variants sent ({sessionData.query_variants.length})
    </summary>
    <div className="mt-1 space-y-1">
      {sessionData.query_variants.map((v, i) => (
        <div key={i} className="text-xs text-muted-foreground pl-3">
          <span className="font-medium">{v.source}:</span> {v.query}
          <span className="ml-1 px-1 rounded bg-surface-bone">{v.language}</span>
        </div>
      ))}
    </div>
  </details>
)}
```

## Edge Cases

1. **Query is already English**: Only generate English variant. Audit shows 100% EN.
2. **Very short query (< 5 chars)**: LLM may struggle with detection. Default to "en".
3. **Mixed-language query**: LLM detects dominant language.
4. **All sources return 0 results for non-English variant**: Audit shows that variant was tried but yielded nothing.
5. **LLM detection fails**: Default to "en", proceed without variants.

## Testing

- `detect_language("RAG y khoa")` → "vi"
- `detect_language("machine learning for NLP")` → "en"
- `generate_query_variants("RAG y khoa", "vi", ["en", "vi"])` → returns variants for both languages
- `compute_bias_audit(...)` → correct english_dominance_score
- Integration: search with Vietnamese query returns language_bias_audit
- Edge case: empty query, English-only query, LLM failure
