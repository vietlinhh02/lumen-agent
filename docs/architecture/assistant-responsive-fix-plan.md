# Assistant Responsiveness and Message Stability Fix Plan

## Context

The assistant surface is mid-migration from the original Plan-Act design to a
ReAct/LangChain-style flow. The current code already has a ReAct agent package,
LangChain-compatible tools, SSE events, and persisted assistant sessions, but
the runtime contract between backend, SQL persistence, and frontend rendering is
not stable yet.

This document is a task plan, not an implementation patch.

## Current Findings

### 1. POST chat replays old history before live events

`app/routers/assistant.py` loads persisted events for a session and then
`stream_with_replay()` yields all of them before the new live run. The frontend
already loads session history through `GET /assistant/sessions/{id}` in
`selectSession()`, so every new message can receive duplicate historical events
again during the POST stream.

Observed code paths:

- `frontend/lib/stores/assistant-store.ts`: `selectSession()` loads detail
  events into the store.
- `app/routers/assistant.py`: `chat()` calls `service.get_persisted_events()`
  and replays those events before the live generator.

Why this breaks UI:

- The frontend optimistically adds a user message before the POST starts.
- Backend persists the same user message with a different event ID.
- POST stream replays old events first, then appends live events.
- The chat list is derived directly from events, so duplicates and reordering
  appear as flicker, message-count jumps, and old messages moving around.

### 2. The final answer is not streamed as a normal assistant message

The agent streams model output as `ThoughtEvent` deltas and only emits a
`MessageEvent(role="assistant")` after parsing the full text. For simple chat,
the code streams tokens once as thoughts, then calls the model again with
`complete()` before yielding the visible assistant message.

Observed code paths:

- `app/agents/assistant/react/agent.py`: `_run_react_loop()` emits streamed
  model text as `ThoughtEvent`, then emits final `MessageEvent` after parsing.
- `app/agents/assistant/react/agent.py`: `_run_simple_chat()` streams thoughts,
  then performs a second non-streaming completion for the final message.

Why this feels unresponsive:

- The user does not see the assistant answer bubble until the entire model call
  finishes.
- Chitchat pays for two model calls.
- If thoughts are collapsed, hidden, filtered, or unsupported, the UI appears
  blank until final completion.

### 3. Backend emits `progress`, frontend ignores it

`ProgressEvent(type="progress")` exists on the backend and is used by the
deterministic research pipeline, but the frontend event union and SSE dispatcher
do not include `progress`.

Observed code paths:

- `app/agents/assistant/events.py`: defines `ProgressEvent`.
- `app/agents/assistant/pipelines/research_pipeline.py`: emits progress at
  search, screen, save, matrix, gap, and report stages.
- `frontend/lib/types/assistant.ts`: `EventType` does not include `progress`.
- `frontend/lib/api/assistant.ts`: `dispatchEvent()` has no `progress` case.
- `frontend/app/(app)/assistant/sessions/[id]/page.tsx`: activity panel does
  not include `progress`.

Why this feels unresponsive:

- Long research pipeline stages can be running correctly, but the browser
  drops their progress events.

### 4. Event log is used as the chat render model

The frontend renders chat items by filtering and regrouping raw events on every
render. This makes the chat UI sensitive to every technical event type, replay
event, duplicate ID, and timestamp precision issue.

Observed code paths:

- `frontend/app/(app)/assistant/sessions/[id]/page.tsx`: derives
  `visibleEvents`, thought groups, and `chatItems` directly from `sessionEvents`.
- `frontend/lib/stores/assistant-store.ts`: stores a single event array per
  session and appends every incoming event.

Why this breaks stability:

- Tool, thought, progress, user message, assistant message, error, and done
  events are all mixed in one append-only render source.
- Technical event volume changes the shape of the visible message list.
- Persisted and live events are treated the same even though they have different
  UX semantics.

### 5. SQL persistence is too granular for live UI state

`AssistantSessionService.chat()` persists the user message and then persists
every emitted event with an immediate commit.

Observed code path:

- `app/services/assistant/session_service.py`: `_persist_event()` inserts one
  `assistant_events` row and commits for every event.

Why this causes latency and flicker:

- Streaming token or progress events become database write pressure.
- SQL event rows are later replayed into the live UI.
- The durable audit log is being treated as the realtime view model.

### 6. Current ReAct loop does not use native LangChain tool-call messages

Tools are LangChain-compatible, but the loop asks the model to output text
patterns like `Action:` and then parses JSON manually. LangChain's current
message model represents tool calls as structured `AIMessage.tool_calls`, and
tool outputs should be returned as `ToolMessage` with the matching tool call ID.

Observed code paths:

- `app/agents/assistant/react/agent.py`: `_parse_tool_calls_from_text()` parses
  free-form text.
- `app/agents/assistant/react/tool_caller.py`: has conversion helpers, but the
  main ReAct loop does not bind tools to the model and consume structured
  tool-call chunks.

Why this is fragile:

- Model formatting mistakes become runtime failures.
- The instruction says "parallel tools", but the loop executes parsed tool calls
  sequentially.
- Tool-call streaming cannot be represented cleanly in the UI.

## Research Notes

LangChain/LangGraph official docs point toward a cleaner split:

- Use event streaming projections for application-facing streams instead of
  making the UI parse every raw runtime event.
- Use message projections for chat tokens and tool-call projections for tool
  lifecycle.
- Use LangGraph checkpointers for short-term thread state and stores for
  long-term memory. The SQL event audit log should not be the only replay and
  resume mechanism.
- For tool calling, use structured AI/tool messages instead of manual
  `Action:` text parsing.

Implication for this codebase: moving to LangChain/LangGraph can help, but only
if the event contract is redesigned first. Simply wrapping the current raw event
array in LangChain will preserve the same flicker.

## Target Architecture

### Runtime contracts

Use three separate models:

1. `assistant_messages`: stable chat transcript shown in the UI.
2. `assistant_runs` or `assistant_events`: audit/progress/tool timeline.
3. LangGraph checkpoint/thread state: resumable agent state for a run.

### Streaming contracts

SSE should stream only events for the current submitted user turn:

- `message_ack`: canonical ID for the user's submitted message.
- `assistant_delta`: visible assistant answer token delta.
- `assistant_message_done`: final assistant message with canonical ID.
- `progress`: stage updates for long workflows.
- `tool_call_started`, `tool_call_delta`, `tool_call_done`.
- `run_done` or `run_error`.

Do not replay full session history from the POST chat endpoint. History belongs
to `GET /assistant/sessions/{id}` or a dedicated `GET /messages` endpoint.

## Task List

### P0. Stop replaying history from POST chat

Files:

- `app/routers/assistant.py`
- `frontend/lib/stores/assistant-store.ts`
- tests around assistant routes and store event handling

Work:

- Remove persisted-history replay from `POST /sessions/{id}/chat`.
- Keep replay/history loading only in `GET /sessions/{id}`.
- Add a regression test: sending a second message should stream only events for
  that second turn.

Acceptance:

- The same user message is not displayed twice.
- Old events are not re-appended during a new stream.
- Existing session reload still shows history through the GET endpoint.

### P0. Add canonical turn/message IDs

Files:

- `app/schemas/assistant.py`
- `app/agents/assistant/events.py`
- `app/services/assistant/session_service.py`
- `frontend/lib/types/assistant.ts`
- `frontend/lib/stores/assistant-store.ts`

Work:

- Add `turn_id` to all events emitted for one user request.
- Let the frontend send a `client_message_id` with the chat request.
- Persist the user message using that ID or return a `message_ack` that maps
  the optimistic local message to the canonical row.
- Deduplicate by semantic IDs (`message_id`, `turn_id`, `event_seq`), not only
  random event IDs.

Acceptance:

- Optimistic user message is replaced or confirmed, not duplicated.
- Reloaded transcript preserves the same message IDs.
- Event order is stable even when timestamps are equal or DB precision differs.

### P0. Stream visible assistant output as message deltas

Files:

- `app/agents/assistant/events.py`
- `app/agents/assistant/react/agent.py`
- `frontend/lib/types/assistant.ts`
- `frontend/lib/api/assistant.ts`
- `frontend/lib/stores/assistant-store.ts`
- `frontend/components/assistant/ChatMessage.tsx`

Work:

- Add `assistant_delta` or `message_delta` event type for visible response text.
- Emit final assistant message once, with accumulated content.
- Stop using `ThoughtEvent` as the visible answer stream.
- Remove the second `provider.complete()` call in `_run_simple_chat()`.

Acceptance:

- User sees the assistant answer bubble stream immediately.
- Chitchat uses one model call, not two.
- Thought/progress UI can be hidden without making the assistant look blank.

### P0. Wire `progress` events end to end

Files:

- `frontend/lib/types/assistant.ts`
- `frontend/lib/api/assistant.ts`
- `frontend/lib/stores/assistant-store.ts`
- `frontend/components/assistant/IterationPanel.tsx`
- `frontend/app/(app)/assistant/sessions/[id]/page.tsx`

Work:

- Add `ProgressEvent` to the TypeScript union.
- Add an `onProgress` dispatcher handler.
- Render latest progress per stage in the activity panel.
- Include progress in persisted-event normalization.

Acceptance:

- Research pipeline search/screen/save/matrix/gap/report stages appear while
  running.
- No unknown-event drops in the browser for `progress`.

### P1. Split transcript state from audit state

Files:

- `frontend/lib/stores/assistant-store.ts`
- `frontend/app/(app)/assistant/sessions/[id]/page.tsx`
- `frontend/components/assistant/*`

Work:

- Store `messagesBySession` separately from `eventsBySession`.
- Render chat from `messagesBySession`.
- Render tools/progress/debug panels from `eventsBySession`.
- Update messages by ID in place when deltas arrive.

Acceptance:

- Tool/progress/thought event volume does not change visible message count.
- Streaming updates only mutate the active assistant message content.
- No chat item keys use array index.

### P1. Reduce SQL writes during streaming

Files:

- `app/services/assistant/session_service.py`
- `app/db/models.py`
- tests for persistence/replay

Work:

- Persist canonical user/assistant messages as messages.
- Persist high-value audit events: tool start/done/error, progress milestones,
  run done/error.
- Do not persist every token delta as an individual SQL row.
- Batch audit event commits per logical step where possible.

Acceptance:

- One user turn creates predictable rows: user message, assistant message,
  tool/progress audit rows, run completion.
- Token streaming remains realtime but does not flood `assistant_events`.
- Session reload does not depend on replaying token deltas.

### P1. Fix session status semantics

Files:

- `app/db/models.py`
- `app/services/assistant/session_service.py`
- `app/routers/assistant.py`
- `frontend/lib/types/assistant.ts`

Work:

- Align backend statuses with frontend union.
- Avoid setting session status to `archived` on every `DoneEvent` if frontend
  expects `completed`.
- Keep `archived` for user-archived sessions only, or add it to the explicit
  frontend/backend contract.

Acceptance:

- Session list status is consistent after a completed run.
- No frontend type lies around status values.

### P2. Replace manual ReAct text parsing with native tool calls

Files:

- `app/agents/assistant/react/agent.py`
- `app/agents/assistant/react/tool_caller.py`
- `app/agents/assistant/react/prompts.py`
- provider adapter files under `app/ai/`

Work:

- Bind LangChain tools to the chat model.
- Read structured tool calls from streamed model chunks / final AI message.
- Return tool outputs as tool messages with matching call IDs.
- Execute independent tool calls with the existing `execute_parallel()` path.

Acceptance:

- No regex parsing of `Action:` is required for normal tool execution.
- Invalid tool arguments surface as structured tool errors.
- Multiple independent tool calls execute concurrently.

### P2. Consider LangGraph checkpointed agent runtime

Files:

- new `app/agents/assistant/graph/` or replacement under `react/`
- `app/services/assistant/session_service.py`
- persistence config

Work:

- Compile a LangGraph graph with a checkpointer.
- Use session ID as `thread_id`.
- Keep product data in existing services/tables.
- Keep chat transcript separate from graph checkpoints.

Acceptance:

- Human-in-the-loop wait/resume works without reconstructing scratchpad from
  raw SQL events.
- The graph can resume a session after interruption.
- The UI still consumes the stable SSE event contract above.

## Verification Plan

1. Backend route test: second chat request streams no old events.
2. Frontend store unit test: optimistic user message is acknowledged, not
   duplicated.
3. Frontend store unit test: `assistant_delta` updates one message in place.
4. Frontend store unit test: `progress` events update activity state without
   changing message count.
5. E2E smoke: create session, send "hi", see visible assistant text stream in
   under one second.
6. E2E smoke: run research pipeline, see progress stages before final summary.
7. Reload session, verify transcript count and order remain unchanged.

## Recommended Sequence

1. P0 replay removal.
2. P0 canonical turn/message IDs.
3. P0 visible message delta streaming.
4. P0 progress event wiring.
5. P1 transcript/audit state split.
6. P1 SQL persistence cleanup.
7. P2 native LangChain/LangGraph migration.

Do not start the LangGraph migration before the event contract is stable. The
current flicker is primarily a transport/state-model problem, not just an agent
framework problem.
