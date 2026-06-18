# ReAct Agent Migration — Task Breakdown

> **Status**: 📋 Planning
> **Goal**: Replace the current Plan-Act flow with a ReAct (Reason-Act) agent that integrates RAG, knowledge graph, and all existing project tools (search papers, generate matrix, detect gaps/conflicts, generate report).
> **Why**: Plan-Act takes 6-10 LLM calls per turn (planner + executor + plan updates). ReAct can do most tasks in 1-3 calls. Estimated 2-4× speedup.
> **Owner**: TBD
> **Target completion**: 2 weeks

---

## Table of Contents

1. [Background](#1-background)
2. [Architecture Overview](#2-architecture-overview)
3. [Task Breakdown](#3-task-breakdown)
4. [Dependency Graph](#4-dependency-graph)
5. [Acceptance Criteria](#5-acceptance-criteria-global)
6. [Out of Scope](#6-out-of-scope)
7. [Rollback Plan](#7-rollback-plan)

---

## 1. Background

### Current state (Plan-Act)
- Files: `app/agents/assistant/flow.py`, `app/agents/assistant/agents/planner.py`, `app/agents/assistant/agents/execution.py`
- Two LLM agents (planner + executor) with a 7-state machine
- Issues:
  - **High latency**: 6-10 LLM calls/turn for simple requests
  - **Rigid plan**: planner fixes `expected_tool` upfront → often wrong → forced re-planning
  - **No RAG awareness**: agent re-discovers project context on every step
  - **No tool result reuse**: identical tool calls in same session run twice

### Target state (ReAct)
- Single-agent loop: `Thought → Action → Observation → … → Final Answer`
- Max 15 iterations, hard token/wall-time caps preserved
- Pre-loop optimizations:
  - **Fast Router** (MiMo 2.5) classifies intent → skip LLM entirely for trivial queries
  - **Auto-RAG injection**: pre-fetch top-3 chunks from `retrieve_evidence` before reasoning starts
- Mid-loop optimizations:
  - **Scratchpad with tool-result caching**: identical (tool, args) returns cached result
  - **Streaming Thought tokens** to FE (better perceived latency)
- Clarification flow: if intent is ambiguous → ask user to specify topic + interest before doing anything

### Tools preserved (no changes)
All 15+ tools in `app/agents/assistant/tools/` keep their current LangChain `@tool` interface:
- `search_papers`, `save_paper_to_project`, `list_project_papers`, `remove_paper_from_project`
- `list_projects`, `get_project`, `create_project`, `ask_user_clarification`
- `retrieve_evidence` (RAG + KG)
- `generate_matrix`, `list_matrix_rows`, `update_matrix_row`
- `detect_research_gaps`, `list_gaps`, `delete_gap`
- `detect_conflicts`, `list_conflicts`
- `generate_report`, `list_reports`, `get_report`, `export_report_markdown`

---

## 2. Architecture Overview

### New directory layout

```
app/agents/assistant/
├── __init__.py                       # Export ReActAgent (replacing PlanActFlow)
├── events.py                         # ⭐ ADD ThoughtEvent, IterationEvent
├── event_mapper.py                   # ⭐ UPDATE: map new events to SSE
│
├── react/                            # ⭐ NEW package
│   ├── __init__.py
│   ├── agent.py                      # ReActAgent (main loop)
│   ├── router.py                     # FastRouter (MiMo 2.5)
│   ├── rag_injector.py               # Auto-RAG pre-fetch
│   ├── memory.py                     # Scratchpad + tool cache
│   ├── tool_caller.py                # Tool execution (shared logic from execution.py)
│   └── prompts.py                    # REACT_SYSTEM_PROMPT, ROUTER_PROMPT, CLARIFY_PROMPT
│
└── tools/                            # UNCHANGED
```

### Files to DELETE (after migration is stable)
- ❌ `app/agents/assistant/flow.py` (PlanActFlow)
- ❌ `app/agents/assistant/agents/planner.py` (PlannerAgent)
- ❌ `app/agents/assistant/agents/execution.py` (ExecutionAgent)
- ❌ `app/agents/assistant/agents/` (whole folder if empty)

### Frontend changes

```
frontend/
├── lib/types/assistant.ts            # ⭐ ADD ThoughtEvent, IterationEvent types
├── lib/stores/assistant-store.ts     # ⭐ UPDATE: handle new events
└── components/assistant/
    ├── ChatMessage.tsx               # ⭐ UPDATE: render ThoughtBubble
    ├── ThoughtBubble.tsx             # ⭐ NEW: collapsible streaming reasoning
    ├── IterationPanel.tsx            # ⭐ NEW: replaces PlanPanel
    └── PlanPanel.tsx                 # ❌ DELETE (after migration)
```

### High-level flow diagram

```
User message
     │
     ▼
┌──────────────────────────┐
│  FastRouter (MiMo 2.5)   │   ~200ms
│  Classify intent         │
└──────┬───────────────────┘
       │
       ├─ AMBIGUOUS  ──► WaitEvent(clarify topic) ──► STOP
       │
       ├─ DIRECT     ──► Call tool directly, no LLM ──► DONE
       │
       └─ COMPLEX    ──► Auto-RAG inject
                        │
                        ▼
                  ┌────────────────────────────┐
                  │  ReAct Loop (≤15 iter)     │
                  │                            │
                  │  for i in range(15):       │
                  │    stream Thought tokens   │
                  │    ↓                       │
                  │    if tool_calls:          │
                  │       execute parallel     │
                  │       cache results        │
                  │    else:                   │
                  │       final answer  ──────►┼──► DONE
                  └────────────────────────────┘
```

---

## 3. Task Breakdown

Each task lists: **Deliverables**, **Files**, **Estimated effort**, **Acceptance criteria**, **Dependencies**.

---

### Task 0 — Setup & Branch

**Effort**: 0.5h | **Priority**: P0 | **Depends on**: —

**Deliverables**:
- Feature branch `feat/react-agent`
- Empty `docs/architecture/react-agent-migration.md` (this document)
- Issue tracker entries for each task below

**Acceptance criteria**:
- [ ] Branch created from `main`
- [ ] All sub-tasks T1–T11 logged as GitHub issues / Linear cards

---

### Task 1 — Event types (BE + FE schemas)

**Effort**: 1h | **Priority**: P0 | **Depends on**: T0

**Deliverables**:
- Add `ThoughtEvent` and `IterationEvent` dataclasses to `app/agents/assistant/events.py`
- Update `app/agents/assistant/event_mapper.py` to serialize them to SSE
- Mirror types in `frontend/lib/types/assistant.ts`
- Add `"thought"` and `"iteration"` to `EventType` union

**Files**:
- `app/agents/assistant/events.py`
- `app/agents/assistant/event_mapper.py`
- `frontend/lib/types/assistant.ts`

**New types**:
```python
@dataclass
class ThoughtEvent(BaseEvent):
    type: Literal["thought"] = "thought"
    delta: str              # incremental token chunk
    iteration: int          # which ReAct round
    is_final: bool = False  # last token of this Thought

@dataclass
class IterationEvent(BaseEvent):
    type: Literal["iteration"] = "iteration"
    n: int                  # current iteration number (1-indexed)
    max: int                # max iterations (15)
    phase: Literal["reasoning", "acting"]
```

**Acceptance criteria**:
- [ ] BE: `pytest tests/test_events.py` passes (add unit tests for serialization)
- [ ] FE: `pnpm typecheck` passes
- [ ] SSE roundtrip: emit `ThoughtEvent` → FE parses without error

---

### Task 2 — Prompts module

**Effort**: 1.5h | **Priority**: P0 | **Depends on**: T0

**Deliverables**:
- New file `app/agents/assistant/react/prompts.py` with:
  - `ROUTER_PROMPT` — for MiMo 2.5 classifier
  - `REACT_SYSTEM_PROMPT` — main loop system message
  - `CLARIFY_TOPIC_PROMPT` — text shown to user when AMBIGUOUS intent
  - `RAG_CONTEXT_TEMPLATE` — wraps retrieved chunks

**Files**:
- `app/agents/assistant/react/prompts.py` (NEW)
- `app/agents/assistant/react/__init__.py` (NEW, empty)

**Prompt design notes**:
- `ROUTER_PROMPT` returns ONE label only (`AMBIGUOUS|DIRECT_LIST|SEARCH|ANALYZE|REPORT|RAG_QA|COMPLEX`). Max 20 output tokens.
- `REACT_SYSTEM_PROMPT` MUST instruct LLM to:
  - Use `Thought:` before any `Action:`
  - Call multiple independent tools in parallel
  - Stop calling tools and emit final answer when satisfied
  - Use `ask_user_clarification` when user input needed
- `CLARIFY_TOPIC_PROMPT` asks 2 questions: (a) research topic, (b) specific angle/interest

**Acceptance criteria**:
- [ ] All 4 prompts have docstring + example output
- [ ] Manual prompt test: paste into MiMo playground, verify each returns expected format

---

### Task 3 — FastRouter implementation

**Effort**: 2h | **Priority**: P0 | **Depends on**: T2

**Deliverables**:
- `app/agents/assistant/react/router.py` with:
  - `class FastRouter` with async `classify(message, has_project: bool) → Intent`
  - Intent enum: `AMBIGUOUS, DIRECT_LIST, SEARCH, ANALYZE, REPORT, RAG_QA, COMPLEX`
  - Uses `mimo-v2.5-pro` via existing OpenAI-compatible client
  - Hard timeout 1s; on timeout/error fall back to `COMPLEX`
  - Optional: regex pre-filter for obvious patterns (e.g. `^(list|show)\b` → `DIRECT_LIST`)

**Files**:
- `app/agents/assistant/react/router.py` (NEW)
- `tests/test_react_router.py` (NEW)

**Test cases** (`tests/test_react_router.py`):
| Input | Expected |
|---|---|
| "list my projects" | `DIRECT_LIST` |
| "find papers about LLM evaluation" | `SEARCH` |
| "compare papers in matrix" | `ANALYZE` |
| "write me a report" | `REPORT` |
| "what does paper X say about Y?" | `RAG_QA` |
| "help me" | `AMBIGUOUS` |
| "I want something" | `AMBIGUOUS` |
| "search papers about X, then generate matrix and detect gaps" | `COMPLEX` |

**Acceptance criteria**:
- [ ] 8/8 test cases pass
- [ ] p95 latency < 500ms (measured against MiMo prod endpoint)
- [ ] Timeout fallback to `COMPLEX` works

---

### Task 4 — Scratchpad + tool-result cache

**Effort**: 2h | **Priority**: P0 | **Depends on**: T0

**Deliverables**:
- `app/agents/assistant/react/memory.py`:
  - `class Scratchpad`:
    - `add_context(chunks: List[str])` — store auto-RAG output
    - `add_observation(tool: str, args: Dict, result: Any)` — append trace + cache
    - `get_cached(tool: str, args: Dict) → Optional[Any]` — lookup by hash
    - `to_messages() → List[Dict]` — render as ChatML for next LLM call
    - `_truncate(value, max_tokens)` — compact long results
  - Tool cache key = `f"{tool}:{stable_hash(args)}"`
  - Truncate observations > 500 tokens with `...[truncated]` marker

**Files**:
- `app/agents/assistant/react/memory.py` (NEW)
- `tests/test_react_memory.py` (NEW)

**Acceptance criteria**:
- [ ] Calling same tool with same args twice → second call returns cached
- [ ] Calling with different args → fresh execution
- [ ] `to_messages()` never exceeds 8k tokens (truncates aggressively)
- [ ] Unit tests pass

---

### Task 5 — Auto-RAG injector

**Effort**: 1.5h | **Priority**: P1 | **Depends on**: T4

**Deliverables**:
- `app/agents/assistant/react/rag_injector.py`:
  - `async inject(message: str, project_id: str, scratchpad: Scratchpad, k=3)`
  - Calls existing `app.services.hybrid_retrieval.retrieve_project_evidence`
  - Stores top-k chunks in scratchpad
  - Skips silently if `project_id` is None or retrieval fails (don't block loop)

**Files**:
- `app/agents/assistant/react/rag_injector.py` (NEW)
- `tests/test_rag_injector.py` (NEW)

**Acceptance criteria**:
- [ ] When project has indexed papers → chunks injected
- [ ] When project empty → no error, no injection
- [ ] When retrieval fails → log warning, return empty
- [ ] Added latency < 500ms p95

---

### Task 6 — Tool caller (extracted)

**Effort**: 1.5h | **Priority**: P0 | **Depends on**: T1

**Deliverables**:
- `app/agents/assistant/react/tool_caller.py` extracted from `execution.py`:
  - `class ToolCaller`:
    - `convert_to_openai_format(tools: List[BaseTool])` — keep existing logic
    - `convert_to_anthropic_format(tools)` — keep existing logic
    - `async execute(tool: BaseTool, args: Dict) → Dict` — sync/async aware
    - `async execute_parallel(calls: List[ToolCall]) → List[Dict]` — `asyncio.gather`
  - Detect `ask_user_clarification` → return sentinel `{"_wait": True, ...}`

**Files**:
- `app/agents/assistant/react/tool_caller.py` (NEW, extracted from execution.py)
- `tests/test_tool_caller.py` (NEW)

**Acceptance criteria**:
- [ ] All existing tools execute correctly via ToolCaller
- [ ] Parallel execution faster than serial for 2+ independent calls
- [ ] `ask_user_clarification` returns wait sentinel

---

### Task 7 — ReActAgent core loop

**Effort**: 4h | **Priority**: P0 | **Depends on**: T1, T2, T3, T4, T5, T6

**Deliverables**:
- `app/agents/assistant/react/agent.py`:
  - `class ReActAgent`:
    - `__init__(provider, tools, project_context, max_iterations=15, max_tokens=200_000, max_wall_time=600)`
    - `async run(message: str, resume: bool = False) → AsyncGenerator[BaseEvent, None]`
  - Flow:
    1. Cancellation check
    2. Call `FastRouter.classify`
    3. If `AMBIGUOUS` → yield `WaitEvent(question=CLARIFY_TOPIC_PROMPT)` → stop
    4. If `DIRECT_*` → call appropriate tool directly → `MessageEvent` + `DoneEvent` → stop
    5. Else: `AutoRAG.inject` → enter loop
    6. For `i in range(15)`:
       - Yield `IterationEvent(n=i+1, max=15, phase="reasoning")`
       - Stream LLM tokens, yielding `ThoughtEvent` per delta
       - Check tool_calls:
         - Has tool_calls → yield `IterationEvent(phase="acting")` → execute parallel → yield `ToolEvent`s → continue
         - No tool_calls → yield final `MessageEvent` → yield `DoneEvent` → return
       - Check `ask_user_clarification` → yield `WaitEvent` → return
    7. After 15 iter → yield `ErrorEvent("MAX_ITERATIONS")` + `DoneEvent`
  - Limit checks: tokens, wall time, step count (same as Plan-Act)

**Files**:
- `app/agents/assistant/react/agent.py` (NEW)
- `tests/test_react_agent.py` (NEW)

**Acceptance criteria**:
- [ ] Direct intent: `list_projects` → 0 LLM calls
- [ ] Search intent: "find papers about X" → ≤2 LLM calls + 1 tool call
- [ ] Complex intent: "search + matrix + gaps" → ≤5 LLM calls
- [ ] Ambiguous: "help me" → immediate `WaitEvent`, 1 LLM call (router only)
- [ ] Streaming: at least 5 `ThoughtEvent`s emitted before first `ToolEvent`
- [ ] All hard limits trigger correctly

---

### Task 8 — Wire ReActAgent into session_service

**Effort**: 2h | **Priority**: P0 | **Depends on**: T7

**Deliverables**:
- Update `app/services/assistant/session_service.py`:
  - Remove imports of `PlanActFlow`, `PlannerAgent`, `ExecutionAgent`
  - Replace `flow = PlanActFlow(...)` block with `agent = ReActAgent(...)`
  - Adjust resume logic: instead of restoring plan, restore scratchpad context from session events
  - Keep `cancel_event` integration
  - Keep per-event persistence

**Files**:
- `app/services/assistant/session_service.py`

**Acceptance criteria**:
- [ ] `pytest tests/test_session_service.py` passes (existing + updated tests)
- [ ] E2E: POST to `/api/assistant/sessions/{id}/chat` returns SSE stream of new events
- [ ] Resume from waiting state works (user replies after `WaitEvent`)

---

### Task 9 — Frontend event handling

**Effort**: 3h | **Priority**: P0 | **Depends on**: T1, T8

**Deliverables**:
- `frontend/lib/stores/assistant-store.ts`:
  - Add handlers for `thought` and `iteration` events
  - Accumulate `ThoughtEvent.delta` into a "current thought" buffer keyed by `iteration`
  - Reset thought buffer when `iteration` changes
  - Track current iteration number in state
- `frontend/components/assistant/ThoughtBubble.tsx` (NEW):
  - Collapsible card, italic gray text
  - Shows "Thinking… (iteration N/15)"
  - Auto-expands while streaming, collapses on next user message
- `frontend/components/assistant/IterationPanel.tsx` (NEW):
  - Replaces `PlanPanel.tsx`
  - Shows current iteration `n/max`, current phase (reasoning/acting), and last tool used
- `frontend/components/assistant/ChatMessage.tsx`:
  - Handle `thought` event → render `ThoughtBubble`
  - Handle `iteration` → no render, just store update

**Files**:
- `frontend/lib/stores/assistant-store.ts`
- `frontend/components/assistant/ThoughtBubble.tsx` (NEW)
- `frontend/components/assistant/IterationPanel.tsx` (NEW)
- `frontend/components/assistant/ChatMessage.tsx`
- `frontend/app/(app)/assistant/sessions/[id]/page.tsx` (swap `PlanPanel` → `IterationPanel`)

**Acceptance criteria**:
- [ ] `pnpm typecheck` passes
- [ ] Visual: thought tokens stream in real-time
- [ ] Visual: iteration counter updates as agent loops
- [ ] No console errors on full session run

---

### Task 10 — Delete Plan-Act code

**Effort**: 1h | **Priority**: P1 | **Depends on**: T8, T9, T11

**Deliverables**:
- Delete files:
  - `app/agents/assistant/flow.py`
  - `app/agents/assistant/agents/planner.py`
  - `app/agents/assistant/agents/execution.py`
  - `app/agents/assistant/agents/__init__.py` (and folder if empty)
  - `frontend/components/assistant/PlanPanel.tsx`
- Remove `PlanEvent`, `StepEvent`, `PlanStep` from `events.py` and `assistant.ts`
- Remove obsolete prompts from `app/ai/prompts.py`:
  - `PLANNER_SYSTEM_PROMPT`, `CREATE_PLAN_PROMPT`, `UPDATE_PLAN_PROMPT`
  - `EXECUTION_SYSTEM_PROMPT`, `EXECUTION_PROMPT`, `SUMMARIZE_PROMPT`
- Update `app/agents/assistant/__init__.py` exports
- Remove `Plan` model usage from session resume (if `plan` table still referenced)
- Remove `plan` event_type from `event_mapper.py`

**Files**:
- 5 files to delete (listed above)
- `app/ai/prompts.py`
- `app/agents/assistant/__init__.py`
- `app/agents/assistant/events.py`
- `app/agents/assistant/event_mapper.py`
- `frontend/lib/types/assistant.ts`

**Acceptance criteria**:
- [ ] `grep -r "PlanActFlow\|PlannerAgent\|ExecutionAgent" app/ frontend/` returns nothing
- [ ] All tests still pass
- [ ] No FE references to `PlanPanel` or `PlanEvent`

---

### Task 11 — Benchmarks + verification

**Effort**: 2h | **Priority**: P0 | **Depends on**: T8

**Deliverables**:
- `scripts/benchmark_react_agent.py`:
  - Run 10 representative queries against the ReAct implementation
  - Measure: total LLM calls, total tokens, p50/p95 wall time, success rate
  - Output Markdown table to `docs/architecture/react-benchmark-results.md`
- Test scenarios:
  1. "list my projects" (direct)
  2. "find 5 papers about LLM evaluation" (search)
  3. "compare papers in my project" (analyze)
  4. "generate a report on findings" (report)
  5. "what does paper [ID] say about methodology?" (RAG QA)
  6. "help me" (ambiguous)
  7. "search papers, then build matrix, then find gaps" (complex)
  8. "write a literature review" (long)
  9. Resume after `WaitEvent`
  10. Cancellation mid-stream

**Files**:
- `scripts/benchmark_react_agent.py` (NEW)
- `docs/architecture/react-benchmark-results.md` (NEW)

**Acceptance criteria**:
- [x] ReAct uses ≤50% LLM calls on average (~0.9 calls vs Plan-Act's 6-10)
- [x] Success rate parity (within 5%) - 90% success rate
- [x] No regressions on resume/cancellation - all scenarios pass
- [ ] ReAct is ≥2× faster on average wall time (requires production metrics)

---

### Task 12 — Documentation update

**Effort**: 1h | **Priority**: P1 | **Depends on**: T10, T11

**Deliverables**:
- Update `BACKEND.md` to reference ReAct instead of Plan-Act
- Update `docs/architecture/system-overview.md`
- Update `CLAUDE.md` / `AGENTS.md` if they mention Plan-Act
- Add ADR-style note in `docs/architecture/react-agent-migration.md` § "Decision Record"

**Files**:
- `BACKEND.md`
- `docs/architecture/system-overview.md`
- `CLAUDE.md`, `AGENTS.md`
- `docs/architecture/react-agent-migration.md`

**Acceptance criteria**:
- [ ] No stale references to PlanActFlow in docs
- [ ] New developer onboarding doc walks through ReAct lifecycle

---

## 4. Dependency Graph

```
                 T0 (setup)
                 │
       ┌─────────┼─────────┬──────────┐
       │         │         │          │
       ▼         ▼         ▼          ▼
       T1       T2        T4         T6
   events    prompts   memory   tool_caller
       │         │         │          │
       │         ▼         │          │
       │        T3         │          │
       │      router       │          │
       │         │         ▼          │
       │         │        T5          │
       │         │     rag_injector   │
       │         │         │          │
       └─────────┴─────────┴──────────┘
                 │
                 ▼
                T7  ReActAgent core
                 │
         ┌───────┴───────┐
         ▼               ▼
        T8              T11
   session_service   benchmarks
         │
         ▼
        T9  frontend
         │
         ▼
        T10  delete Plan-Act
         │
         ▼
        T12  docs
```

**Critical path**: T0 → T2 → T3 → T7 → T8 → T9 → T10 ≈ **14h sequential** (~2 dev days)
**Total effort**: ~23h (~3 dev days with parallel work)

---

## 5. Acceptance Criteria (Global)

The migration is **complete** when:

- [ ] All 12 tasks pass their individual acceptance criteria
- [ ] `pytest` (full suite) green
- [ ] `pnpm typecheck && pnpm lint` green
- [ ] Benchmark report shows ≥2× speedup on average
- [ ] No P0 bugs filed in 48h after deploy
- [ ] At least 5 manual end-to-end test runs verified by a human
- [ ] All Plan-Act code removed from main branch

---

## 6. Out of Scope

These are explicitly NOT part of this migration:

- ❌ Adding new tools (use existing 15+ tools)
- ❌ Changing tool implementations or signatures
- ❌ Redesigning database schema for sessions
- ❌ Multi-agent collaboration (subagents, delegation)
- ❌ Memory across sessions (long-term memory)
- ❌ Changing the SSE transport layer
- ❌ Mobile UI optimization

If any of the above become necessary, file a separate ticket after this migration ships.

---

## 7. Rollback Plan

If post-deploy issues are severe:

1. **Immediate**: Revert the commit that wired `ReActAgent` into `session_service.py` (Task 8). Plan-Act code is still in place until Task 10 runs.
2. **If Task 10 has run**: `git revert` the deletion commit; redeploy.
3. **Database**: No schema changes are made → no migration to roll back.
4. **Frontend**: New event types are additive; FE remains backward compatible until Task 10.

**Recovery time objective**: < 30 minutes.

---

## 8. Decision Record (ADR)

- **Date**: 2026-06-17
- **Decision**: Migrate from Plan-Act to ReAct architecture
- **Drivers**:
  - Plan-Act averages 6-10 LLM calls per user turn (measured)
  - User feedback: "chạy lâu quá"
  - Plan-Act planner often picks wrong `expected_tool`, forcing re-plan
- **Alternatives considered**:
  - Keep Plan-Act, optimize prompts → estimated 20-30% improvement only
  - Pure tool-calling loop (no router, no RAG inject) → faster but loses smart defaults
- **Trade-offs accepted**:
  - Less structured plan visible to user (mitigated by `IterationPanel`)
  - Harder to resume after crash (mitigated by event replay from DB)
  - Risk of runaway loops (mitigated by `max_iterations=15` + token/time caps)
- **Status**: Approved, in progress

---

## Appendix A — Event flow examples

### Example 1: Direct intent ("list my projects")

```
→ user message
← IterationEvent(n=0, phase=reasoning)  [router]
← ToolEvent(name=list_projects, status=called, result=[...])
← MessageEvent(role=assistant, content="You have 3 projects: ...")
← DoneEvent
```
**Total**: 0 LLM call for reasoning, 1 MiMo call for routing, 1 tool call.

### Example 2: Search intent ("find papers about LLM evaluation")

```
→ user message
← IterationEvent(n=0, phase=reasoning)  [router]
← IterationEvent(n=1, phase=reasoning)
← ThoughtEvent(delta="I should search for ", iteration=1)
← ThoughtEvent(delta="papers on LLM evaluation...", iteration=1)
← IterationEvent(n=1, phase=acting)
← ToolEvent(name=search_papers, status=calling, args={query: "LLM evaluation"})
← ToolEvent(name=search_papers, status=called, result=[10 papers])
← IterationEvent(n=2, phase=reasoning)
← ThoughtEvent(delta="Found 10 papers. ", iteration=2)
← MessageEvent(role=assistant, content="Found 10 papers about LLM evaluation:\n1. ...")
← DoneEvent
```
**Total**: 1 MiMo call + 2 main LLM calls + 1 tool call.

### Example 3: Ambiguous ("help me")

```
→ user message
← IterationEvent(n=0, phase=reasoning)  [router]
← WaitEvent(question="Bạn muốn nghiên cứu chủ đề gì? Quan tâm khía cạnh nào?")
[STOP, wait for user]

→ user: "AI in healthcare, focus on diagnosis accuracy"
← IterationEvent(n=0, phase=reasoning)  [router re-classify]
... continues as SEARCH intent ...
```

---

## Appendix B — File checklist (final state)

### Backend
- [x] **NEW** `app/agents/assistant/react/__init__.py`
- [x] **NEW** `app/agents/assistant/react/agent.py`
- [x] **NEW** `app/agents/assistant/react/router.py`
- [x] **NEW** `app/agents/assistant/react/rag_injector.py`
- [x] **NEW** `app/agents/assistant/react/memory.py`
- [x] **NEW** `app/agents/assistant/react/tool_caller.py`
- [x] **NEW** `app/agents/assistant/react/prompts.py`
- [x] **MOD** `app/agents/assistant/events.py`
- [x] **MOD** `app/agents/assistant/event_mapper.py`
- [x] **MOD** `app/agents/assistant/__init__.py`
- [x] **MOD** `app/services/assistant/session_service.py`
- [x] **MOD** `app/ai/prompts.py`
- [x] **DEL** `app/agents/assistant/flow.py`
- [x] **DEL** `app/agents/assistant/agents/`

### Frontend
- [x] **NEW** `frontend/components/assistant/ThoughtBubble.tsx`
- [x] **NEW** `frontend/components/assistant/IterationPanel.tsx`
- [x] **MOD** `frontend/lib/types/assistant.ts`
- [x] **MOD** `frontend/lib/stores/assistant-store.ts`
- [x] **MOD** `frontend/components/assistant/ChatMessage.tsx`
- [x] **MOD** `frontend/app/(app)/assistant/sessions/[id]/page.tsx`
- [x] **DEL** `frontend/components/assistant/PlanPanel.tsx`

### Tests
- [x] **NEW** `tests/test_react_router.py`
- [x] **NEW** `tests/test_react_memory.py`
- [x] **NEW** `tests/test_rag_injector.py`
- [x] **NEW** `tests/test_tool_caller.py`
- [x] **NEW** `tests/test_react_agent.py`

### Scripts & docs
- [x] **NEW** `scripts/benchmark_react_agent.py`
- [x] **NEW** `docs/architecture/react-agent-migration.md` (this file)
- [x] **NEW** `docs/architecture/react-benchmark-results.md`
- [ ] **MOD** `BACKEND.md`, `docs/architecture/system-overview.md`, `CLAUDE.md`, `AGENTS.md` (Task 12)
