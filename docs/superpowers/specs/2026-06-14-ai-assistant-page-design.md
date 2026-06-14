# AI Assistant Page — Design Spec

## Problem

The current research workflow requires users to manually click through 7 separate pages (search → save → matrix → gaps → report) and wait for each backend action to complete. For new users, this is overwhelming. For returning users, it is repetitive.

There is no single page where a user can say "I want to research RAG for medical QA" and watch the system autonomously create a project, find papers, build a matrix, detect gaps, and produce a citation-safe Markdown review — all in one session with real-time progress.

The pain points are:

1. **Too many manual steps** — 7 pages for the core workflow
2. **No conversational interface** — every action requires button clicks
3. **Hard to track progress** — user has to navigate between pages to see what completed
4. **Hard to iterate on output** — editing a report requires regenerating from scratch

## Goal

Build a new top-level page (`/assistant`) that:

1. Lets the user describe their research intent in natural language
2. Autonomously creates a new project, runs the full research pipeline, and produces a Markdown literature review
3. Streams real-time progress (checklist of pipeline steps + chat-style log)
4. Renders the Markdown output live in a preview pane
5. Lets the user continue chatting after the pipeline finishes: ask questions about the saved papers, edit specific sections, add more papers, regenerate the matrix, or detect more gaps
6. Persists the chat history and the Markdown document so the user can resume later

## User Mental Model

User opens `/assistant` and says: **"Tôi muốn tìm hiểu về RAG cho medical question answering"**.

The system:

1. Asks 1-2 clarifying questions to confirm project basics (title, topic, research question, max papers)
2. User confirms → system creates a `Project` in DB
3. System runs the full pipeline autonomously, streaming progress to the UI
4. At the end, the user sees a Markdown literature review in the right panel
5. User keeps chatting: "thêm 3 papers về clinical trial", "đoạn 2 viết ngắn lại", "paper nào nói về PubMedQA?"
6. Each chat message is a tool-calling turn that mutates the project or updates the document

## Decisions

| Area | Choice | Rationale |
|---|---|---|
| Mental model | AI auto-creates new Project + runs full pipeline | User explicitly chose "Option A" — new project from scratch |
| Auto-pilot level | Auto-pilot for routine, pause for important decisions | User chose hybrid: AI auto-runs sub-steps but pauses for project creation and key checkpoints |
| Post-pipeline actions | Q&A + edit report + add papers + regenerate matrix + add gaps | User chose "Balanced" — covers common follow-ups without over-scoping |
| Progress mechanism | WebSocket (full duplex) | User chose WebSocket for pause/resume + real-time events |
| Markdown editor mode | Chat-driven edit (no inline editing) | User chose "Chat-driven" — simpler UX, no Notion-style split editor |
| Data model | Separate `chat_documents` + `chat_messages` tables | User chose option 2 — chat is a parallel system, not tied to `review_reports` |
| Agent algorithm | Full LLM Agent (ReAct / function-calling) | User chose Approach A — most flexible, LLM picks tools in any order |

## Architecture

### System shape

```
┌──────────────────────────────────────────────────────────┐
│ Frontend: Next.js 16                                      │
│ ┌────────────────┬─────────────────────────────────────┐  │
│ │ Chat panel     │ Markdown preview panel              │  │
│ │ (left, ~40%)   │ (right, ~60%)                       │  │
│ │                │                                     │  │
│ │ • user msgs    │ Live-rendered HTML from .md         │  │
│ │ • agent msgs   │ (react-markdown, giống Reports)     │  │
│ │ • tool logs    │                                     │  │
│ │ • input box    │ Sticky header: title + version +   │  │
│ │                │ status badge                        │  │
│ └────────────────┴─────────────────────────────────────┘  │
│              ▲                                            │
│              │ WebSocket (wss://.../ws/assistant)         │
│              ▼                                            │
├──────────────────────────────────────────────────────────┤
│ Backend: FastAPI                                          │
│   ws /api/assistant/ws                                    │
│     ├─ AgentRunner (ReAct loop, max 20 iterations)        │
│     │   ├─ LLM with tool definitions                      │
│     │   ├─ Tool executor → existing services              │
│     │   └─ Progress emitter → ws.send_json                │
│     └─ Message store → chat_messages table                │
└──────────────────────────────────────────────────────────┘
```

### Component boundaries

| Component | Owns | Depends on |
|---|---|---|
| `AssistantPage` (frontend) | Layout, route handling | `useAssistantStore`, `useAssistantWS` |
| `ChatPanel` (frontend) | Message list, input box, send/stop | Zustand store |
| `PreviewPanel` (frontend) | Markdown render, version display | Zustand store (`currentMarkdown`) |
| `ProgressChecklist` (frontend) | Pipeline step states | Zustand store (`progress`) |
| `useAssistantWS` (frontend hook) | WebSocket lifecycle, event dispatch | Zustand store actions |
| `useAssistantStore` (Zustand) | All client state for the page | — |
| `AssistantWSRouter` (backend) | WS auth, message routing | `AssistantRunner` |
| `AssistantRunner` (backend) | ReAct loop, tool calls, progress emission | `AIProvider`, tool handlers |
| Tool handlers (8 modules in `app/services/assistant_tools/`) | One per tool | Existing services |

## Backend Design

### Tools (8 total, OpenAI function-calling format)

| Tool | Args | Returns | Wraps |
|---|---|---|---|
| `create_project` | `{title, topic, research_question, max_papers}` | `{project_id, status}` | `services/project.create_project` |
| `search_papers` | `{query, max_results, year_from, sources}` | `{papers_found, diagnostics}` | `services/paper_search.search_and_download` |
| `save_paper_to_project` | `{project_id, paper_dict, relevance_label}` | `{project_paper_id, status}` | `services/project.save_paper_to_project` |
| `generate_matrix` | `{project_id}` | `{rows_created, status}` | background job `services/literature_matrix.generate` |
| `detect_gaps` | `{project_id, max_gaps}` | `{gaps_created, status}` | background job `services/gap_detection` |
| `generate_report` | `{project_id, include_gaps, document_id}` | `{document_id, version, status}` | new `services/report_chat_doc.generate_for_chat` |
| `edit_report_section` | `{document_id, section_index, instruction}` | `{new_version, section_preview}` | new `services/report_chat_doc.edit_section` |
| `qa_search_papers` | `{project_id, question}` | `{answer, cited_paper_ids, evidence_chunks}` | RAG over saved papers via `services/hybrid_retrieval` |

**Tool execution semantics:**

- `create_project` runs synchronously and is **gated by user confirmation**. The agent decides to confirm by emitting a structured `needs_confirmation` event from the runner (this is NOT a tool the LLM calls — it's a special branch in the runner that pauses the loop, emits the event, and waits for a `user_response` from the client). The runner sends `{type: "needs_confirmation", prompt: "...", options: [...]}` to the WS, waits for client to send `{type: "user_response", choice: "..."}`, then proceeds. The agent system prompt instructs the LLM to always confirm project basics with one clear question before calling `create_project`.

- `search_papers`, `save_paper_to_project`, `generate_matrix`, `detect_gaps` are autonomous — the agent can call them without confirmation. They run in background where applicable and return a `job_id`; the runner polls/watches the job and emits `progress` events.

- `generate_report` is the only step after which the assistant emits `markdown_updated` so the preview panel updates.

- `edit_report_section` operates on a specific section by index. LLM rewrites only that section; rest of the document is preserved.

- `qa_search_papers` does RAG over the project's saved papers and returns cited answer. No document mutation.

### WebSocket protocol

**Endpoint:** `ws://.../api/assistant/ws?project_id=<uuid>&token=<jwt>`

**Client → Server** (JSON text frames):

```json
{ "type": "user_message", "content": "tôi muốn nghiên cứu về RAG y khoa" }
{ "type": "user_response", "choice": "ok", "payload": {} }
{ "type": "stop" }
{ "type": "resume" }
{ "type": "ping" }
```

**Server → Client** (JSON text frames):

| Event | Shape | Purpose |
|---|---|---|
| `connected` | `{session_id, project_id, resumed: bool}` | Confirm connection |
| `message_history` | `{messages: [...]}` | On reconnect: full chat history |
| `markdown_snapshot` | `{content, version, title}` | On reconnect: current doc state |
| `progress` | `{step, status, percent, label}` | Pipeline step state change |
| `log` | `{level, message}` | Human-readable log line (info/warn/error) |
| `tool_call` | `{tool, args, call_id}` | Agent decided to call a tool |
| `tool_result` | `{tool, call_id, summary, duration_ms, ok}` | Tool execution result |
| `agent_chunk` | `{delta, call_id}` | Streaming token from LLM |
| `agent_message` | `{content, role, message_id}` | Final agent message after a turn |
| `markdown_updated` | `{content, version, section_changed}` | Doc content changed |
| `needs_confirmation` | `{prompt, options, request_id}` | Agent paused, waiting for user |
| `done` | `{iterations, total_duration_ms}` | Agent finished a turn |
| `stopped` | `{}` | User stopped the agent |
| `error` | `{message, code, recoverable}` | Something broke |
| `pong` | `{}` | Heartbeat reply |

**Heartbeat:** Server sends `ping` frame every 30s; client must reply with `pong` (or text `{"type":"ping"}`). Disconnect on 2 missed pings.

### AgentRunner (`app/services/assistant_runner.py`)

```
class AssistantRunner:
    def __init__(self, db, user, project_id, document_id, ws_send):
        self.db = db
        self.user = user
        self.project_id = project_id
        self.document_id = document_id
        self.ws_send = ws_send  # async callable
        self.max_iterations = 20
        self.stopped = asyncio.Event()

    async def run_turn(self, user_message: str) -> None:
        """One user message → agent loops until done or stopped."""

    async def execute_tool(self, call: ToolCall) -> ToolResult:
        """Route tool call to handler, return result, emit events."""

    async def emit(self, event: dict) -> None:
        """Send JSON event to WS client."""
```

**ReAct loop:**

```
1. Append user message to history
2. Emit log: "🤔 Thinking..."
3. Call LLM with [system + history + tool definitions] + stream=True
4. For each streamed chunk: emit agent_chunk
5. If LLM returns tool_calls:
   a. For each tool call: emit tool_call
   b. Execute tool, emit tool_result
   c. Append tool result to history
   d. Loop to step 3
6. If LLM returns final text (no tool calls):
   a. Emit agent_message
   b. Emit done
7. If iterations >= 20: emit done with reason="max_iterations"
```

**System prompt** (`app/ai/prompts.py`):

```python
ASSISTANT_SYSTEM = """\
You are Lumen, an AI research assistant. You help researchers produce
defensible literature reviews from real academic papers.

You have access to 8 tools. Use them to:
1. Create a project when the user describes a research intent
2. Search academic sources for relevant papers
3. Save selected papers to the project
4. Build a literature matrix (structured extraction)
5. Detect research gaps from the matrix
6. Generate a citation-safe Markdown literature review
7. Edit specific sections of the review when the user asks
8. Answer questions about the saved papers using RAG

Rules:
- Always confirm project basics (title, topic, research question) with the user
  before calling create_project. Ask one clear question.
- After pipeline completes, the user can keep chatting. Match their intent
  to the right tool. For Q&A, use qa_search_papers. For edits, use
  edit_report_section. For adding more papers, use search_papers +
  save_paper_to_project.
- Be concise. Summarize what you did in 1-2 sentences after each tool call.
- Never invent paper titles, authors, or DOIs. Only cite what qa_search_papers
  or generate_report returns.
- If a tool fails, report the error to the user and suggest a next step.
- If the user stops you, save progress and wait.
"""
```

### Tool handlers (8 files in `app/services/assistant_tools/`)

Each handler is a single async function: `async def handle_<tool>(db, user, args, runner) -> dict`.

- `create_project.py` — wraps `services/project.create_project`, also creates initial `chat_documents` row
- `search_papers.py` — wraps `services/paper_search.search_and_download`
- `save_paper_to_project.py` — wraps `services/project.save_paper_to_project`
- `generate_matrix.py` — starts background job via `services/literature_matrix.generate`, polls until done
- `detect_gaps.py` — starts background job via `services/gap_detection`, polls until done
- `generate_report.py` — generates report markdown, writes to `chat_documents.content_md`
- `edit_report_section.py` — LLM rewrites one section, increments `chat_documents.version`
- `qa_search_papers.py` — RAG over saved papers using `hybrid_retrieval.retrieve_project_evidence`

The runner passes a `runner` reference to handlers so they can:
- Emit progress events (`runner.emit({"type": "progress", ...})`)
- Check stop signal (`runner.stopped.is_set()` → return early)
- Log (`runner.emit({"type": "log", "level": "info", "message": "..."})`)

### Background job handling

`generate_matrix`, `detect_gaps`, `generate_report` may be long-running. The handlers:

1. Submit work via `asyncio.ensure_future()` (the pattern already used in `app/routers/project.py:181` and `app/routers/search_session.py`). Each future runs in the same event loop and writes results to DB.
2. Handler `await`s the future and emits `progress` events as the job progresses (percent, step label)
3. Emit `tool_result` with summary when done
4. For `generate_report`, also emit `markdown_updated` with the full new content

If the user stops mid-job, the handler checks `runner.stopped.is_set()` between sub-steps. For already-running LLM calls, the call completes and partial result is returned. MVP does not implement a true job queue (Celery/RQ) — that is a stretch goal.

## Frontend Design

### Page layout (`frontend/app/(app)/assistant/page.tsx`)

```
┌─────────────────────────────────────────────────────────┐
│ Header: Project title (editable) │ Doc version │ Status │
├──────────────────────────────┬──────────────────────────┤
│ ChatPanel (40%)              │ PreviewPanel (60%)       │
│                              │                          │
│ ┌──────────────────────────┐ │ ┌────────────────────┐  │
│ │ ProgressChecklist        │ │ │ ReactMarkdown      │  │
│ │ □ Tạo project            │ │ │ render từ          │  │
│ │ ✓ Search papers          │ │ │ chat_documents     │  │
│ │ ✓ Save papers            │ │ │ .content_md        │  │
│ │ ▶ Generate matrix (40%)  │ │ │                    │  │
│ │ □ Detect gaps            │ │ │ (auto-scroll to    │  │
│ │ □ Generate report        │ │ │  latest version)   │  │
│ └──────────────────────────┘ │ └────────────────────┘  │
│                              │                          │
│ ┌──────────────────────────┐ │                          │
│ │ ChatMessages (scroll)    │ │                          │
│ │ • user bubble            │ │                          │
│ │ • agent bubble (stream)  │ │                          │
│ │ • tool log line          │ │                          │
│ └──────────────────────────┘ │                          │
│                              │                          │
│ ┌──────────────────────────┐ │                          │
│ │ [Stop]  Input box  [Send]│ │                          │
│ └──────────────────────────┘ │                          │
└──────────────────────────────┴──────────────────────────┘
```

### Routing

- `/assistant` (no project yet) — shows "Tạo project mới" wizard, empty preview
- `/assistant/[projectId]` — loads existing session, restores chat history + doc

### Components

| File | Purpose |
|---|---|
| `app/(app)/assistant/page.tsx` | Entry, decides wizard vs existing session |
| `app/(app)/assistant/[projectId]/page.tsx` | Existing session |
| `components/assistant/ChatPanel.tsx` | Message list + input |
| `components/assistant/PreviewPanel.tsx` | Markdown render |
| `components/assistant/ProgressChecklist.tsx` | Pipeline step list |
| `components/assistant/MessageBubble.tsx` | Single chat message |
| `components/assistant/ToolLog.tsx` | Tool call + result log line |
| `components/assistant/StatusBadge.tsx` | Header status indicator |
| `components/assistant/AssistantHeader.tsx` | Top bar with title + version |

### State management (Zustand `useAssistantStore`)

```typescript
type AssistantState = {
  // Identity
  projectId: string | null;
  documentId: string | null;
  userId: string;

  // Chat
  messages: ChatMessage[];
  streamingMessage: string | null;  // current agent message being streamed

  // Document
  currentMarkdown: string;
  documentVersion: number;
  documentTitle: string;

  // Progress
  progress: Record<PipelineStep, { status: "pending" | "running" | "done" | "failed"; percent: number }>;
  currentLog: LogEntry[];  // last 50 log lines

  // Agent
  agentStatus: "idle" | "thinking" | "running" | "needs_confirmation" | "stopped" | "done" | "error";
  pendingConfirmation: { prompt: string; options: string[]; requestId: string } | null;

  // Connection
  ws: WebSocket | null;
  wsConnected: boolean;

  // Actions
  connect: (projectId: string) => Promise<void>;
  disconnect: () => void;
  sendMessage: (content: string) => void;
  sendUserResponse: (choice: string) => void;
  stop: () => void;
  handleEvent: (event: AssistantEvent) => void;
  reset: () => void;
};
```

### WebSocket hook (`useAssistantWS`)

```typescript
function useAssistantWS(projectId: string | null) {
  const store = useAssistantStore();

  useEffect(() => {
    if (!projectId) return;
    const ws = new WebSocket(`${WS_URL}/api/assistant/ws?project_id=${projectId}&token=${token}`);
    store.setWs(ws);

    ws.onopen = () => store.setConnected(true);
    ws.onclose = () => store.setConnected(false);
    ws.onmessage = (e) => {
      const event = JSON.parse(e.data);
      store.handleEvent(event);
    };
    ws.onerror = (e) => console.error(e);

    return () => ws.close();
  }, [projectId]);
}
```

### Markdown rendering

Reuse `react-markdown` (already in `components/reports/ReportContent.tsx`). On `markdown_updated` event, replace `currentMarkdown` in store. Component re-renders. Smooth fade-in transition (Tailwind `transition-opacity`).

## Data Model

### New tables (2)

**`chat_documents`**

```sql
CREATE TABLE chat_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  content_md TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  INDEX ix_chat_documents_project (project_id)
);
```

One row per chat session. `version` increments on every `edit_report_section` or `generate_report` call.

**`chat_messages`**

```sql
CREATE TABLE chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES chat_documents(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool_log')),
  content TEXT NOT NULL,
  tool_name TEXT,                    -- for tool_log: which tool
  tool_args JSONB,                   -- for tool_log: input
  tool_result JSONB,                 -- for tool_log: output summary
  agent_run_id UUID,                 -- links to agent_runs (existing)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  INDEX ix_chat_messages_document (document_id, created_at)
);
```

### Existing tables reused

- `projects` — created by `create_project` tool
- `papers`, `project_papers` — created by `search_papers` + `save_paper_to_project`
- `literature_matrix_rows` — created by `generate_matrix`
- `research_gaps`, `gap_evidence` — created by `detect_gaps`
- `agent_runs`, `agent_steps` — one row per agent turn, populated by runner

## REST Endpoints (read-only + history)

WebSocket is the only write path. REST is for reading history and listing.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/assistant/documents` | List user's chat documents (latest per project) |
| `GET` | `/api/assistant/documents/{id}` | Get doc + full message history |
| `GET` | `/api/assistant/documents/{id}/export` | Download `.md` file |
| `DELETE` | `/api/assistant/documents/{id}` | Delete a chat session |

`POST` is not exposed — all writes go through the WebSocket.

## Data Flow

### First-time session (no project)

```
1. User navigates to /assistant
2. Frontend: no projectId, shows wizard ("Tôi muốn nghiên cứu về...")
3. User types "RAG cho medical QA"
4. Frontend opens WS to /api/assistant/ws (project_id = "new" or null)
5. Backend creates a temporary "intent" record, sends {type: "connected", session_id}
6. User message → Runner turns
7. Agent calls request_user_confirmation with project basics
8. Runner emits {type: "needs_confirmation", prompt: "Confirm project: title='RAG Medical QA', topic='...'", options: ["OK", "Sửa"]}
9. User clicks OK → sends {type: "user_response", choice: "OK"}
10. Runner calls create_project tool → gets project_id
11. Runner creates chat_documents row, updates WS to include real project_id
12. Agent continues: search_papers → save_paper_to_project → ... → generate_report
13. Each step emits progress + tool_call + tool_result
14. At end: emits markdown_updated with full content
15. Frontend updates preview, sets URL to /assistant/[newProjectId]
```

### Resume session

```
1. User navigates to /assistant/[projectId]
2. Frontend calls GET /api/assistant/documents/{id} → loads chat_documents + chat_messages
3. Frontend renders message history + current markdown
4. Frontend opens WS with project_id
5. Backend sends {type: "connected", resumed: true} + {type: "message_history"} + {type: "markdown_snapshot"}
6. Store hydrates from server, WS events now drive live updates
```

## Error Handling

| Error | Source | Client behavior |
|---|---|---|
| LLM provider timeout | `AIProvider` | Emit `error` with `code: "ai_timeout"`, show "AI đang chậm, thử lại sau" toast, mark step failed |
| Tool not found | LLM hallucination | Runner strips invalid tool, returns error to LLM, LLM retries |
| Tool exception | Any handler | Runner catches, returns error string to LLM, LLM responds naturally |
| Project not found | DB query | WS disconnects with `error` frame, client shows "Project không tồn tại" |
| WebSocket disconnect | Network | Client retries with backoff (1s, 2s, 4s, max 30s), shows "Đang kết nối lại..." badge |
| User stops mid-pipeline | `stop` frame | Runner sets stopped flag, finishes current tool call, emits `stopped`, saves partial state |
| Background job fails | Job runner | Emit `error` for the step, mark step `failed`, allow user to retry |

## Testing

| Test | File | Type |
|---|---|---|
| `AssistantRunner` ReAct loop with mocked LLM | `tests/test_assistant_runner.py` | Unit |
| Tool handler: `create_project` | `tests/test_assistant_tools.py` | Unit |
| Tool handler: `search_papers` | `tests/test_assistant_tools.py` | Unit |
| Tool handler: `edit_report_section` increments version | `tests/test_assistant_tools.py` | Unit |
| Tool handler: `qa_search_papers` returns cited answer | `tests/test_assistant_tools.py` | Unit |
| WebSocket auth (valid + invalid token) | `tests/test_assistant_ws.py` | Integration |
| WebSocket resume sends history + snapshot | `tests/test_assistant_ws.py` | Integration |
| Frontend: `useAssistantStore` handles all event types | `frontend/__tests__/assistantStore.test.ts` | Unit |
| Frontend: WebSocket reconnect on disconnect | `frontend/__tests__/useAssistantWS.test.ts` | Unit |

## Files to Create / Modify

### Create

| File | Purpose |
|---|---|
| `app/services/assistant_runner.py` | ReAct agent loop |
| `app/services/assistant_tools/` | 8 tool handler files |
| `app/services/report_chat_doc.py` | Generate + edit Markdown doc |
| `app/routers/assistant.py` | REST endpoints for history/export |
| `app/routers/assistant_ws.py` | WebSocket endpoint |
| `app/schemas/assistant.py` | Pydantic models |
| `app/db/migrations/004_chat_documents.sql` | Alembic migration |
| `frontend/app/(app)/assistant/page.tsx` | Wizard entry page |
| `frontend/app/(app)/assistant/[projectId]/page.tsx` | Existing session page |
| `frontend/components/assistant/*.tsx` | 8 components listed above |
| `frontend/lib/stores/assistantStore.ts` | Zustand store |
| `frontend/lib/hooks/useAssistantWS.ts` | WebSocket hook |
| `frontend/lib/api/assistant.ts` | REST client |
| `tests/test_assistant_runner.py` | Runner unit tests |
| `tests/test_assistant_tools.py` | Tool handler unit tests |
| `tests/test_assistant_ws.py` | WS integration tests |

### Modify

| File | Change |
|---|---|
| `app/db/models.py` | Add `ChatDocument`, `ChatMessage` models |
| `app/main.py` | Register assistant routers |
| `app/ai/prompts.py` | Add `ASSISTANT_SYSTEM` |
| `app/ai/provider.py` | (no change — `complete_structured` and `stream` already exist) |
| `frontend/components/AppShell.tsx` | Add "AI Assistant" sidebar item |
| `frontend/lib/types.ts` | Add `ChatMessage`, `PipelineStep`, `AssistantEvent` types |

## Non-Goals (MVP)

- Multiple chat sessions per project — MVP: 1 chat per project (latest wins)
- Branching conversations / undo
- Voice input
- Image upload / OCR
- Sharing chat sessions between users
- Export to PDF / DOCX (Markdown only)
- Code execution / web browsing tools
- Multi-user collaboration on the same document
- Custom tool definitions by user

## Edge Cases

1. **Project creation fails** (e.g., duplicate title) — emit error, runner does not proceed, ask user to retry with different title
2. **Empty search results** — runner reports "Không tìm được paper nào", asks user to broaden query
3. **All search sources fail** — emit error with diagnostics, allow user to retry individual sources
4. **Matrix generation returns 0 rows** — emit warning, skip gap detection, still attempt report (will be empty)
5. **LLM returns malformed tool call** — runner logs, asks LLM to retry, max 3 attempts
6. **User sends message while agent is running** — reject with `error` "Agent đang bận, vui lòng đợi hoặc bấm Stop"
7. **User disconnects WS mid-tool-call** — runner continues (state in DB), client gets history on reconnect
8. **Two browser tabs open same session** — both connect, both receive events; first to send "stop" wins
9. **Project deleted while session open** — runner detects on next DB call, emits error, closes WS

## Success Criteria

The MVP is complete when:

1. User can open `/assistant`, describe a research intent, and within 1-2 minutes see a complete Markdown literature review in the preview pane
2. Progress is visible in real-time (no more than 2s delay between server emit and UI update)
3. User can continue chatting after the pipeline: add papers, edit sections, ask questions
4. Closing the browser and reopening `/assistant/[projectId]` restores the full session
5. The project created by the assistant appears in `/projects` and is editable through all existing pages
6. Citation guardrail still works: the generated Markdown only cites saved project papers
7. Tests pass: `pytest tests/test_assistant_*.py -v` all green
8. Frontend types check: `tsc --noEmit` clean
9. Lint clean: `ruff check` and `oxlint` both green
