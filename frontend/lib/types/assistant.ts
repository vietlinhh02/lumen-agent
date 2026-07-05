/**
 * TypeScript types for the Assistant API and SSE events.
 * 
 * These types mirror the backend Pydantic schemas in:
 * - app/schemas/assistant.py (API request/response)
 * - app/agents/assistant/events.py (SSE events)
 */

// ── Session Types ─────────────────────────────────────────────────────────────

export interface SessionCreate {
  project_id?: string | null;
  title?: string | null;
}

export interface SessionResponse {
  id: string;
  title: string | null;
  project_id: string | null;
  status: string;
  created_at: string;
}

export interface SessionSummary {
  id: string;
  title: string | null;
  project_id: string | null;
  project_title: string | null;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  event_count: number;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
  total: number;
}

export interface SessionEvent {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface SessionDetail {
  id: string;
  title: string | null;
  project_id: string | null;
  project_title: string | null;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  events: SessionEvent[];
}

// ── Status Types ────────────────────────────────────────────────────────────────
/**
 * Session status values, aligned with backend SessionStatus.
 * 
 * Status flow:
 *   - 'active': Session exists and can receive messages (default on creation)
 *   - 'completed': A chat turn completed successfully
 *   - 'failed': A chat turn failed with an error
 *   - 'cancelled': A chat turn was cancelled (stop button)
 *   - 'archived': User manually archived the session (NOT auto-set by system)
 * 
 * Note: 'idle' and 'running' are deprecated frontend concepts.
 * Use 'active' for ready sessions and check isStreaming for ongoing chat.
 */
export type SessionStatus = "active" | "completed" | "failed" | "cancelled" | "archived";
export type ToolStatus = "calling" | "called" | "failed";
export type MessageRole = "user" | "assistant";

// ── Chat Types ─────────────────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
  client_message_id?: string | null;
}

// ── SSE Event Types ────────────────────────────────────────────────────────────

/**
 * Base event structure for all SSE events.
 */
export interface BaseEvent {
  id: string;
  timestamp: string;
  type: EventType;
  /** Turn identifier grouping all events for a single user request. */
  turn_id?: string | null;
}

/**
 * Message event - text message from user or assistant.
 */
export interface MessageEvent extends BaseEvent {
  type: "message";
  role: MessageRole;
  content: string;
  attachments?: Array<Record<string, unknown>> | null;
  /** Turn identifier grouping all events for a single user request. */
  turn_id?: string | null;
}

/**
 * Message ack event - acknowledges a client-generated message ID.
 * The frontend should replace optimistic messages with this canonical ID.
 */
export interface MessageAckEvent extends BaseEvent {
  type: "message_ack";
  /** The client's message ID */
  client_message_id: string;
  /** The canonical event ID assigned by backend */
  canonical_id: string;
  /** The turn ID for this user request */
  turn_id: string;
}

/**
 * Assistant delta event - streaming chunk of the visible assistant message.
 * Unlike ThoughtEvent (internal reasoning), this streams the actual answer
 * that the user sees in the chat bubble.
 */
export interface AssistantDeltaEvent extends BaseEvent {
  type: "assistant_delta";
  /** Incremental token chunk for the visible assistant message */
  delta: string;
  /** True for the last token, signaling the message is complete */
  is_final?: boolean;
}

/**
 * Title event - session title update.
 */
export interface TitleEvent extends BaseEvent {
  type: "title";
  title: string;
}

/**
 * Tool event - tool call (both calling and result).
 */
export interface ToolEvent extends BaseEvent {
  type: "tool";
  tool_call_id: string;
  name: string;
  status: ToolStatus;
  function: string;
  args: Record<string, unknown>;
  result?: unknown | null;
  error?: string | null;
}

/**
 * Done event - session completion signal.
 */
export interface DoneEvent extends BaseEvent {
  type: "done";
  summary?: string | null;
}

/**
 * Error event - error condition.
 */
export interface ErrorEvent extends BaseEvent {
  type: "error";
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

/**
 * Wait event - assistant waiting for user input (clarification).
 */
export interface WaitEvent extends BaseEvent {
  type: "wait";
  question: string;
  options?: string[] | null;
  placeholder?: string | null;
}

/**
 * Thought event - streaming chunk of the ReAct agent's chain-of-thought.
 * The frontend should accumulate `delta` into a per-iteration buffer
 * so the user sees reasoning tokens stream in real time.
 */
export interface ThoughtEvent extends BaseEvent {
  type: "thought";
  /** Incremental token chunk for this Thought. */
  delta: string;
  /** ReAct iteration index (0-indexed). */
  iteration: number;
  /** True for the last token of the current Thought. */
  is_final?: boolean;
}

/**
 * Iteration event - marks the start of a new ReAct iteration and its phase.
 * Emitted right before reasoning (streaming Thought tokens) and again
 * right before acting (executing tool calls).
 */
export interface IterationEvent extends BaseEvent {
  type: "iteration";
  /** Current iteration number (0-indexed). */
  n: number;
  /** Max iterations cap (e.g., 15). */
  max: number;
  /** Current phase within the iteration. */
  phase: "reasoning" | "acting";
}

/**
 * Progress event - marks progress in a multi-stage pipeline.
 * Emitted by pipeline orchestrators (e.g., ResearchPipeline) so the UI
 * can render a real-time progress bar without having to parse tool events.
 */
export interface ProgressEvent extends BaseEvent {
  type: "progress";
  /** Pipeline stage name (e.g., 'search', 'matrix'). */
  stage: string;
  /** Progress fraction within the pipeline (0.0 - 1.0). */
  progress: number;
  /** Human-readable status message. */
  message: string;
  /** Optional structured data (counts, IDs, links). */
  data?: Record<string, unknown> | null;
}

/**
 * Union type of all possible SSE event data.
 */
export type AssistantEventData =
  | MessageEvent
  | TitleEvent
  | ToolEvent
  | DoneEvent
  | ErrorEvent
  | WaitEvent
  | ThoughtEvent
  | IterationEvent
  | MessageAckEvent
  | AssistantDeltaEvent
  | ProgressEvent;

/**
 * Discriminated union event type with event name for SSE.
 */
export interface SSEEvent {
  event: string;
  data: AssistantEventData;
}

/**
 * Event type literal for discriminated union.
 */
export type EventType =
  | "message"
  | "title"
  | "tool"
  | "done"
  | "error"
  | "wait"
  | "thought"
  | "iteration"
  | "message_ack"
  | "assistant_delta"
  | "progress";

// ── Chat Result Type ───────────────────────────────────────────────────────────

/**
 * Result from chat() function with cancel capability.
 */
export interface ChatResult {
  /** Call this to cancel the stream */
  cancel: () => void;
  /** Promise that resolves when the stream ends */
  finished: Promise<void>;
}

// ── Tool Result Types ──────────────────────────────────────────────────────────

/**
 * Generic tool result wrapper.
 */
export interface ToolResult<T = unknown> {
  ok: boolean;
  data?: T;
  error_code?: string;
  message?: string;
}

/**
 * Project listing result.
 */
export interface ProjectListResult {
  id: string;
  name: string;
  topic: string;
}

/**
 * Paper search result.
 */
export interface PaperSearchResult {
  title: string;
  authors: Array<{ name: string; author_id?: string }>;
  year: number | null;
  venue: string | null;
  doi: string | null;
  citation_count: number | null;
  source: string;
}

/**
 * Save paper result.
 */
export interface SavePaperResult {
  project_paper_id: string;
  status: string;
  duplicate: boolean;
}

/**
 * Matrix row.
 */
export interface MatrixRowResult {
  id: string;
  paper_title: string | null;
  research_problem: string | null;
  method: string | null;
  dataset_or_context: string | null;
  key_result: string | null;
  limitation: string | null;
  contribution: string | null;
}

/**
 * Gap result.
 */
export interface GapResult {
  id: string;
  title: string;
  description: string;
  suggested_direction: string;
  confidence: string;
}

/**
 * Conflict result.
 */
export interface ConflictResult {
  id: string;
  title: string;
  description: string;
  paper_a_title: string;
  paper_b_title: string;
  confidence: string;
}

/**
 * Report result.
 */
export interface ReportResult {
  id: string;
  title: string;
  validation_status: string;
  total_citations: number;
  invalid_citations: number;
}

/**
 * Evidence chunk result.
 */
export interface EvidenceChunkResult {
  project_paper_id: string;
  title: string;
  chunk_text: string;
  score: number;
  page_start?: number | null;
  page_end?: number | null;
}

// ── Store State Types ──────────────────────────────────────────────────────────

/**
 * Tool artifact for preview panels.
 */
export interface ToolArtifact {
  type: "papers" | "matrix" | "gaps" | "conflicts" | "report" | "evidence" | "project" | null;
  title: string;
  data: unknown;
  projectId?: string | null;
  reportId?: string | null;
}

/**
 * State for the assistant store.
 */
export interface AssistantState {
  // Sessions
  sessions: SessionSummary[];
  loadingSessions: boolean;
  activeSessionId: string | null;
  
  // Current session
  currentSession: SessionDetail | null;
  loadingSession: boolean;
  
  // Events
  events: Map<string, AssistantEventData[]>;
  
  // Streaming state
  isStreaming: boolean;
  
  // Current tool artifact (preview data from tool results)
  currentToolArtifact: ToolArtifact | null;
  
  // Error state
  error: string | null;
  
  // Actions
  loadSessions: (force?: boolean) => Promise<void>;
  createSession: (data?: SessionCreate) => Promise<SessionResponse | null>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  updateSessionProject: (sessionId: string, projectId: string | null) => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<boolean>;
  sendMessage: (message: string) => Promise<void>;
  sendResearchMessage: (message: string) => Promise<void>;
  stopStream: () => void;
  applyEvent: (event: AssistantEventData) => void;
  clearUnread: (sessionId: string) => void;
  reset: () => void;
}
