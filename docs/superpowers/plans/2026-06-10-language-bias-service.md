# Language Bias Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add language detection, query variant generation, and bias audit to the paper search flow (sync + LangGraph) with frontend display.

**Architecture:** Standalone `language_bias.py` service with one combined LLM call for detect + variants. Audit computed from source diagnostics (result counts per language variant sent). Sync flow calls service in `search_and_download()`. LangGraph node wraps service. Frontend renders inline badges.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, LangGraph, DeepSeek V4, Next.js 16

**Key insight:** `query_planner_node` already generates `detected_language` + `query_variants` in LangGraph. The language_bias node just needs to compute `language_bias_audit` from `source_diagnostics`.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `app/ai/prompts.py` | **Modify** | Add `LANGUAGE_BIAS_SYSTEM`, `LANGUAGE_BIAS_USER` |
| `app/services/language_bias.py` | **Create** | detect_language, generate_query_variants, compute_bias_audit |
| `app/schemas/paper.py` | **Modify** | Add QueryVariant, LanguageBiasAudit; update request/response |
| `app/services/paper_search.py` | **Modify** | Call language bias in search flow |
| `app/services/search_session.py` | **Modify** | Store language bias fields on SearchRun |
| `app/routers/search_session.py` | **Modify** | Store and return language bias in sessions |
| `app/agents/nodes.py` | **Modify** | Add `language_bias_node` |
| `app/agents/state.py` | **Modify** | Add `language_bias_audit` field |
| `app/agents/graph.py` | **Modify** | Wire language_bias node |
| `frontend/lib/types.ts` | **Modify** | Add QueryVariant, LanguageBiasAudit types |
| `frontend/app/(app)/search/page.tsx` | **Modify** | Render language audit badges |
| `tests/test_language_bias.py` | **Create** | Unit tests |

---

### Task 1: Add Language Bias Prompts

**Files:**
- Modify: `app/ai/prompts.py` (append after line 383)

- [ ] **Step 1: Add prompts to end of prompts.py**

```python
# ── Language Bias ─────────────────────────────────────────────────────────────

LANGUAGE_BIAS_SYSTEM = """\
You are a multilingual research search specialist. Detect the language of a
research query and generate optimized search variants for academic sources.

Rules:
- Detect the primary language of the query. Return the ISO 639-1 code.
- Always generate an English variant optimized for academic APIs (Semantic Scholar, arXiv).
- If the query is not in English, also generate a variant in the original
  language for broader discovery sources (Exa, Firecrawl).
- Keep variants specific and academic in tone. Do not just translate literally
  — optimize each variant for the target source.
- Return 2-4 variants total.
"""

LANGUAGE_BIAS_USER = """\
Research query: {query}

Detect language and generate optimized search variants.
"""
```

- [ ] **Step 2: Verify prompts import**

Run: `python -c "from app.ai.prompts import LANGUAGE_BIAS_SYSTEM, LANGUAGE_BIAS_USER; print('OK')"`
Expected: `OK`

---

### Task 2: Create Language Bias Service

**Files:**
- Create: `app/services/language_bias.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_language_bias.py`:

```python
"""Tests for language bias service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.language_bias import (
    LanguageBiasAudit,
    QueryVariant,
    compute_bias_audit,
    detect_and_generate_variants,
)


@pytest.mark.asyncio
async def test_detect_and_generate_english_query():
    mock_provider = AsyncMock()
    mock_provider.complete_structured.return_value = {
        "detected_language": "en",
        "variants": [
            {"source": "semantic_scholar", "query": "machine learning for NLP", "language": "en"},
            {"source": "arxiv", "query": "machine learning natural language processing", "language": "en"},
        ],
    }
    with patch("app.services.language_bias.get_provider", return_value=mock_provider):
        variants, detected_lang = await detect_and_generate_variants(
            "machine learning for NLP", ["en"]
        )

    assert detected_lang == "en"
    assert len(variants) >= 1
    assert all(v.language == "en" for v in variants)


@pytest.mark.asyncio
async def test_detect_and_generate_vietnamese_query():
    mock_provider = AsyncMock()
    mock_provider.complete_structured.return_value = {
        "detected_language": "vi",
        "variants": [
            {"source": "semantic_scholar", "query": "RAG medical question answering", "language": "en"},
            {"source": "arxiv", "query": "retrieval augmented generation medical QA", "language": "en"},
            {"source": "exa", "query": "RAG hỏi đáp y khoa tiếng Việt", "language": "vi"},
        ],
    }
    with patch("app.services.language_bias.get_provider", return_value=mock_provider):
        variants, detected_lang = await detect_and_generate_variants(
            "RAG hỏi đáp y khoa", ["en", "vi"]
        )

    assert detected_lang == "vi"
    assert len(variants) >= 2
    lang_set = {v.language for v in variants}
    assert "en" in lang_set
    assert "vi" in lang_set


def test_compute_bias_audit_all_english():
    variants = [
        QueryVariant(source="semantic_scholar", query="ML for NLP", language="en"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 25},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert audit.policy == "balanced"
    assert audit.candidate_counts_by_language["en"] == 25
    assert audit.english_dominance_score == 1.0


def test_compute_bias_audit_mixed():
    variants = [
        QueryVariant(source="semantic_scholar", query="RAG medical QA", language="en"),
        QueryVariant(source="arxiv", query="RAG medical QA", language="en"),
        QueryVariant(source="exa", query="RAG y khoa", language="vi"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 15},
        {"source": "arxiv", "status": "ok", "result_count": 8},
        {"source": "exa", "status": "ok", "result_count": 5},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert audit.candidate_counts_by_language["en"] == 23
    assert audit.candidate_counts_by_language["vi"] == 5
    assert 0.0 < audit.english_dominance_score < 1.0


def test_compute_bias_audit_with_failed_source():
    variants = [
        QueryVariant(source="semantic_scholar", query="test", language="en"),
        QueryVariant(source="exa", query="kiểm tra", language="vi"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 10},
        {"source": "exa", "status": "failed", "result_count": 0, "message": "timeout"},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert audit.candidate_counts_by_language["en"] == 10
    assert audit.candidate_counts_by_language["vi"] == 0
    assert audit.english_dominance_score == 1.0


def test_compute_bias_audit_adjustments():
    variants = [
        QueryVariant(source="semantic_scholar", query="test", language="en"),
        QueryVariant(source="exa", query="kiểm tra", language="vi"),
    ]
    diagnostics = [
        {"source": "semantic_scholar", "status": "ok", "result_count": 10},
        {"source": "exa", "status": "ok", "result_count": 2},
    ]
    audit = compute_bias_audit(diagnostics, "balanced", variants)

    assert "included_original_language_query" in audit.adjustments_applied


@pytest.mark.asyncio
async def test_detect_llm_failure_graceful():
    mock_provider = AsyncMock()
    mock_provider.complete_structured.side_effect = Exception("LLM timeout")
    with patch("app.services.language_bias.get_provider", return_value=mock_provider):
        variants, detected_lang = await detect_and_generate_variants("test", ["en"])

    assert detected_lang == "en"
    assert len(variants) == 1
    assert variants[0].source == "semantic_scholar"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_language_bias.py -v`
Expected: All FAIL with "Module not found" or "function not defined"

- [ ] **Step 3: Create the service file**

Create `app/services/language_bias.py`:

```python
"""Language bias detection, query variant generation, and audit computation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.ai.prompts import LANGUAGE_BIAS_SYSTEM, LANGUAGE_BIAS_USER
from app.ai.provider import get_provider

logger = logging.getLogger(__name__)


@dataclass
class QueryVariant:
    source: str
    query: str
    language: str


@dataclass
class LanguageBiasAudit:
    policy: str = "balanced"
    candidate_counts_by_language: dict[str, int] = field(default_factory=dict)
    english_dominance_score: float = 0.0
    adjustments_applied: list[str] = field(default_factory=list)


async def detect_and_generate_variants(
    query: str,
    target_languages: list[str],
) -> tuple[list[QueryVariant], str]:
    """Detect query language and generate search variants in one LLM call.

    Returns (variants, detected_language).
    Falls back gracefully on LLM failure.
    """
    try:
        provider = get_provider()
        user_msg = LANGUAGE_BIAS_USER.format(query=query)
        result = await provider.complete_structured(
            messages=[{"role": "user", "content": user_msg}],
            system=LANGUAGE_BIAS_SYSTEM,
            schema={
                "type": "object",
                "properties": {
                    "detected_language": {"type": "string"},
                    "variants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "query": {"type": "string"},
                                "language": {"type": "string"},
                            },
                            "required": ["source", "query", "language"],
                        },
                        "minItems": 1,
                        "maxItems": 5,
                    },
                },
                "required": ["detected_language", "variants"],
            },
            tool_name="language_bias",
            max_tokens=1000,
        )
        detected_lang = result.get("detected_language", "en")
        variants = [
            QueryVariant(
                source=v["source"],
                query=v["query"],
                language=v["language"],
            )
            for v in result.get("variants", [])
        ]
        if not variants:
            variants = [QueryVariant(source="semantic_scholar", query=query, language=detected_lang)]

        return variants, detected_lang

    except Exception as exc:
        logger.warning("Language bias detection failed: %s, falling back to 'en'", exc)
        return [QueryVariant(source="semantic_scholar", query=query, language="en")], "en"


def assign_variants_to_sources(
    variants: list[QueryVariant],
    all_sources: list[str],
) -> dict[str, str]:
    """Map each source to the best query from the variants list.

    Academic sources (semantic_scholar, arxiv) get English variant.
    Discovery sources (exa, firecrawl) get original-language variant if available.
    Falls back to first variant if no language match.
    """
    variant_map: dict[str, str] = {}

    en_variants = [v for v in variants if v.language == "en"]
    non_en_variants = [v for v in variants if v.language != "en"]
    academic_sources = {"semantic_scholar", "arxiv", "openalex"}
    discovery_sources = {"exa", "firecrawl"}

    for src in all_sources:
        if src in academic_sources:
            chosen = en_variants[0] if en_variants else variants[0]
        elif src in discovery_sources:
            chosen = non_en_variants[0] if non_en_variants else en_variants[0] if en_variants else variants[0]
        else:
            chosen = variants[0]
        variant_map[src] = chosen.query

    return variant_map


def compute_bias_audit(
    source_diagnostics: list[dict],
    policy: str,
    variants: list[QueryVariant],
) -> LanguageBiasAudit:
    """Compute language coverage audit from source diagnostics.

    Maps each source's result count to the language of the variant sent.
    Computes english_dominance_score = en_count / total_count.
    """
    adjustments: list[str] = []

    variant_lang_map: dict[str, str] = {}
    for v in variants:
        variant_lang_map[v.source] = v.language

    has_non_en = any(v.language != "en" for v in variants)
    if has_non_en:
        adjustments.append("included_original_language_query")

    counts: dict[str, int] = {}
    for diag in source_diagnostics:
        count = diag.get("result_count", 0)
        if count <= 0:
            continue
        source_name = diag.get("source", "")
        lang = variant_lang_map.get(source_name, "en")
        counts[lang] = counts.get(lang, 0) + count

    total = sum(counts.values()) or 1
    en_count = counts.get("en", 0)
    score = round(en_count / total, 2)

    return LanguageBiasAudit(
        policy=policy,
        candidate_counts_by_language=counts,
        english_dominance_score=score,
        adjustments_applied=adjustments,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_language_bias.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/language_bias.py tests/test_language_bias.py app/ai/prompts.py
git commit -m "feat: add language bias service with detect, variants, audit"
```

---

### Task 3: Update Schemas

**Files:**
- Modify: `app/schemas/paper.py`

- [ ] **Step 1: Add QueryVariant and LanguageBiasAudit models**

Add after `PaperSearchRequest` (after line 27):

```python
class QueryVariant(BaseModel):
    source: str
    query: str
    language: str


class LanguageBiasAudit(BaseModel):
    policy: str = "balanced"
    candidate_counts_by_language: dict[str, int] = Field(default_factory=dict)
    english_dominance_score: float = 0.0
    adjustments_applied: list[str] = Field(default_factory=list)
```

- [ ] **Step 2: Update PaperSearchRequest**

Replace the existing `PaperSearchRequest` (lines 10-27):

```python
class PaperSearchRequest(BaseModel):
    query: str = Field(
        ..., description="Natural-language search query", min_length=2, max_length=500
    )
    limit: int = Field(default=50, description="Max papers to return", ge=1, le=500)
    year_from: int | None = Field(
        default=None, description="Earliest publication year", ge=1900, le=2100
    )
    year_to: int | None = Field(
        default=None, description="Latest publication year", ge=1900, le=2100
    )
    download_pdfs: bool = Field(
        default=True,
        description="Automatically download full-text PDFs for returned papers",
    )
    target_languages: list[str] = Field(
        default_factory=list,
        description="Preferred languages for query variants, e.g. ['en', 'vi']",
    )
    language_policy: str = Field(
        default="balanced",
        description="Language bias policy: 'balanced', 'original_first', or 'english_first'",
    )
```

- [ ] **Step 3: Update PaperSearchResponse**

Add fields to `PaperSearchResponse` (after line 73):

Replace lines 63-73 with:

```python
class PaperSearchResponse(BaseModel):
    query: str
    total_found: int
    total_returned: int
    search_time_ms: float
    download_time_ms: float | None = None
    pdfs_downloaded: int = 0
    pdfs_failed: int = 0
    papers: list[PaperResult]
    detected_language: str | None = None
    query_variants: list[QueryVariant] = Field(default_factory=list)
    language_bias_audit: LanguageBiasAudit | None = None
    source_diagnostics: list[dict] = Field(default_factory=list)
```

- [ ] **Step 4: Verify schemas compile**

Run: `python -c "from app.schemas.paper import PaperSearchResponse, QueryVariant, LanguageBiasAudit; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/schemas/paper.py
git commit -m "feat: add language bias schemas to paper search request/response"
```

---

### Task 4: Integrate into Sync Search Flow

**Files:**
- Modify: `app/services/paper_search.py`

- [ ] **Step 1: Update imports in paper_search.py**

Add to imports (after line 24):

```python
from app.services.language_bias import (
    compute_bias_audit,
    detect_and_generate_variants,
)
from app.schemas.paper import LanguageBiasAudit, QueryVariant as QueryVariantSchema
```

- [ ] **Step 2: Add language bias calls in search_and_download**

Insert after line 58 (after `# ── 1. Search ──` comment), replace lines 59-67:

```python
    # ── 1. Language bias: detect + generate variants ─────────────────────
    detected_lang = "en"
    variants: list = []
    source_diagnostics: list[dict] = []

    try:
        variants, detected_lang = await detect_and_generate_variants(
            request.query,
            request.target_languages or [detected_lang, "en"],
        )
    except Exception as exc:
        logger.warning("Language bias detection failed: %s", exc)

    # ── 2. Search ────────────────────────────────────────────────────────
    t0 = time.monotonic()
    all_raw: list[RawPaper] = []

    # Determine which sources to use based on variants
    source_query_map: dict[str, str] = {}
    for v in variants:
        source_query_map[v.source] = v.query

    if not source_query_map:
        source_query_map["semantic_scholar"] = request.query

    for src_name, src_query in source_query_map.items():
        try:
            if src_name == "semantic_scholar":
                source = PaperHubSource()
            elif src_name == "arxiv":
                from app.sources.arxiv import ArxivSource
                source = ArxivSource()
            elif src_name == "openalex":
                from app.sources.openalex import OpenAlexSource
                source = OpenAlexSource()
            else:
                source_diagnostics.append({
                    "source": src_name,
                    "status": "skipped",
                    "result_count": 0,
                    "message": f"Source '{src_name}' not implemented",
                })
                continue

            papers = await source.search(
                query=src_query,
                limit=min(request.limit, 100),
                year_from=request.year_from,
                year_to=request.year_to,
            )
            all_raw.extend(papers)
            source_diagnostics.append({
                "source": src_name,
                "status": "ok",
                "result_count": len(papers),
            })
        except Exception as exc:
            logger.warning("Source %s failed: %s", src_name, exc)
            source_diagnostics.append({
                "source": src_name,
                "status": "failed",
                "result_count": 0,
                "message": str(exc)[:200],
            })

    search_ms = round((time.monotonic() - t0) * 1000, 1)
    raw_papers = _deduplicate_raw_books(all_raw)
    raw_papers = raw_papers[:request.limit]
```

- [ ] **Step 3: Add deduplication helper**

Add before `_classify_pdf_source`:

```python
def _deduplicate_raw_books(papers: list[RawPaper]) -> list[RawPaper]:
    """Deduplicate by strongest identifier, preserving order."""
    seen: set[str] = set()
    result: list[RawPaper] = []
    for p in papers:
        key = p.semantic_scholar_id or p.arxiv_id or p.doi or p.title.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result
```

- [ ] **Step 4: Add audit computation and variant data to response**

Insert before line 161 (`response = PaperSearchResponse(...)`), replace lines 161-170:

```python
    # ── 5. Compute language bias audit ──────────────────────────────────
    audit: LanguageBiasAudit | None = None
    if source_diagnostics:
        try:
            audit = compute_bias_audit(
                source_diagnostics,
                request.language_policy,
                variants,
            )
        except Exception as exc:
            logger.warning("Failed to compute bias audit: %s", exc)

    # Build schema-level variants for response
    response_variants = [
        QueryVariantSchema(source=v.source, query=v.query, language=v.language)
        for v in variants
    ]

    response = PaperSearchResponse(
        query=request.query,
        total_found=len(raw_papers),
        total_returned=len(raw_papers),
        search_time_ms=search_ms,
        download_time_ms=download_ms,
        pdfs_downloaded=pdfs_downloaded,
        pdfs_failed=pdfs_failed,
        papers=results,
        detected_language=detected_lang,
        query_variants=response_variants,
        language_bias_audit=audit,
        source_diagnostics=source_diagnostics,
    )
```

- [ ] **Step 5: Verify the file compiles**

Run: `python -c "from app.services.paper_search import search_and_download; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app/services/paper_search.py
git commit -m "feat: integrate language bias into sync search flow"
```

---

### Task 4b: Store Language Bias in Search Sessions

**Files:**
- Modify: `app/services/search_session.py`

- [ ] **Step 1: Update create_search_session signature**

Replace the existing `create_search_session` function (lines 20-37):

```python
async def create_search_session(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    query: str,
    results: list[dict],
    total_found: int,
    detected_language: str | None = None,
    language_policy: str = "balanced",
    target_languages: list[str] | None = None,
    english_dominance_score: float | None = None,
) -> SearchRun:
    run = SearchRun(
        project_id=project_id,
        user_query=query,
        total_results=total_found,
        results_json=results,
        detected_language=detected_language,
        language_policy=language_policy,
        target_languages=target_languages,
        english_dominance_score=english_dominance_score,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.services.search_session import create_search_session; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/search_session.py
git commit -m "feat: store language bias fields in search sessions"
```

---

### Task 4c: Return Language Bias in Session Detail

**Files:**
- Modify: `app/routers/search_session.py`

- [ ] **Step 1: Update SessionDetailResponse**

Add fields to `SessionDetailResponse` (after line 80):

```python
    detected_language: str | None = None
    query_variants: list[dict] = []
    language_bias_audit: dict | None = None
    source_diagnostics: list[dict] = []
```

- [ ] **Step 2: Update create_session endpoint**

Replace lines 92-98 to pass language bias data:

```python
    search_req = PaperSearchRequest(query=request.query, limit=request.limit, download_pdfs=False)
    outcome = await search_and_download(search_req)
    results = [p.model_dump() for p in outcome.response.papers]

    audit_data = outcome.response.language_bias_audit
    run = await create_search_session(
        db, user, request.project_id, request.query, results, outcome.response.total_found,
        detected_language=outcome.response.detected_language,
        english_dominance_score=audit_data.english_dominance_score if audit_data else None,
    )
```

- [ ] **Step 3: Update return statement in create_session**

Replace lines 106-118:

```python
    audit = outcome.response.language_bias_audit
    resp_audit = audit.model_dump() if audit else None
    resp_variants = [v.model_dump() for v in outcome.response.query_variants]

    return SessionDetailResponse(
        id=run.id,
        project_id=run.project_id,
        user_query=run.user_query,
        total_results=run.total_results,
        screening_scores=[],
        created_at=str(run.created_at),
        page=1,
        page_size=page_size,
        total_pages=total_pages,
        papers=page_result,
        saved_paper_ids=saved_ids,
        detected_language=outcome.response.detected_language,
        query_variants=resp_variants,
        language_bias_audit=resp_audit,
        source_diagnostics=outcome.response.source_diagnostics,
    )
```

- [ ] **Step 4: Verify compiles**

Run: `python -c "from app.routers.search_session import router; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/routers/search_session.py
git commit -m "feat: return language bias audit in session detail"
```

---

### Task 5: Add language_bias_audit to ResearchState

**Files:**
- Modify: `app/agents/state.py`

- [ ] **Step 1: Add field**

Add after line 28 (after `query_variants`):

```python
    language_bias_audit: dict = field(default_factory=dict)  # {policy, candidate_counts_by_language, ...}
```

- [ ] **Step 2: Verify**

Run: `python -c "from app.agents.state import ResearchState; s = ResearchState(project_id='00000000-0000-0000-0000-000000000000', user_id='00000000-0000-0000-0000-000000000000'); print(s.language_bias_audit)"`
Expected: `{}`

- [ ] **Step 3: Commit**

```bash
git add app/agents/state.py
git commit -m "feat: add language_bias_audit to ResearchState"
```

---

### Task 6: Add language_bias Node

**Files:**
- Modify: `app/agents/nodes.py`

- [ ] **Step 1: Add language_bias_node**

Add after `search_agent_node` (after line ~195, find the end of search_agent_node function):

```python
# ── Node 1b: Language Bias Audit ─────────────────────────────────────────


async def language_bias_node(state: ResearchState) -> dict:
    """Compute language coverage audit from search diagnostics."""
    from app.services.language_bias import LanguageBiasAudit, compute_bias_audit

    diagnostics = state.source_diagnostics or {}
    variants = state.query_variants or []

    if not diagnostics or not variants:
        return {
            "current_node": "language_bias",
            "language_bias_audit": {"policy": "balanced", "candidate_counts_by_language": {}, "english_dominance_score": 0.0, "adjustments_applied": []},
        }

    variant_objects = []
    for v in variants:
        variant_objects.append(type("V", (), {"source": v.get("sources", ["semantic_scholar"])[0] if isinstance(v.get("sources"), list) and v["sources"] else "semantic_scholar", "query": v.get("query", ""), "language": v.get("language", "en")}))

    diag_list = []
    for src_name, info in diagnostics.items():
        diag_list.append({
            "source": src_name,
            "status": info.get("status", "skipped"),
            "result_count": info.get("count", 0),
            "message": info.get("error"),
        })

    audit = compute_bias_audit(diag_list, "balanced", variant_objects)

    return {
        "current_node": "language_bias",
        "language_bias_audit": {
            "policy": audit.policy,
            "candidate_counts_by_language": audit.candidate_counts_by_language,
            "english_dominance_score": audit.english_dominance_score,
            "adjustments_applied": audit.adjustments_applied,
        },
    }
```

- [ ] **Step 2: Verify compiles**

Run: `python -c "from app.agents.nodes import language_bias_node; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/agents/nodes.py
git commit -m "feat: add language_bias_node to compute audit from diagnostics"
```

---

### Task 7: Wire language_bias into Graph

**Files:**
- Modify: `app/agents/graph.py`

- [ ] **Step 1: Add import**

Add `language_bias_node` to the import block (line 15-24):

```python
from app.agents.nodes import (
    citation_validator_node,
    conflict_detection_node,
    gap_analysis_node,
    language_bias_node,
    matrix_extraction_node,
    query_planner_node,
    review_writer_node,
    save_screened_node,
    search_agent_node,
)
```

- [ ] **Step 2: Add node and update edges**

Add node after `search_agent` (after line 57):

```python
    graph.add_node("language_bias", _wrap(language_bias_node))
```

Update edges (replace lines 67-68):

```python
    graph.add_edge("query_planner", "search_agent")
    graph.add_edge("search_agent", "language_bias")
    graph.add_edge("language_bias", "save_screened")
```

- [ ] **Step 3: Verify graph compiles**

Run: `python -c "from app.agents.graph import build_research_graph; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/agents/graph.py
git commit -m "feat: wire language_bias node into research graph"
```

---

### Task 8: Update Frontend Types

**Files:**
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Add new types**

Find the existing types file and add:

```typescript
export interface QueryVariant {
  source: string;
  query: string;
  language: string;
}

export interface LanguageBiasAudit {
  policy: string;
  candidate_counts_by_language: Record<string, number>;
  english_dominance_score: number;
  adjustments_applied: string[];
}
```

Add to `SessionDetailResponse`:

```typescript
export interface SessionDetailResponse {
  // ... existing fields ...
  detected_language?: string | null;
  query_variants?: QueryVariant[];
  language_bias_audit?: LanguageBiasAudit | null;
  source_diagnostics?: Array<{
    source: string;
    status: string;
    result_count: number;
    message?: string;
  }>;
}
```

- [ ] **Step 2: Verify frontend typecheck**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No new errors from these changes

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat: add language bias types to frontend"
```

---

### Task 9: Render Language Audit in Frontend

**Files:**
- Modify: `frontend/app/(app)/search/page.tsx`

- [ ] **Step 1: Add language audit badges after search bar**

After the search bar section and before the `{sessionData && (...)}` results section, add:

```tsx
{/* Language bias audit */}
{sessionData?.language_bias_audit && (
  <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3 flex-wrap">
    {sessionData.detected_language && (
      <span className="px-2 py-0.5 rounded bg-surface-bone">
        Language: {sessionData.detected_language}
      </span>
    )}
    <span className="px-2 py-0.5 rounded bg-surface-bone">
      Policy: {sessionData.language_bias_audit.policy}
    </span>
    {Object.entries(sessionData.language_bias_audit.candidate_counts_by_language).map(([lang, count]) => (
      <span key={lang} className="px-2 py-0.5 rounded bg-surface-bone">
        {lang.toUpperCase()}: {count}
      </span>
    ))}
    <span className={`px-2 py-0.5 rounded font-medium ${
      sessionData.language_bias_audit.english_dominance_score < 0.7
        ? "bg-green-100 text-green-800"
        : sessionData.language_bias_audit.english_dominance_score < 0.85
          ? "bg-yellow-100 text-yellow-800"
          : "bg-red-100 text-red-800"
    }`}>
      EN: {Math.round(sessionData.language_bias_audit.english_dominance_score * 100)}%
    </span>
  </div>
)}

{/* Query variants (collapsible) */}
{sessionData?.query_variants && sessionData.query_variants.length > 0 && (
  <details className="mb-3">
    <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
      Query variants sent ({sessionData.query_variants.length})
    </summary>
    <div className="mt-1.5 space-y-1">
      {sessionData.query_variants.map((v, i) => (
        <div key={i} className="text-xs text-muted-foreground pl-3 flex items-center gap-1.5">
          <span className="font-medium min-w-[100px]">{v.source}:</span>
          <span>{v.query}</span>
          <span className="ml-auto px-1 rounded bg-surface-bone text-[10px]">{v.language}</span>
        </div>
      ))}
    </div>
  </details>
)}
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(app\)/search/page.tsx
git commit -m "feat: render language bias audit badges in search UI"
```

---

### Task 10: Run All Tests and Lint

- [ ] **Step 1: Run all backend tests**

Run: `pytest tests/ -v`
Expected: All pass

- [ ] **Step 2: Run backend linter**

Run: `ruff check app/services/language_bias.py app/schemas/paper.py app/services/paper_search.py app/agents/nodes.py app/agents/graph.py app/agents/state.py`
Expected: No errors

- [ ] **Step 3: Run frontend typecheck**

Run: `cd frontend && npx tsc --noEmit --pretty`
Expected: No new errors (pre-existing errors OK)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete language bias service integration"
```
