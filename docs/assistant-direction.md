# Lumen Assistant — Project Direction

> Chat-first entry point that lets a researcher drive the entire Lumen workflow
> (search → save → matrix → gaps → review) by talking to an AI agent, instead of
> clicking through 7 separate pages. Internally reuses every existing service,
> LangGraph workflow, Hybrid RAG, and citation guardrail — no rewrite of AI logic.

## 1. Goals

### 1.1. Product Goals

1. **Single chat surface for the full workflow.** User stays in one tab and
   types natural-language commands instead of clicking sidebar items.
2. **Plan-Act transparency.** User sees a live plan, each step's status, and
   each tool call as it happens — never a "black box" chat.
3. **Zero data duplication.** Every artifact the assistant produces is stored
   on the same `Project` entity, so the existing Matrix / Gaps / Map / Reports
   pages continue to work as deep-link destinations.
4. **Same citation guardrail.** Reports generated through chat are validated
   exactly the same way as reports generated from the UI.

### 1.2. Engineering Goals

1. **Reuse > rewrite.** Wrap existing services as tools; do not duplicate AI
   logic in a second workflow engine.
2. **Resume-friendly.** Every event is persisted; user can close the tab and
   reopen the session later with full history replay.
3. **Bounded execution.** A session has a hard cap on steps, tokens, and wall
   time, enforced by the flow itself.
4. **Stream-first.** All assistant output is delivered as Server-Sent Events;
   the UI never blocks waiting for a long tool call.

### 1.3. Non-Goals (this phase)

- Multi-user real-time collaboration on a single session.
- Voice input / TTS output.
- Replacing the existing per-feature pages — those remain the deep-edit
  surfaces. Assistant is the **entry point**, not a replacement.
- Running a Docker sandbox / browser / shell (no `ai-manus`-style sandbox).
- Auto-deploying model changes or self-tuning prompts.

---

## 2. Architecture Overview

```
┌────────────────────────── Frontend (Next.js) ─────────────────────────┐
│  /assistant                                                           │
│  ┌───────────────┐  ┌──────────────────────────┐  ┌────────────────┐  │
│  │ SessionList   │  │ ChatMessage stream       │  │ ToolPanel      │  │
│  │ (Zustand)     │  │ + PlanPanel (sticky)     │  │ (slide-in)     │  │
│  │               │  │ + ChatBox (input / stop) │  │ - papers       │  │
│  │               │  │                          │  │ - matrix       │  │
│  │               │  │                          │  │ - gaps         │  │
│  │               │  │                          │  │ - report       │  │
│  │               │  │                          │  │ - evidence     │  │
│  └───────────────┘  └──────────────────────────┘  └────────────────┘  │
│       SSE stream (fetch-event-source)                                 │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ POST /api/assistant/sessions/{id}/chat
                                  ▼
┌────────────────────────── Backend (FastAPI) ──────────────────────────┐
│  routers/assistant.py                                                 │
│    └── AssistantSessionService                                         │
│         └── PlanActFlow (state machine)                               │
│              ├── PlannerAgent  (LLM → plan JSON)                      │
│              └── ExecutionAgent (LLM + tool calls)                    │
│                   └── AssistantToolkit (LangChain tools)              │
│                        ├── project_tools     (list/get/create)        │
│                        ├── paper_tools       (search/save/download)   │
│                        ├── matrix_tools      (generate/show/edit)     │
│                        ├── gap_tools         (detect/show)            │
│                        ├── conflict_tools    (detect/show)            │
│                        ├── report_tools      (generate/show/export)   │
│                        ├── evidence_tools    (retrieve)               │
│                        └── ask_user_tool     (clarification)          │
│                                                                       │
│  All tool bodies call existing services:                              │
│    app/services/{project,paper_search,matrix,gap_detection,…}.py     │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  ▼
            PostgreSQL — assistant_sessions, assistant_events,
                         assistant_plans (+ existing 17 tables)
```

### Key Design Decisions

| Decision | Reason |
|---|---|
| Plan-Act state machine (not single LLM call) | Chat commands can span 4-6 backend services; single prompt would lose state and hallucinate. |
| Wrap services as tools, do not reimplement | Lumen already has battle-tested AI flows. Reuse preserves citation guardrail and reduces regression risk. |
| Persist every event to PostgreSQL | Lets users resume a session after a refresh; gives us an audit trail. |
| SSE, not WebSocket | One-way push matches the use case (server → client). Smaller surface area than WS. |
| Project context required on session start | Keeps the citation guardrail intact; user can't accidentally mix papers across projects. |
| Ask-user tool (WaitEvent) | When project/topic is ambiguous, pause and ask — better than guessing. |

---

## 3. Tasks & Output Requirements

> Each task lists: **what to ship**, **output artifacts**, **acceptance
> criteria**, and **files touched**. Tasks are numbered for dependency
> tracking; later tasks can only start when their prerequisites are merged.

### Task 1 — Database & Models

**What:** Add three tables for assistant sessions, events, and plans to the
existing PostgreSQL schema, with migrations wired into the FastAPI lifespan.

**Output artifacts:**

- `app/db/models.py` — `AssistantSession`, `AssistantEvent`, `AssistantPlan`
  SQLAlchemy models with proper FKs, indexes, cascade rules.
- `app/main.py` — lifespan migration block (idempotent `CREATE TABLE IF NOT
  EXISTS` + index creation), mirroring the existing `background_jobs` pattern.
- `tests/test_assistant_models.py` — basic insert/read test for each table.

**Acceptance criteria:**

- `docker compose up -d db && make dev` starts cleanly with the new tables
  created.
- No changes to existing 17 tables' columns.
- Each table has `created_at` (and `updated_at` where relevant) with default
  `now()`.
- `assistant_events` has an index on `(session_id, created_at)` for fast
  history replay.
- `assistant_plans.session_id` is `UNIQUE` (one current plan per session).

---

### Task 2 — Event Schemas

**What:** Define the full event model used by the SSE stream. Mirrors
`ai-manus` types but adapted to Lumen's needs (no sandbox, no shell, no VNC).

**Output artifacts:**

- `app/agents/assistant/events.py` — Pydantic v2 base + concrete events:
  `MessageEvent`, `TitleEvent`, `PlanEvent`, `StepEvent`, `ToolEvent`,
  `DoneEvent`, `ErrorEvent`, `WaitEvent`. Each carries `id`, `timestamp`,
  `type` discriminator.
- `app/agents/assistant/event_mapper.py` — `AgentEvent → SSE` mapping
  (Union-based, similar to ai-manus's `EventMapper`).
- `tests/test_assistant_events.py` — serialization round-trip + type
  discrimination tests.

**Acceptance criteria:**

- Every event has a `Literal` discriminator usable with Pydantic v2 `Union`
  parsing.
- Timestamps are ISO-8601 strings on the wire, `datetime` in memory.
- `EventMapper.event_to_sse_event()` returns a uniform shape
  `{event: str, data: dict}` ready for `sse_starlette`.

---

### Task 3 — Tool Layer (skeleton)

**What:** Build the toolkit abstraction and a registry that exposes
LangChain-compatible tools. No real tool bodies yet — just the contract.

**Output artifacts:**

- `app/agents/assistant/tools/__init__.py` — `BaseToolkit` abstract class with
  `get_tools() -> list[Tool]`, plus a global `get_all_toolkits(user_id,
  project_id) -> list[BaseToolkit]` factory.
- `app/agents/assistant/tools/context.py` — `set_user_context`, `get_user_id`,
  `get_project_id` using a `contextvars.ContextVar` so tools can access the
  authenticated user without explicit threading.
- `app/agents/assistant/tools/schemas.py` — Pydantic input/output schemas for
  every tool (one module = one toolkit in later tasks).
- `tests/test_assistant_tools_context.py` — context propagation test.

**Acceptance criteria:**

- `BaseToolkit` raises `NotImplementedError` on `get_tools()`; subclasses
  must implement it.
- Context is set per-request (not per-process) so concurrent users are safe.
- All tool schemas are exported and importable.

---

### Task 4 — Project & Paper Tools

**What:** Wrap the existing project + paper services as tools.

**Output artifacts:**

- `app/agents/assistant/tools/project_tools.py`:
  - `list_projects()` → returns `[{id, name, topic}]` for the current user.
  - `get_project(project_id)` → returns full project metadata.
  - `create_project(name, topic, research_question?)` → returns new
    `project_id` and a deep link `/projects/{id}`.
  - `ask_user_clarification(question, options?)` → emits `WaitEvent`, pauses
    executor until user replies.
- `app/agents/assistant/tools/paper_tools.py`:
  - `search_papers(query, sources=["semantic_scholar","paperhub"],
    year_from?, limit=20)` → calls `services/paper_search.search()` in
    parallel; returns list of normalized papers with source diagnostics.
  - `save_paper_to_project(project_id, paper)` → calls
    `services.project.save_paper_to_project()`; returns
    `{project_paper_id, status, duplicate: bool}`.
  - `remove_paper_from_project(project_id, project_paper_id)`.
  - `list_project_papers(project_id, status="saved")` → returns
    `[{project_paper_id, title, authors, year, doi, …}]`.
- `tests/test_assistant_project_tools.py`,
  `tests/test_assistant_paper_tools.py` — round-trip tests using a test DB.

**Acceptance criteria:**

- Tools never raise raw exceptions back to the LLM; they return
  `{"ok": False, "error_code": "...", "message": "..."}` so the LLM can
  reason about failures.
- Each tool's docstring explicitly tells the LLM **when** to call it
  ("Use this when the user asks for paper X but does not name a project").
- `search_papers` runs all sources in parallel with `asyncio.gather` and a
  per-source timeout (45s) — same pattern as `search_agent_node`.
- No tool accepts another user's `project_id`; ownership check is enforced
  inside the service call.

---

### Task 5 — Matrix / Gap / Conflict / Report / Evidence Tools

**What:** Wrap the remaining domain services as tools.

**Output artifacts:**

- `app/agents/assistant/tools/matrix_tools.py`:
  - `generate_matrix(project_id)` → enqueues background job, polls until
    `completed` or `failed`, returns `{status, rows_created}`.
  - `list_matrix_rows(project_id, limit=200)` → returns rows for review.
  - `update_matrix_row(row_id, field, new_value)` → calls existing
    `PATCH /projects/{id}/matrix/{row_id}` service.
- `app/agents/assistant/tools/gap_tools.py`:
  - `detect_research_gaps(project_id)` → enqueue + poll.
  - `list_gaps(project_id)`.
  - `delete_gap(gap_id)`.
- `app/agents/assistant/tools/conflict_tools.py`:
  - `detect_conflicts(project_id)` → enqueue + poll.
  - `list_conflicts(project_id)`.
- `app/agents/assistant/tools/report_tools.py`:
  - `generate_report(project_id, title?, include_gap_section=True,
    selected_gap_ids?)` → enqueue + poll, returns `{report_id,
    validation_status, total_citations, invalid_citations}`.
  - `list_reports(project_id)`.
  - `get_report(project_id, report_id)` → full markdown + references.
  - `export_report_markdown(project_id, report_id)`.
- `app/agents/assistant/tools/evidence_tools.py`:
  - `retrieve_evidence(project_id, query, k=8, content_types?)` → calls
    `services.hybrid_retrieval.retrieve_project_evidence()`; returns chunks
    with `project_paper_id` and score.
- Tests for each module, mirroring the existing `tests/test_*_*.py`
  patterns.

**Acceptance criteria:**

- Each "long-running" tool (matrix/gaps/conflicts/report) blocks with
  polling (max 120s, 2s interval) and returns the final job status, not the
  job id.
- Citation guardrail is preserved: `generate_report` always returns the
  `validation_status` so the LLM can warn the user.
- All tools respect ownership (project_id must belong to the calling user).
- Polling never blocks the event loop longer than 2s between checks.

---

### Task 6 — Planner Agent

**What:** An agent that takes a user message (plus the active project
context) and returns a `Plan` JSON: a list of step objects with
`id`, `description`, `expected_tool`.

**Output artifacts:**

- `app/agents/assistant/agents/planner.py` — `PlannerAgent` class.
  - `create_plan(message, project_context) -> AsyncGenerator[BaseEvent]`
    yields `MessageEvent("reasoning…")` then `PlanEvent(CREATED, plan)`.
  - `update_plan(plan, last_step) -> AsyncGenerator[BaseEvent]` yields
    `PlanEvent(UPDATED, plan)` after each executed step.
- `app/ai/prompts.py` (extend) — new prompt constants:
  `PLANNER_SYSTEM_PROMPT`, `CREATE_PLAN_PROMPT`, `UPDATE_PLAN_PROMPT`.
- `app/ai/structured_outputs.py` (extend) — `PlanOutput`, `StepOutput`
  Pydantic models with strict schema.
- `tests/test_planner_agent.py` — uses a mock provider; asserts a valid plan
  is produced for a sample message.

**Acceptance criteria:**

- Output plan matches `PlanOutput` schema: `{title, language, steps: [...]}`.
- Each step has a unique `id`, a clear one-sentence `description`, and an
  `expected_tool` field the LLM uses for self-checking.
- The planner never invents tools; it must choose from the tool list
  injected via the system prompt.
- `update_plan` is idempotent when the plan is already complete.

---

### Task 7 — Execution Agent

**What:** An agent that executes one step at a time using the registered
tools, yielding `ToolEvent` and `MessageEvent` along the way.

**Output artifacts:**

- `app/agents/assistant/agents/execution.py` — `ExecutionAgent` class.
  - `execute_step(plan, step, message) -> AsyncGenerator[BaseEvent]`.
  - Drives the LangChain tool-calling loop (model → tool call → tool result
    → model) using the project's existing `app.ai.provider.get_provider()`.
  - On `ask_user_clarification` tool call, yields `WaitEvent` and returns.
- `app/ai/prompts.py` (extend) — `EXECUTION_SYSTEM_PROMPT`,
  `EXECUTION_PROMPT`, `SUMMARIZE_PROMPT`.
- `tests/test_execution_agent.py` — uses mock provider + 1 real tool; asserts
  `ToolEvent` and final `MessageEvent` are emitted in order.

**Acceptance criteria:**

- At most one LLM call per tool round-trip; no infinite loop.
- Tool results are appended to the LLM context exactly once.
- If the LLM produces a tool call for an unknown tool, an `ErrorEvent` is
  yielded and the step is marked `failed`.
- Final `MessageEvent` is yielded after the last tool call completes
  (or the model stops calling tools).

---

### Task 8 — PlanActFlow

**What:** The state machine that orchestrates planner + executor.

**Output artifacts:**

- `app/agents/assistant/flow.py` — `PlanActFlow(BaseFlow)`.
  - State enum: `IDLE → PLANNING → EXECUTING → UPDATING → SUMMARIZING →
    COMPLETED`.
  - `run(message) -> AsyncGenerator[BaseEvent]` walks the state machine.
  - Respects a `CancelledError` (from session stop) by yielding
    `DoneEvent()` and breaking the loop.
  - Hard limits: `max_steps=20`, `max_total_tokens=200_000`,
    `max_wall_time=600s`. Enforced at the start of each step.
- `tests/test_plan_act_flow.py` — uses mock planner + executor; verifies
  state transitions and limit enforcement.

**Acceptance criteria:**

- Every state transition emits the appropriate event (no silent jumps).
- Reaching any limit yields a clear `ErrorEvent` and a `DoneEvent`.
- Resume from `EXECUTING` after a `WaitEvent` is supported.

---

### Task 9 — AssistantSessionService

**What:** The application service that owns session lifecycle and exposes
`chat()` as an `AsyncGenerator[BaseEvent]`.

**Output artifacts:**

- `app/services/assistant/session_service.py`:
  - `create_session(db, user, project_id?) -> AssistantSession`.
  - `get_session(db, user, session_id) -> AssistantSession | None`.
  - `list_sessions(db, user) -> list[AssistantSessionSummary]`.
  - `delete_session(db, user, session_id)`.
  - `chat(session_id, user_id, message) -> AsyncGenerator[BaseEvent]` —
    builds toolkits, loads `AssistantPlan` from DB if resuming, runs
    `PlanActFlow`, persists every event and final plan.
  - `stop_session(session_id)`: set a cancellation flag in a Redis-free
    `asyncio.Event` map keyed by `session_id` (in-process; fine for single
    backend instance — document the limitation).
- `tests/test_assistant_session_service.py` — uses a test DB and mock
  flow; verifies events are persisted in order.

**Acceptance criteria:**

- `chat()` yields events in real time; the caller (router) forwards them
  to the SSE response.
- Persisted events can be replayed in `get_session()` for resume.
- A second `chat()` call on a running session returns `409` (or yields an
  `ErrorEvent` then `DoneEvent` — choose one and document it).

---

### Task 10 — Router & SSE Endpoint

**What:** FastAPI router with all REST endpoints and the SSE chat endpoint.

**Output artifacts:**

- `app/routers/assistant.py`:
  - `PUT /api/assistant/sessions` — create.
  - `GET /api/assistant/sessions` — list (lightweight summaries).
  - `GET /api/assistant/sessions/{id}` — full session with events.
  - `DELETE /api/assistant/sessions/{id}`.
  - `POST /api/assistant/sessions/{id}/stop` — cancel running task.
  - `POST /api/assistant/sessions/{id}/chat` — `EventSourceResponse` from
    `session_service.chat()`.
- `app/main.py` — register router under `/api/assistant`.
- `tests/test_assistant_routes.py` — uses `httpx.AsyncClient` against the
  app; verifies happy-path SSE stream and stop semantics.

**Acceptance criteria:**

- SSE response is `text/event-stream`, `Cache-Control: no-cache`,
  `X-Accel-Buffering: no`.
- Each SSE event has `event:` (type) and `data:` (JSON) lines.
- 401 on missing/invalid JWT; 404 on session not owned by user.
- Stop endpoint returns 204 within 1s and the in-flight `chat()` yields
  `DoneEvent()`.

---

### Task 11 — Frontend: API Client & Store

**What:** The TypeScript layer that talks to the assistant backend and holds
session state.

**Output artifacts:**

- `frontend/lib/api/assistant.ts` — `createSession`, `getSession`,
  `listSessions`, `deleteSession`, `stopSession`, `chat(sessionId, message,
  handlers)` (uses `@microsoft/fetch-event-source` or native `EventSource`
  with `fetch` POST fallback).
- `frontend/lib/stores/assistant-store.ts` (Zustand):
  - state: `sessions`, `activeSessionId`, `events: Map<id, Event[]>`,
    `isStreaming`, `currentPlan`, `currentToolArtifact`.
  - actions: `loadSessions`, `createSession`, `selectSession`, `sendMessage`,
    `stopStream`, `applyEvent(event)`, `clearUnread`.
- `frontend/lib/types/assistant.ts` — typed event union matching backend
  Pydantic schemas.
- `frontend/lib/stores/index.ts` (update) — export the new store.

**Acceptance criteria:**

- `chat()` returns a cancel function; clicking **Stop** calls it and
  triggers `stopSession()`.
- Reopening a session replays persisted events into the store before
  attaching the live stream.
- `applyEvent` correctly switches on `event.type` and dispatches to the
  right reducer (plan / step / tool / message / etc.).

---

### Task 12 — Frontend: Chat Page

**What:** The `/assistant` route with sidebar, message stream, plan panel,
and tool panel.

**Output artifacts:**

- `frontend/app/(app)/assistant/layout.tsx` — minimal layout that fits
  inside the existing `(app)` shell.
- `frontend/app/(app)/assistant/page.tsx` — redirects to the most recent
  session, or to `?new=1` flow that creates one and navigates.
- `frontend/app/(app)/assistant/sessions/[id]/page.tsx` — the actual chat
  page.
- `frontend/components/assistant/SessionList.tsx` — left sidebar; lists
  sessions, "+ New chat" button, click to switch.
- `frontend/components/assistant/ChatMessage.tsx` — renders one message
  bubble based on `event.type` (text / plan / step / tool / error).
- `frontend/components/assistant/ChatBox.tsx` — sticky-bottom input with
  Send / Stop, character limit, "Attach" placeholder.
- `frontend/components/assistant/PlanPanel.tsx` — sticky plan view with
  step statuses (idle / running / done / failed).
- `frontend/components/assistant/ToolPanel.tsx` + sub-views:
  - `PaperListView.tsx`
  - `MatrixPreview.tsx` (with "Open full matrix" button → `/projects/{id}/matrix`)
  - `GapListView.tsx` (link → `/projects/{id}/gaps`)
  - `ReportPreview.tsx` (link → `/projects/{id}/reports/{rid}`)
  - `EvidenceChunksView.tsx` (with chunk source highlight)
- `frontend/components/AppShell.tsx` (update) — add a sidebar entry
  "Assistant" pointing to `/assistant`.
- `frontend/lib/markdown.ts` (update if needed) — render report markdown.

**Acceptance criteria:**

- User can: create session → type message → see plan appear → watch each
  step's status update → open tool artifacts → click a deep link to the
  matching project page where edits are possible.
- The chat auto-scrolls to the latest message; a "Jump to latest" button
  appears when the user scrolls up.
- When the LLM asks a clarification (WaitEvent), the input is re-enabled
  with a placeholder echoing the question.
- "Stop" cancels the SSE connection immediately and resets `isStreaming`.

---

### Task 13 — Observability & Limits

**What:** Per-session telemetry and rate limiting.

**Output artifacts:**

- `app/services/assistant/metrics.py` — counters:
  `assistant_sessions_created`, `assistant_tool_calls_total{tool}`,
  `assistant_llm_tokens_total{role}`, `assistant_steps_total{status}`.
- `app/routers/assistant.py` (update) — log structured JSON per session
  (`session_id`, `user_id`, `step_count`, `wall_time`, `tool_calls`).
- `app/services/assistant/rate_limit.py` — per-user token bucket (in-memory
  or Redis if available; default to in-memory with TTL). Throttle: 10
  concurrent sessions, 100 messages / hour.
- `tests/test_assistant_metrics.py`,
  `tests/test_assistant_rate_limit.py`.

**Acceptance criteria:**

- Each session logs a single summary line with start, end, status,
  `steps_count`, `tokens_used`, `tool_calls`.
- A 6th concurrent session from the same user is rejected with HTTP 429.
- The 101st message in an hour is rejected with HTTP 429.

---

### Task 14 — Tests (end-to-end + quality)

**What:** Bring test coverage of the assistant surface to the same bar as
the rest of the project.

**Output artifacts:**

- `tests/test_assistant_models.py` (Task 1)
- `tests/test_assistant_events.py` (Task 2)
- `tests/test_assistant_tools_context.py` (Task 3)
- `tests/test_assistant_project_tools.py`, `tests/test_assistant_paper_tools.py`
  (Task 4)
- `tests/test_assistant_matrix_tools.py`, `tests/test_assistant_gap_tools.py`,
  `tests/test_assistant_conflict_tools.py`, `tests/test_assistant_report_tools.py`,
  `tests/test_assistant_evidence_tools.py` (Task 5)
- `tests/test_planner_agent.py`, `tests/test_execution_agent.py` (Tasks 6-7)
- `tests/test_plan_act_flow.py` (Task 8)
- `tests/test_assistant_session_service.py` (Task 9)
- `tests/test_assistant_routes.py` (Task 10)
- `tests/test_assistant_metrics.py`, `tests/test_assistant_rate_limit.py`
  (Task 13)
- One **integration test** that runs the real flow against a test DB with
  a mock LLM provider, simulating: "Find 5 RAG papers, save, generate
  matrix, summarize".

**Acceptance criteria:**

- `make test` passes with all new test files.
- Coverage for the assistant package is ≥ 80% lines.
- The integration test verifies event order:
  `title → plan → step.started → tool.calling → tool.called → step.completed
  → … → done`.

---

### Task 15 — Documentation & Demo

**What:** User-facing and developer-facing docs for the assistant.

**Output artifacts:**

- `docs/assistant.md` — user guide (5-min tour, example prompts,
  limitations).
- `docs/architecture/assistant-architecture.md` — system diagram + data
  flow + state machine description.
- `docs/architecture/api-design.md` (update) — new `/api/assistant/*`
  endpoint section with request/response examples.
- Update `docs/status.md` and `docs/README.md` to mention the assistant.
- A 90-second demo script (markdown) walking through the "find papers →
  save → matrix → review" flow entirely from chat.

**Acceptance criteria:**

- Every public endpoint is documented with at least one curl example.
- The state machine has a mermaid diagram.
- `docs/README.md` glossary gains the terms: `AssistantSession`,
  `PlanActFlow`, `AssistantEvent`, `WaitEvent`.

---

## 4. Dependency Graph

```
Task 1  Models                ─┐
Task 2  Event schemas         ─┤
Task 3  Tool skeleton         ─┴──► Task 4  Project/Paper tools
                                       │
                                       ├──► Task 5  Matrix/Gap/Conflict/Report/Evidence tools
                                       │
                                       ├──► Task 6  Planner
                                       ├──► Task 7  Executor
                                       │         │
                                       │         ▼
                                       └──► Task 8  PlanActFlow
                                                  │
                                                  ▼
                                                Task 9  SessionService
                                                       │
                                                       ▼
                                                Task 10 Router + SSE
                                                       │
                                ┌──────────────────────┴────────────────────┐
                                ▼                                           ▼
                          Task 11 Frontend API+Store                Task 13 Observability
                                │                                           │
                                ▼                                           │
                          Task 12 Chat Page  ◄──────────────────────────────┤
                                                                            │
                                ┌───────────────────────────────────────────┘
                                ▼
                          Task 14 Tests
                                ▼
                          Task 15 Docs & Demo
```

---

## 5. Definition of Done (per task)

A task is "done" only when **all** of the following hold:

1. Code merged to `main`, CI green (`make lint`, `make typecheck`, `make
   test`).
2. New tests added in the same PR; existing tests still pass.
3. No new TODOs or `pass` placeholders in production code.
4. If it added a new module, its docstring explains purpose in 1-2
   sentences.
5. If it touched a public API, `docs/architecture/api-design.md` and
   `docs/status.md` are updated in the same PR.
6. The demo flow in §6 below can be executed end-to-end after the task
   lands.

---

## 6. Demo Flow (target: 3-4 minutes)

The entire user journey runs inside the `/assistant` tab:

1. **Log in** as a researcher (~10s).
2. **Open Assistant** from the sidebar (~5s).
3. **Create a new session** pinned to project "RAG-MedQA" (~5s).
4. **Type:** "Find 8 recent papers on retrieval-augmented generation for
   medical question answering, save them, and generate the matrix."
5. Watch the plan appear, then each step stream:
   - `search_papers` (SS + PaperHub in parallel) — shows paper list in
     ToolPanel.
   - `save_paper_to_project` (×8) — status updates.
   - `generate_matrix` — background job polled to completion; matrix
     preview in ToolPanel.
6. **Type:** "Now show me the top 3 research gaps."
7. Watch `detect_research_gaps` run, gap list in ToolPanel, deep link to
   `/projects/{id}/gaps` for full evidence view.
8. **Type:** "Generate a literature review including those 3 gaps."
9. Watch `generate_report` run; report preview shows `validation_status =
   valid`; click "Open full report" → `/projects/{id}/reports/{rid}`.
10. **Type:** "Stop." (mid-flow, optional) — confirms cancellation works.

**The defining moment:** clicking a citation in the report still
traces back to a saved paper. The chat never weakens the citation
guardrail.

---

## 7. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | LLM hallucinates a tool that doesn't exist | High | Medium | Tool registry is injected into the system prompt; executor rejects unknown tool names with `ErrorEvent`. |
| 2 | Plan runs forever (runaway loop) | Medium | High | Hard caps: `max_steps`, `max_tokens`, `max_wall_time` enforced in `PlanActFlow` (Task 8). |
| 3 | User mixes papers across projects | Medium | High | Project context is required at session start; `ask_user_clarification` tool pauses flow when ambiguous. |
| 4 | Long-running tool blocks the event loop | Medium | High | All long tools use the existing background job pattern (`BackgroundJob`) and poll with `asyncio.sleep(2)`. |
| 5 | SSE reconnect loses context | Medium | Medium | Events are persisted; on reconnect, the client first calls `GET /sessions/{id}` to replay history, then re-opens the stream. |
| 6 | Token costs explode from verbose plans | Medium | Medium | `UPDATE_PLAN_PROMPT` instructs the planner to mark remaining steps done if no new info is needed. |
| 7 | Cancellation flag lost on multi-instance deploy | Low | Medium | Document in-process limitation; design note: move to Redis pub/sub in a follow-up. |
| 8 | Citation guardrail bypassed if report tool returns wrong shape | Low | High | `generate_report` tool is the **only** way to write a report and goes through the existing validated service — no new path. |

---

## 8. Open Questions

1. **Token usage telemetry:** do we surface per-session cost in the UI
   (settings page) or only in backend logs? — *defer to Task 13.*
2. **Sharing sessions:** is `/assistant/sessions/{id}/share` in scope, or
   defer to a later phase? — *recommend defer.*
3. **Streaming tokens for the assistant's own message:** the current event
   model yields `MessageEvent` once at the end of a step. Do we want
   true token-level streaming for the final summary? — *recommend
   follow-up; out of scope for v1.*
4. **Multi-language UI:** prompts are English; do we localize the chat
   replies? — *recommend English-only for v1; matches Lumen's current
   scope.*

---

## 9. Out-of-Scope (documented for clarity)

- Voice / TTS.
- Per-step token-level streaming.
- Multi-user collaborative sessions.
- Public share links for assistant sessions.
- Replacing the existing Matrix / Gaps / Map / Reports pages.
- Running any code in a sandbox (we are a domain app, not a general
  agent).
- Migrating assistant history when a user is deleted (just CASCADE).

---

## 10. References

- `docs/README.md` — overall product overview.
- `docs/architecture/system-overview.md` — three-layer architecture.
- `docs/architecture/backend-architecture.md` — FastAPI service boundaries.
- `docs/architecture/agent-rag-strategy.md` — LangGraph + Hybrid RAG
  rationale.
- `app/agents/graph.py` — the existing 9-node research workflow we are
  *not* duplicating.
- `ai-manus/backend/app/domain/services/flows/plan_act.py` — the
  reference Plan-Act flow we are adapting.
- `ai-manus/backend/app/interfaces/schemas/event.py` — the reference
  event schema we are adapting.
