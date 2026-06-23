# Auto Search & Save — Design Spec

**Date**: 2026-06-23
**Owner**: Dear Husband's request
**Status**: Approved (Approach B + Architecture)

## 1. Goals

Add an "Auto Search" button to the search page that:
1. Searches across **all wired paper sources** (Semantic Scholar, arXiv via PaperHub, OpenAlex via PaperHub, Exa)
2. Fetches a **larger pool** of candidates (200/source = ~800 raw → ~300 after dedup)
3. Uses **LLM scoring** to rank all candidates by relevance to project topic
4. **Picks top N papers** (user chooses 25 / 50 / 100) with `score=high`
5. **Auto-saves** those papers into the project
6. **Filters out** any papers that fail to save (duplicates, etc.)
7. Shows **multi-step progress** so user knows which phase is running

## 2. Non-Goals

- Per-source selection UI (auto-search always uses all wired sources)
- Manual review of papers before save (user can remove from project later)
- Custom scoring rubric (reuses existing high/medium/low system)
- Multi-language query expansion (uses project's `research_question` as-is)

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ Frontend: frontend/app/(app)/projects/[id]/search/page.tsx          │
│   Auto Search button (dropdown 25/50/100)                           │
│     ↓ click                                                         │
│   handleAutoSearch(target_count)                                     │
│     ↓ POST /api/projects/{id}/search/auto                           │
│   Frontend polls /api/papers/search/jobs/{job_id}                   │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Backend                                                             │
│   POST /api/projects/{project_id}/search/auto                       │
│     → auto_search_and_save() creates SearchRun + BackgroundJob     │
│     → _run_auto_search_job() 4-phase worker                        │
└──────────────────────────────────────────────────────────────────────┘

4-phase worker:
  Phase 1 (0-25%):   Fan-out search → 4 sources, limit=200/source
                     progress_json: {phase: "searching", current_source, papers_found}
  Phase 2 (25-60%):  Dedupe candidates, batch LLM score (25/batch)
                     progress_json: {phase: "scoring", batch_n, batches_total, papers_scored}
  Phase 3 (60-65%):  Filter score=high, pick top N, fallback to medium if insufficient
                     progress_json: {phase: "filtering", kept: N}
  Phase 4 (65-100%): Auto-save top N papers via save_paper_to_project
                     progress_json: {phase: "saving", saved, skipped, current_paper}
```

## 4. Backend Components

### 4.1 New endpoint: `POST /api/projects/{project_id}/search/auto`

**File**: `app/routers/search_session.py`

**Request body** (`AutoSearchRequest`):
```python
class AutoSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    target_count: int = Field(..., ge=10, le=100)  # 25, 50, or 100
```

**Response** (202 Accepted):
```json
{
  "job_id": "uuid",
  "session_id": "uuid",
  "target_count": 50,
  "status": "running"
}
```

**Errors**:
- `400`: `target_count` not in {25, 50, 100} (use dropdown, not free input)
- `404`: project not owned by user
- `429`: user already has running auto-search job (limit 1 concurrent)

### 4.2 New service: `auto_search_and_save`

**File**: `app/services/search_session.py`

```python
async def auto_search_and_save(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    query: str,
    target_count: int,
) -> dict:
    """Create SearchRun + BackgroundJob, launch worker, return job_id."""
    # 1. Verify project ownership
    # 2. Reject if user already has running auto_search job
    # 3. Create SearchRun with empty results_json (worker fills)
    # 4. Create BackgroundJob(job_type="auto_search", progress_json={phase: "queued", target_count})
    # 5. asyncio.ensure_future(_run_auto_search_job)
    # 6. Return {job_id, session_id, target_count, status: "running"}
```

### 4.3 New worker: `_run_auto_search_job`

**File**: `app/services/search_session.py`

```python
async def _run_auto_search_job(
    job_id: UUID, project_id: UUID, query: str,
    target_count: int, user_id: UUID,
) -> None:
    """4-phase worker. Updates job.progress_json between phases."""
    # Phase 1: Search all 4 sources in parallel
    #   - use existing search_and_download with limit=200 (per_source cap in fan-out: 100)
    #   - Bump per_source cap to 200 for this call (extend search_and_download to accept max_per_source)
    #   - Aggregate results, update progress_json after each source completes
    #   - On per-source failure, log + continue with other sources

    # Phase 2: Dedupe + batch LLM score
    #   - _deduplicate_raw_books() (existing)
    #   - Split into batches of 25 papers
    #   - Call provider.complete_structured with JSON schema expecting array of {index, score}
    #   - Aggregate scores, update progress_json after each batch
    #   - New prompt: AUTO_SEARCH_SCREEN_SYSTEM/USER (similar to PAPER_SCREEN but expects JSON array)

    # Phase 3: Filter + pick top N
    #   - Sort papers: high first, then medium, then low
    #   - Take top target_count papers where score=high
    #   - If < target_count have "high", fill remaining with "medium"
    #   - If still short, return what we have (don't pad with "low")

    # Phase 4: Auto-save top N
    #   - Loop through top N papers
    #   - Build SavePaperRequest for each
    #   - Call save_paper_to_project (returns None if duplicate)
    #   - Track saved vs skipped counts
    #   - Update progress_json after each save
    #   - Persist saved paper IDs into SearchRun.results_json (with status="saved" flag)

    # On completion:
    #   - job.status = "completed"
    #   - job.result = {session_id, saved_count, skipped_count, paper_ids: [...]}
    #   - job.completed_at = now()

    # On exception:
    #   - job.status = "failed"
    #   - job.error_message = str(exc)[:500]
    #   - job.progress_json.phase = "failed"
```

### 4.4 New prompt constants

**File**: `app/ai/prompts.py`

```python
AUTO_SEARCH_SCREEN_SYSTEM = """\
You are a paper relevance scorer. Score each paper on a 3-point scale:
- "high": highly relevant to the research topic, should be saved
- "medium": somewhat related, marginal relevance
- "low": not relevant, should be discarded

Output a JSON array. Each element: {"index": <int>, "score": "high"|"medium"|"low", "reason": "<one sentence>"}.
Indices match the input order. Be strict: most papers should be "medium" or "low"."""

AUTO_SEARCH_SCREEN_USER = """\
Research topic: {topic}
Research question: {research_question}

Papers to score (indexed from 0):
{papers_json}

Output a JSON array of {{index, score, reason}} in the same order.
"""
```

### 4.5 New Pydantic schemas

**File**: `app/schemas/paper.py`

```python
class AutoSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    target_count: int = Field(..., ge=10, le=100)

class AutoSearchResponse(BaseModel):
    job_id: str
    session_id: str
    target_count: int
    status: str
```

### 4.6 Modified: `search_and_download` accepts `max_per_source`

**File**: `app/services/paper_search.py`

Current: `paper_search.py:475-480` caps per-source at `min(limit * 2, 100)`. Change to accept explicit `max_per_source` param. Auto-search passes 200; normal search stays at default behavior (or 100).

```python
async def search_and_download(
    request: PaperSearchRequest,
    max_per_source: int | None = None,
) -> SearchOutcome:
    ...
    papers = await source.search(
        query=src_query,
        limit=min(request.limit, 500) if max_per_source is None else max_per_source,
        year_from=request.year_from, year_to=request.year_to,
    )
```

### 4.7 Modified: job status endpoint includes `progress_json`

**File**: `app/routers/search_session.py:237-248`

The existing `GET /search/jobs/{job_id}` already returns `progress_json` field on `BackgroundJob` model — just need to make sure the response includes it. Add to the `get_job_status` service if missing.

## 5. Frontend Components

### 5.1 Modified: search page

**File**: `frontend/app/(app)/projects/[id]/search/page.tsx`

Add an "Auto Search" dropdown button next to existing Search button:

```tsx
<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <Button variant="outline" disabled={isAutoSearching}>
      <SparkleIcon /> Auto Search {isAutoSearching && "(running)"}
    </Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuItem onClick={() => handleAutoSearch(25)}>
      Auto Search 25 papers
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => handleAutoSearch(50)}>
      Auto Search 50 papers
    </DropdownMenuItem>
    <DropdownMenuItem onClick={() => handleAutoSearch(100)}>
      Auto Search 100 papers
    </DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

### 5.2 New component: `AutoSearchProgress`

**File**: `frontend/components/search/AutoSearchProgress.tsx`

Multi-step progress UI showing current phase + sub-progress:

```tsx
interface Props {
  jobId: string;
  onComplete: (result: { saved_count: number; skipped_count: number }) => void;
  onError: (message: string) => void;
}

export function AutoSearchProgress({ jobId, onComplete, onError }: Props) {
  const { progress, status, result, error_message } = useJobPolling(jobId, 2000);

  // Render 4-step bar based on progress.phase
  // Show per-phase sub-progress (e.g. "Searching Semantic Scholar... 150 found")
  // On "completed": call onComplete(result)
  // On "failed": call onError(error_message)
}
```

### 5.3 Modified: search store

**File**: `frontend/lib/stores/search-store.ts`

Add new action:

```typescript
async startAutoSearch(targetCount: 25 | 50 | 100) {
  const projectId = get().selectedProjectId;
  const query = get().searchQuery;
  if (!projectId || !query) return;

  set({ isAutoSearching: true, autoSearchJobId: null });
  try {
    const resp = await apiFetch<AutoSearchResponse>(
      `/projects/${projectId}/search/auto`,
      {
        method: "POST",
        body: JSON.stringify({ query, target_count: targetCount }),
        headers: { Authorization: `Bearer ${token}` },
      },
    );
    set({ autoSearchJobId: resp.job_id, autoSearchSessionId: resp.session_id });
  } catch (err) {
    set({ isAutoSearching: false });
    throw err;
  }
},
```

## 6. Data Flow

```
1. User types query in search bar
2. User clicks "Auto Search" → picks 50
3. handleAutoSearch(50) called
4. POST /api/projects/{id}/search/auto {query, target_count: 50}
5. Backend verifies project ownership
6. Backend checks no running auto_search job for this user
7. Backend creates SearchRun (empty results_json)
8. Backend creates BackgroundJob(job_type="auto_search", progress_json={phase: "queued"})
9. Backend launches _run_auto_search_job
10. Returns 202 {job_id, session_id, target_count: 50, status: "running"}
11. Frontend opens AutoSearchProgress modal with job_id
12. Frontend polls GET /api/papers/search/jobs/{job_id} every 2s

Worker phases (server-side):
  Phase 1: search_and_download(max_per_source=200)
    - Updates progress_json: {phase: "searching", sources: [{name, status, count}]}
  Phase 2: dedupe → batch LLM score 25/batch
    - Updates progress_json: {phase: "scoring", batch_n, batches_total, papers_scored}
  Phase 3: filter + pick top N
    - Updates progress_json: {phase: "filtering", kept: N}
  Phase 4: loop save_paper_to_project
    - Updates progress_json: {phase: "saving", saved, skipped, current_paper_title}
  Completion:
    - job.status = "completed", job.result = {saved, skipped, paper_ids, session_id}

13. Frontend receives "completed" event → calls onComplete
14. Toast "Saved 50 papers" + navigate to project papers tab
```

## 7. Error Handling

| Failure | Source | Behavior |
|---|---|---|
| Single source fails in Phase 1 | Network/API | Log + continue with other sources. Partial results |
| All sources fail in Phase 1 | All sources down | job.status="failed", error="No sources returned papers" |
| LLM batch fails in Phase 2 | API timeout | Use "medium" as fallback for that batch (don't lose papers) |
| All LLM batches fail | API down | job.status="failed", error="Scoring failed" |
| `target_count` > available "high" | Few matches | Fill with "medium", log warning. If still short, return what we have |
| Per-paper save fails (Phase 4) | Duplicate/invalid | Increment `skipped`, continue. Don't fail the job |
| Total job timeout | 5 minutes | job.status="failed", error="Auto-search exceeded 5min timeout" |
| Concurrent auto-search | User clicks twice | Return 429 if user already has running auto_search job |

## 8. Constraints & Limits

| Limit | Value | Why |
|---|---|---|
| `target_count` options | 25, 50, 100 | UI dropdown, no free input |
| Max papers per source | 200 | Total ~800 raw, headroom for dedup |
| LLM batch size | 25 papers/batch | Token economy + JSON schema reliability |
| Max concurrent auto_search jobs per user | 1 | Prevent abuse |
| Hard job timeout | 5 minutes (300s) | Avoid stuck jobs |
| Max tokens per LLM call | 8K | Within provider limits |
| Max sources | 4 (current) | S2, arXiv, OpenAlex, Exa |

## 9. Testing

### Unit tests (`tests/test_auto_search.py`)

1. `test_auto_search_request_validates_target_count` — 25/50/100 OK, others rejected
2. `test_auto_search_creates_job_and_run` — service creates SearchRun + BackgroundJob
3. `test_auto_search_rejects_concurrent_job` — 2nd call returns 429
4. `test_auto_search_phase1_calls_all_sources` — worker fans out to 4 sources
5. `test_auto_search_phase2_batches_llm_score` — 100 papers → 4 batches
6. `test_auto_search_phase3_picks_top_n_high_first` — sort + filter logic
7. `test_auto_search_phase3_falls_back_to_medium` — when < N high
8. `test_auto_search_phase4_saves_each_paper` — loop save_paper_to_project
9. `test_auto_search_phase4_skips_duplicates` — None return treated as skipped
10. `test_auto_search_progress_json_updated_at_each_phase` — assert key transitions
11. `test_auto_search_timeout_fails_job` — wall-clock > 300s → failed
12. `test_auto_search_single_source_failure_continues` — Phase 1 partial

### Integration tests (`tests/test_auto_search_integration.py`)

1. `test_full_flow_with_mock_providers` — mock S2/PaperHub/Exa, mock LLM, assert 50 papers saved end-to-end
2. `test_progress_json_polling_endpoint` — GET /jobs/{id} returns progress_json correctly
3. `test_concurrent_job_limit` — user starts 2 jobs in parallel, 2nd rejected

## 10. Files to Create

| File | Purpose |
|---|---|
| `app/services/search_session.py` | MODIFY: add `auto_search_and_save` + `_run_auto_search_job` |
| `app/routers/search_session.py` | MODIFY: add `POST /search/auto` endpoint |
| `app/schemas/paper.py` | MODIFY: add `AutoSearchRequest`, `AutoSearchResponse` |
| `app/ai/prompts.py` | MODIFY: add `AUTO_SEARCH_SCREEN_SYSTEM/USER` |
| `app/services/paper_search.py` | MODIFY: accept `max_per_source` param |
| `frontend/components/search/AutoSearchProgress.tsx` | NEW: multi-step progress UI |
| `frontend/app/(app)/projects/[id]/search/page.tsx` | MODIFY: add Auto Search button |
| `frontend/lib/stores/search-store.ts` | MODIFY: add `startAutoSearch` action |
| `frontend/lib/types.ts` | MODIFY: add `AutoSearchRequest/Response` types |
| `tests/test_auto_search.py` | NEW: unit tests |

## 11. Out of Scope

- Per-source selection UI (auto-search always uses all wired sources)
- Manual review of papers before save (user can remove from project later)
- Custom scoring rubric (reuses existing high/medium/low system)
- Multi-language query expansion (uses project's `research_question` as-is)
- SSE streaming (BackgroundJob polling is sufficient)
- Multi-pass query expansion (single query → many sources is enough headroom)

## 12. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM scoring returns weird JSON | Medium | Low | Fallback to "medium" for failed batches |
| Source API rate limits on 200/query | Medium | Medium | Per-source backoff already exists |
| User clicks button twice | Medium | Low | 429 if running job exists |
| Job hangs after server restart | Low | Medium | BackgroundJob pattern already handles this |
| `target_count` of 100 takes >5min | Medium | Medium | Increase timeout to 10min if 100 selected |