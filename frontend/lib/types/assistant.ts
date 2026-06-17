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

export interface PlanStepData {
  id: string;
  description: string;
  expected_tool: string;
  status: PlanStepStatus;
}

export interface PlanData {
  id: string;
  title: string | null;
  language: string | null;
  steps: PlanStepData[];
  current_step_index: number;
  status: PlanStatus;
  created_at: string;
  updated_at: string;
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
  plan: PlanData | null;
}

// ── Status Types ────────────────────────────────────────────────────────────────

export type SessionStatus = "idle" | "running" | "completed" | "failed" | "cancelled";
export type PlanStatus = "created" | "in_progress" | "completed" | "failed" | "cancelled";
export type PlanStepStatus = "pending" | "running" | "completed" | "failed";
export type ToolStatus = "calling" | "called" | "failed";
export type MessageRole = "user" | "assistant";

// ── Chat Types ─────────────────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
}

// ── SSE Event Types ────────────────────────────────────────────────────────────

/**
 * Base event structure for all SSE events.
 */
export interface BaseEvent {
  id: string;
  timestamp: string;
  type: EventType;
}

/**
 * Message event - text message from user or assistant.
 */
export interface MessageEvent extends BaseEvent {
  type: "message";
  role: MessageRole;
  content: string;
  attachments?: Array<Record<string, unknown>> | null;
}

/**
 * Title event - session title update.
 */
export interface TitleEvent extends BaseEvent {
  type: "title";
  title: string;
}

/**
 * A single step within a plan.
 */
export interface PlanStep {
  id: string;
  description: string;
  expected_tool: string;
  status: PlanStepStatus;
}

/**
 * Plan event - contains the current plan with all steps.
 */
export interface PlanEvent extends BaseEvent {
  type: "plan";
  plan_id: string;
  title: string;
  language: string;
  steps: PlanStep[];
}

/**
 * Step event - step status change notification.
 */
export interface StepEvent extends BaseEvent {
  type: "step";
  step_id: string;
  description: string;
  status: PlanStepStatus;
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
 * Union type of all possible SSE event data.
 */
export type AssistantEventData =
  | MessageEvent
  | TitleEvent
  | PlanEvent
  | StepEvent
  | ToolEvent
  | DoneEvent
  | ErrorEvent
  | WaitEvent;

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
  | "plan"
  | "step"
  | "tool"
  | "done"
  | "error"
  | "wait";

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
  
  // Current plan
  currentPlan: PlanData | null;
  
  // Current tool artifact (preview data from tool results)
  currentToolArtifact: ToolArtifact | null;
  
  // Error state
  error: string | null;
  
  // Actions
  loadSessions: (force?: boolean) => Promise<void>;
  createSession: (data?: SessionCreate) => Promise<SessionResponse | null>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  deleteSession: (id: string) => Promise<boolean>;
  sendMessage: (message: string) => Promise<void>;
  stopStream: () => void;
  applyEvent: (event: AssistantEventData) => void;
  clearUnread: (sessionId: string) => void;
  reset: () => void;
}
