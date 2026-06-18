# Task 10: Matrix / Gap / Conflict / Report — Performance & Quality Optimization

## Status: Planned

## Research Foundation

Researched 12+ recent papers (2024–2026) on LLM-driven systematic literature review, multi-document RAG, and contradiction detection:

| Paper | Year | Key Contribution | Applicable To |
|-------|------|-----------------|---------------|
| Databricks "Reliable LLM Pipelines" | 2026 | Map → Reduce → Align pattern | Matrix, Report |
| ACL "On Context Utilization" | 2024 | Middle curse; hierarchical summarization beats flat | Gap, Report |
| PMC "Collaborative LLMs for Extraction" | 2024 | Dual-LLM cross-critique; 0.94 accuracy vs 0.89 single | Matrix, Gap |
| Madam-RAG | 2025 | Multi-agent debate for conflicting evidence | Conflict |
| LitGapFinder | 2026 | Concept co-occurrence gap detection; 60% hit rate | Gap |
| Long Context vs RAG Benchmark | 2025 | RAG beats full-context; papers naturally segmented | All |
| Async LLM Patterns | 2026 | asyncio.gather + Semaphore; 3–50× speedup | Matrix, Conflict |
| PROMPTHEUS SLR Pipeline | 2025 | 3-phase: screening → extraction → synthesis | All |
| OpenExtract | 2025 | RAG per entry; 1000-token chunks + 500 overlap | Matrix |
| CoTHSSum | 2025 | Hierarchical + CoT for long documents | Report |

**Core insight confirmed:** Full-text N-paper injection into a single LLM call is always wrong. 
The correct pattern is: **atomic per-document extraction → matrix → cross-document RAG reasoning → synthesis**.

---

## Problem Statement

### Current Architecture

```
Papers → [PDF Normalization] → chunks → [Matrix Extraction]
                                              ↓ per-paper (sequential)
                                       LiteratureMatrixRow × N
                                              ↓
                               [Gap Analysis / Conflict Detection]
                                              ↓ 1 call tổng (bottleneck khi N>30)
                               [Report Generation]
                                              ↓ 1 call tổng (bottleneck khi N>30)
                                       Literature Review
```

### Issues Identified

| Step | Issue | Severity |
|------|-------|----------|
| Matrix Extraction | Sequential per-paper loop (20 paper × 2s = 40–60s) | 🔴 High |
| Gap Analysis | 1 LLM call với ALL matrix rows → middle curse khi N>30 | 🟡 Medium |
| Conflict Detection | Sequential 10 groups, no parallel, no cross-dedup | 🟡 Medium |
| Report Generation | 1 LLM call tổng → thin sections, low coverage | 🟡 Medium |
| BackgroundJob | No granular progress → user sees spinner only | 🟡 Medium |
| Caching | Re-generate = recompute everything | 🟢 Low |

---

## Phase 1: Matrix Extraction — Parallelize + Backpressure (P0)

**File:** `app/agents/nodes.py` → `matrix_extraction_node`

### Problem
```python
# CURRENT — sequential
for pp in papers_to_process:           # ← bottleneck: 20×2s = 40s
    paper_chunks = await retrieve_paper_evidence(...)
    result = await provider.complete_structured(...)
```

### Solution: Parallel + Semaphore
```python
import asyncio

_MATRIX_CONCURRENCY = 8   # bound by LLM rate limit

async def matrix_extraction_node(state, db):
    papers = await _load_pending_papers(db, state.project_id)
    if not papers:
        return {"matrix_rows": [], "matrix_status": "completed"}

    sem = asyncio.Semaphore(_MATRIX_CONCURRENCY)
    provider = get_provider()

    async def _extract_one(pp) -> dict | None:
        async with sem:
            paper = pp.paper
            chunks = await retrieve_paper_evidence(
                db, pp.id, state.user_topic,
                limit=_MAX_CHUNKS_PER_PAPER,
                content_types=["method","results","limitation","table","narrative"],
            )
            ctx = _build_chunk_context(chunks)
            try:
                result = await provider.complete_structured(
                    messages=[{"role":"user","content": MATRIX_EXTRACTION_CHUNK_USER.format(...)}],
                    system=MATRIX_EXTRACTION_CHUNK_SYSTEM,
                    schema=MatrixRowOutput.model_json_schema(),
                    tool_name="matrix_row",
                    max_tokens=2000,
                )
                return {"project_paper_id": pp.id, "confidence": result.get("confidence","medium"), ...}
            except Exception as exc:
                logger.warning("Matrix extraction failed for '%s': %s", paper.title[:60], exc)
                return None

    # Fan out — wall-clock: 40s → ~8s (concurrency=8)
    results = await asyncio.gather(*[_extract_one(pp) for pp in papers], return_exceptions=True)
    rows = [r for r in results if isinstance(r, dict)]
    
    # Persist
    await upsert_rows(db, state.project_id, rows)
    return {"matrix_rows": _rows_to_json_safe(rows), "matrix_status": "completed", "current_node": "matrix_extraction"}
```

**Impact:** 3–5× speedup. Reference: `app/services/pdf_normalizer.py:218–322` đã có pattern này.

---

## Phase 2: Conflict Detection — Parallel Groups + Cross-Dedup (P0)

**File:** `app/services/conflict_detection.py` → `detect_and_persist_conflicts`

### Problem
```python
# CURRENT — sequential
for shared_context, group in candidate_groups[:10]:  # ← bottleneck: 10×2s = 20s
    chunk_context = await _build_group_chunk_context(...)  # sequential per paper
    result = await provider.complete_structured(...)
```

### Solution A: Parallel Groups
```python
sem = asyncio.Semaphore(5)

async def _detect_one_group(shared_context, group):
    async with sem:
        chunk_context = await _build_group_chunk_context(db, project_id, group, shared_context)
        result = await provider.complete_structured(...)
        return _validate_conflicts(result.get("conflicts", []), shared_context)

# Parallel: 10 groups → ~3s instead of 20s
tasks = [_detect_one_group(ctx, grp) for ctx, grp in candidate_groups[:10]]
results = await asyncio.gather(*tasks, return_exceptions=True)
conflicts = [c for r in results if isinstance(r, list) for c in r]
```

### Solution B: Cross-Group Deduplication
```python
# 2 groups có thể detect cùng 1 conflict (same paper_a + paper_b)
def _dedup_conflicts(conflicts):
    seen = {}
    for c in conflicts:
        key = (str(c["paper_a_id"]), str(c["paper_b_id"]))
        if key not in seen or c.get("confidence") == "high":
            seen[key] = c
    return list(seen.values())
```

### Solution C: Multi-Agent Cross-Critique (Madam-RAG style)
Optionally: run 2 LLM calls per group (different providers), aggregator picks higher-confidence.
Cost 2× but hallucination rate drops significantly (PMC 2024: 2.5% → 0.25%).

**Impact:** 2–3× speedup + deduplication quality gain.

---

## Phase 3: Gap Analysis — Hierarchical Map-Reduce (P1)

**File:** `app/agents/nodes.py` → `gap_analysis_node`

### Problem
```python
# CURRENT — 1 call với ALL rows
# Middle curse: với 50-100 rows, model yếu ở giữa context
result = await provider.complete_structured(
    messages=[{"role":"user","content": GAP_ANALYSIS_CHUNK_USER.format(
        paper_ids_json=ALL_ids,
        matrix_rows_json=ALL_rows,  # ← bottleneck
        chunk_context=...,
    )}],
    ...
)
```

### Solution: 2-Tier Map-Reduce

**Tier 1 — Map:** Chia matrix rows thành chunk (12 rows/chunk), parallel extract candidate gaps.
**Tier 2 — Reduce:** Merge + dedup + rank candidate gaps từ các chunk.

```python
_CHUNK_ROWS_FOR_GAP = 12
_MAX_GAPS_PER_CHUNK = 3

async def _gap_map_chunk(rows_chunk, project_topic, relevant_chunks, provider):
    safe_rows = _rows_to_json_safe([{
        "project_paper_id": r.project_paper_id,
        "research_problem": r.research_problem, "method": r.method,
        "dataset_or_context": r.dataset_or_context,
        "key_result": r.key_result, "limitation": r.limitation,
    } for r in rows_chunk])
    
    chunk_context = _build_chunk_context(relevant_chunks)
    user_msg = GAP_ANALYSIS_CHUNK_USER.format(
        project_topic=project_topic,
        paper_ids_json=json.dumps([str(r.project_paper_id) for r in rows_chunk]),
        matrix_rows_json=json.dumps(safe_rows, indent=2),
        chunk_context=chunk_context,
    )
    result = await provider.complete_structured(
        messages=[{"role":"user","content": user_msg}],
        system=GAP_ANALYSIS_CHUNK_SYSTEM,
        schema=GapListOutput.model_json_schema(),
        tool_name="gap_chunk_analysis",
        max_tokens=3000,
    )
    return result.get("gaps", [])

async def _gap_reduce(candidates, project_topic, provider):
    if not candidates:
        return []
    dedup_prompt = f"""Deduplicate and rank these candidate gaps.
    Prefer gaps backed by more evidence papers.
    Return max 8 final gaps.
    Candidates:
    {json.dumps(candidates, indent=2)}"""
    result = await provider.complete_structured(
        messages=[{"role":"user","content": dedup_prompt}],
        system="""You are a research gap analyst. Merge and deduplicate candidate gaps.
        Keep only unique, evidence-backed gaps. Rank by evidence strength.""",
        schema=GapListOutput.model_json_schema(),
        tool_name="gap_dedup",
        max_tokens=3000,
    )
    return result.get("gaps", [])

async def gap_analysis_node(state, db):
    matrix_rows = await _load_matrix_rows(db, state.project_id)
    if len(matrix_rows) < _MIN_MATRIX_ROWS_FOR_GAPS:
        return {"gap_status": "failed", "errors": ["..."]}
    
    # RAG retrieval (multi-query, giữ nguyên)
    chunks_by_paper = await _multi_query_gap_retrieval(db, state.project_id, state.user_topic)
    
    # Chia rows → chunks
    row_chunks = [matrix_rows[i:i+_CHUNK_ROWS_FOR_GAP] 
                  for i in range(0, len(matrix_rows), _CHUNK_ROWS_FOR_GAP)]
    
    # Parallel Map
    provider = get_provider()
    map_tasks = []
    for rows_chunk in row_chunks:
        # Lấy chunks relevant với rows_chunk (theo project_paper_id)
        relevant = []
        for r in rows_chunk:
            relevant.extend(chunks_by_paper.get(r.project_paper_id, []))
        map_tasks.append(_gap_map_chunk(rows_chunk, state.user_topic, relevant, provider))
    
    map_results = await asyncio.gather(*map_tasks, return_exceptions=True)
    all_candidates = [g for r in map_results if isinstance(r, list) for g in r]
    
    # Reduce
    final_gaps = await _gap_reduce(all_candidates, state.user_topic, provider)
    
    # Validate + persist
    validated_gaps = _validate_gaps(final_gaps, matrix_rows)
    await upsert_gaps(db, state.project_id, validated_gaps)
    
    return {"gaps": _rows_to_json_safe(validated_gaps), "gap_status": "completed", "current_node": "gap_analysis"}
```

**Impact:** 
- No middle curse (mỗi chunk 12 rows, bounded context)
- Scalable: 100 rows → 8 chunks × 3 = 24 candidates → reduce → 5-8 final gaps
- Recall cao hơn vì mỗi chunk tập trung reasoning

---

## Phase 4: Report Generation — Multi-Section + Multi-Pass (P1)

**File:** `app/services/report_generation.py`

### Problems
1. 1 LLM call tổng → thin sections, lặp structure
2. `_MAX_RAG_CHUNKS = 50` → coverage limited
3. Retrieval query chỉ 80 terms max → miss nuanced angles

### Solution: Multi-Query + Structured Section Planning

**Step 1 — Thematic Query Expansion:**
```python
# Mở rộng retrieval thành nhiều query chuyên biệt, mỗi query cho 1 khía cạnh
_REPORT_ANGLE_QUERIES = [
    "{topic} methodology comparison framework evaluation metrics",
    "{topic} dataset benchmark performance results ablation",
    "{topic} limitations weakness failure case generalization",
    "{topic} application domain real-world deployment practical",
    "{topic} temporal progression evolution future direction",
    "{topic} theoretical foundation assumption prior work",
    "{topic} conflicting findings disagreement debate",
    "{topic} gap underexplored missing comparison",
]

async def _retrieve_multi_angle(db, project_id, topic, matrix_rows, max_chunks_per_angle=15):
    all_chunks = []
    seen_ids = set()
    
    for template in _REPORT_ANGLE_QUERIES:
        query = template.format(topic=topic)
        chunks = await retrieve_project_evidence(db, project_id, query, limit=max_chunks_per_angle)
        for c in chunks:
            if c.chunk_id not in seen_ids:
                seen_ids.add(c.chunk_id)
                all_chunks.append(c)
    
    # Sort by score
    all_chunks.sort(key=lambda x: x.score, reverse=True)
    return all_chunks
```

**Step 2 — Section Planning LLM Call:**
```python
# Thêm LLM call đầu tiên: lên kế hoạch sections
async def _plan_sections(topic, research_question, safe_rows, safe_gaps, safe_conflicts, provider):
    plan_prompt = f"""Given the following literature:
    
Topic: {topic}
Research Question: {research_question}
Matrix Rows: {json.dumps(safe_rows[:10], indent=2)}  # First 10 as preview
Gaps: {json.dumps(safe_gaps, indent=2)}
Conflicts: {json.dumps(safe_conflicts, indent=2)}

Plan a literature review with 5-8 sections. Each section should cover a distinct angle:
- At least one section on methodology comparison
- At least one section on findings and results synthesis  
- At least one section on limitations and challenges
- If gaps exist, at least one section addressing research gaps
- If conflicts exist, at least one section on conflicting findings
- Include a section on applications and future directions

Return:
{{
  "sections": [
    {{
      "heading": "section name",
      "theme": "1-2 sentence description of what this section synthesizes",
      "focus_paper_ids": ["list of paper IDs most relevant to this section"],
      "key_angles": ["methodology", "results", "comparison"]
    }}
  ]
}}"""
    
    result = await provider.complete_structured(
        messages=[{"role":"user","content": plan_prompt}],
        system="You are a literature review planner.",
        schema={"type":"object","properties":{"sections":{"type":"array"}}},
        tool_name="review_plan",
        max_tokens=2000,
    )
    return result.get("sections", [])
```

**Step 3 — Per-Section Generation + Aggregate:**
```python
_MAX_SECTION_CHUNK_BUDGET = 8000  # chars per section
_MAX_SECTION_TOKENS = 1500

async def _generate_section(section_plan, chunks_by_paper, paper_ids_json, topic, provider):
    # Lấy chunks từ focus papers
    focus_chunks = []
    for pid_str in section_plan.get("focus_paper_ids", []):
        try:
            pid = UUID(pid_str)
            focus_chunks.extend(chunks_by_paper.get(pid, []))
        except:
            pass
    
    # Limit chunk budget
    chunk_parts = []
    total = 0
    for c in focus_chunks[:8]:
        label = c.section_label or c.content_type or "section"
        block = f"---{label}---\n{c.chunk_text}"
        if total + len(block) > _MAX_SECTION_CHUNK_BUDGET:
            break
        chunk_parts.append(block)
        total += len(block)
    
    chunk_context = "\n\n".join(chunk_parts) if chunk_parts else "No full-text available."
    
    section_prompt = f"""Write the following literature review section:

Topic: {topic}
Section: {section_plan['heading']}
Theme: {section_plan['theme']}

Available paper IDs: {paper_ids_json}

Full-text evidence:
{chunk_context}

Write this section in academic prose. Each paragraph MUST cite papers using their project_paper_id.
After your first paragraph, add a blockquote starting with "**Key synthesis:**" with citations.
"""
    
    result = await provider.complete_structured(
        messages=[{"role":"user","content": section_prompt}],
        system=REVIEW_WRITER_CHUNK_SYSTEM,
        schema=ReviewSectionOutput.model_json_schema(),
        tool_name="review_section",
        max_tokens=_MAX_SECTION_TOKENS,
    )
    return result

async def _aggregate_sections(sections, conflicts, gaps, provider):
    """Final pass: weave in conflicts + gaps, ensure smooth transitions."""
    if not sections:
        return []
    
    # Inject conflict and gap sections if not already covered
    aggregate_prompt = f"""You have generated {len(sections)} sections for a literature review.
    Please review and improve them:
    1. Ensure each section has meaningful citations (no empty citation_paper_ids)
    2. Add smooth transitions between sections
    3. If conflicts exist but not addressed, add a paragraph on conflicting findings
    4. If gaps exist but not addressed, add a paragraph on research gaps
    5. Ensure consistent citation style throughout
    
    Existing sections:
    {json.dumps(sections, indent=2)}
    
    Conflicts to address:
    {json.dumps(conflicts, indent=2)}
    
    Gaps to address:
    {json.dumps(gaps, indent=2)}
    """
    
    result = await provider.complete_structured(
        messages=[{"role":"user","content": aggregate_prompt}],
        system=REVIEW_WRITER_CHUNK_SYSTEM,
        schema=ReviewOutput.model_json_schema(),
        tool_name="review_aggregate",
        max_tokens=6000,
    )
    return result.get("sections", [])
```

**Step 4 — Revised generate_report:**
```python
async def generate_report(db, project_id, user_id, topic, research_question, ...):
    # 1-4. Load data (giữ nguyên)
    matrix_rows, project_papers, gaps, conflicts = await _load_all_data(db, project_id)
    
    # 5. Multi-angle RAG retrieval
    all_chunks = await _retrieve_multi_angle(db, project_id, topic, matrix_rows)
    chunks_by_paper = _group_chunks_by_paper(all_chunks)
    
    # 6. Section planning
    safe_rows = _rows_to_json_safe(matrix_rows)
    safe_gaps = _rows_to_json_safe(gaps)
    safe_conflicts = _rows_to_json_safe(conflicts)
    paper_ids_json = json.dumps([str(pp.id) for pp in project_papers])
    
    sections_plan = await _plan_sections(topic, research_question, safe_rows, safe_gaps, safe_conflicts, provider)
    
    # 7. Per-section generation (parallel)
    section_tasks = [
        _generate_section(plan, chunks_by_paper, paper_ids_json, topic, provider)
        for plan in sections_plan
    ]
    generated_sections = await asyncio.gather(*section_tasks, return_exceptions=True)
    valid_sections = [s for s in generated_sections if isinstance(s, dict)]
    
    # 8. Aggregate + weave conflicts/gaps
    final_sections = await _aggregate_sections(valid_sections, safe_conflicts, safe_gaps, provider)
    
    # 9. Validate + persist (giữ nguyên)
    ...
```

**Impact:**
- 5-8 distinct sections vs hiện tại có thể 3-4 generic sections
- Multi-angle RAG: 80 terms → 8×15=120 chunks coverage
- Per-section generation: mỗi section độc lập, không bị context overwhelm

---

## Phase 5: BackgroundJob Progress Streaming (P1)

**File:** `app/db/models.py` → `BackgroundJob`

### Problem
User sees spinner only. No idea how many papers processed.

### Solution
```python
# Add to BackgroundJob model
class BackgroundJob(Base):
    ...
    progress_json = Column(JSON, nullable=True)  # {processed: 5, total: 20, current: "Paper Title"}

# In matrix_extraction_node, update every N papers:
async def _update_progress(bg_db, job_id, processed, total, current_paper=""):
    await bg_db.execute(
        update(BackgroundJob).where(BackgroundJob.id == job_id).values(
            progress_json={"processed": processed, "total": total, "current": current_paper[:50]}
        )
    )
    await bg_db.commit()

# Update call after each batch:
_BATCH_PROGRESS_UPDATE = 5
processed = 0
for result in results:
    if isinstance(result, dict):
        processed += 1
        if processed % _BATCH_PROGRESS_UPDATE == 0:
            await _update_progress(bg_db, job.id, processed, len(papers_to_process), paper.title)
```

### Frontend: Poll + Display Progress Bar
```tsx
// frontend/lib/hooks/useJobPolling.ts
const result = await pollJob(jobId);
const progress = result.progress_json as {processed: number, total: number, current: string} | null;
// → Show progress bar: (processed/total) × 100%
```

---

## Phase 6: Content Hash Caching (P2)

**File:** `app/services/literature_matrix.py` + migration

### Problem
Re-generate = recompute everything even if paper content unchanged.

### Solution
```python
# Migration
ALTER TABLE literature_matrix_rows ADD COLUMN content_hash VARCHAR(16);

# In matrix_extraction_node
content_hash = hashlib.sha256(
    f"{pp.id}:{paper.updated_at.isoformat()}".encode()
).hexdigest()[:16]

# Check before extract
existing = await db.execute(
    select(LiteratureMatrixRow).where(
        LiteratureMatrixRow.project_paper_id == pp.id,
        LiteratureMatrixRow.content_hash == content_hash,
    )
)
if existing.scalar_one_or_none():
    logger.info("Skipping '%s' — content unchanged", paper.title[:60])
    continue  # skip, already cached
```

---

## Phase 7: Collaborative Multi-Model Extraction (P2)

**File:** `app/services/literature_matrix.py` → `matrix_extraction_node`

### Problem
Single LLM: hallucination ~2.5%, accuracy 0.89.

### Solution: Dual-Provider Cross-Critique (PMC 2024)
```python
# Extract with 2 providers in parallel
async def _extract_collaborative(pp, topic, provider_a, provider_b):
    # Provider A: primary extraction
    result_a = await provider_a.complete_structured(...)
    
    # Provider B: verify
    verify_prompt = f"""Verify this extraction. If any field is wrong or hallucinated,
    correct it. If correct, return it unchanged.
    Extraction: {json.dumps(result_a)}
    Evidence: {chunk_context}"""
    
    result_b = await provider_b.complete_structured(
        messages=[{"role":"user","content": verify_prompt}],
        system=VERIFICATION_SYSTEM,
        schema=MatrixRowOutput.model_json_schema(),
        tool_name="matrix_verify",
        max_tokens=2000,
    )
    
    # If discordance → aggregator picks or flags for human review
    if result_a != result_b:
        return _resolve_discordance(result_a, result_b)
    return result_a
```

**Impact:** Accuracy 0.89 → 0.94, hallucination 2.5% → 0.25%. Cost 2×.

---

## Roadmap

| Priority | Task | Effort | Impact | Status |
|----------|------|--------|--------|--------|
| 🔴 P0 | Matrix: parallel + Semaphore | 2h | 3–5× speed | TODO |
| 🔴 P0 | Conflict: parallel groups + dedup | 1h | 2–3× speed | TODO |
| 🟡 P1 | Gap: Map-Reduce hierarchical | 4-6h | Quality ↑ N>30 | TODO |
| 🟡 P1 | Report: multi-angle RAG + section planning | 4-6h | Richer content | TODO |
| 🟡 P1 | BackgroundJob: progress_json streaming | 2h | UX ↑↑↑ | TODO |
| 🟢 P2 | Content hash caching | 2h | Cost ↓ | TODO |
| 🟢 P2 | Conflict: cross-group dedup | 1h | Quality ↑ | TODO |
| 🔵 P3 | Collaborative dual-model extraction | 1-2 days | Hallucination ↓10× | TODO |

---

## Key Constants (Tuning Guide)

| Constant | Current | Suggested | Rationale |
|----------|---------|-----------|-----------|
| `_MATRIX_CONCURRENCY` | N/A | 8 | Bound by LLM rate limit (10 concurrent typical) |
| `_MAX_PAPERS` | 20 | 20–50 | RAG chunk budget, increase with better embeddings |
| `_MAX_CHUNKS_PER_PAPER` | 5 | 5 | Context budget; 5×avg_chunk=~4K chars |
| `_CHUNK_ROWS_FOR_GAP` | N/A | 12 | Bounded context for Map phase |
| `_MAX_GAPS_PER_CHUNK` | N/A | 3 | Quality guard; 12 rows × 3 = 36 candidates → reduce |
| `_MAX_RAG_CHUNKS` | 50 | 50–100 | Memory; increase with 128K context models |
| `_REPORT_ANGLE_QUERIES` | N/A | 8 | One per distinct theme |
| `_MAX_SECTION_CHUNK_BUDGET` | N/A | 8000 | Per-section context; avoids overload |

---

## Testing Plan

| Test | File | What to Verify |
|------|------|----------------|
| Matrix parallel | `tests/test_matrix_extraction.py` | Same rows as sequential; progress updates |
| Gap Map-Reduce | `tests/test_gap_analysis.py` | Same gaps as flat; coverage ≥ flat |
| Conflict parallel | `tests/test_conflict_detection.py` | Same conflicts as sequential; dedup works |
| Report multi-section | `tests/test_review_writer.py` | ≥5 sections; each section ≥2 paragraphs |
| Progress streaming | `tests/test_background_jobs.py` | progress_json updates every batch |
| Content hash cache | `tests/test_matrix_extraction.py` | Skip on unchanged content |
