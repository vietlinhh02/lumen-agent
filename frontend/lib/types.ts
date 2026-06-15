export interface ProjectCreate {
  title: string;
  topic: string;
  research_question?: string | null;
}

export interface ProjectResponse {
  id: string;
  owner_id: string;
  title: string;
  topic: string;
  research_question: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  paper_count: number;
}

export interface ProjectListResponse {
  projects: ProjectResponse[];
}

export interface ProjectPaperResponse {
  id: string;
  project_id: string;
  paper_id: string;
  status: string;
  relevance_label: string | null;
  user_note: string | null;
  full_text_status: string | null;
  saved_at: string;
  title: string;
  abstract: string | null;
  year: number | null;
  venue: string | null;
  doi: string | null;
  arxiv_id: string | null;
  authors: Array<{ name: string; author_id?: string }>;
  citation_count: number | null;
  pdf_path: string | null;
  has_matrix: boolean;
  has_enrichment: boolean;
}

export interface PaperAuthor {
  name: string;
  author_id: string | null;
}

export interface PaperResult {
  title: string;
  abstract: string | null;
  year: number | null;
  venue: string | null;
  doi: string | null;
  arxiv_id: string | null;
  semantic_scholar_id: string | null;
  url: string | null;
  citation_count: number | null;
  authors: PaperAuthor[];
  fields_of_study: string[];
  is_open_access: boolean | null;
  source_names: string[];
  source_specific: Record<string, unknown>;
  pdf_downloaded: boolean;
  pdf_path: string | null;
  pdf_source: string | null;
}

export interface PaperSearchResponse {
  query: string;
  total_found: number;
  total_returned: number;
  search_time_ms: number;
  download_time_ms: number | null;
  pdfs_downloaded: number;
  pdfs_failed: number;
  papers: PaperResult[];
}

export interface SavePaperRequest {
  paper_title: string;
  paper_abstract?: string | null;
  paper_year?: number | null;
  paper_venue?: string | null;
  paper_doi?: string | null;
  paper_arxiv_id?: string | null;
  paper_semantic_scholar_id?: string | null;
  paper_url?: string | null;
  paper_citation_count?: number | null;
  paper_authors?: Array<Record<string, string>>;
  paper_source_names?: string[];
  source_specific?: Record<string, unknown>;
  relevance_label?: string | null;
  user_note?: string | null;
  download_pdf?: boolean;
}

export interface SavePaperResponse {
  project_paper_id: string;
  paper_id: string;
  title: string;
  status: string;
  pdf_path: string | null;
  full_text_status: string | null;
}

export interface SuggestQueriesResponse {
  queries: string[];
}

export interface ScreenPapersResponse {
  scores: string[];
}

export interface SessionListItem {
  id: string;
  project_id: string;
  user_query: string;
  total_results: number;
  created_at: string;
}

export interface SessionListResponse {
  sessions: SessionListItem[];
}

export interface SessionDetailResponse {
  id: string;
  project_id: string;
  user_query: string;
  total_results: number;
  screening_scores: string[];
  created_at: string;
  page: number;
  page_size: number;
  total_pages: number;
  papers: Record<string, unknown>[];
  saved_paper_ids: string[];
  detected_language?: string | null;
  query_variants?: QueryVariant[];
  language_bias_audit?: LanguageBiasAudit | null;
  source_diagnostics?: SourceDiagnostic[];
}

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

export interface SourceDiagnostic {
  source: string;
  status: string;
  result_count: number;
  message?: string;
}

export interface AutoSaveResponse {
  saved: number;
  skipped: number;
  error?: string;
}

export interface NormalizeResponse {
  processed: number;
  skipped: number;
  failed: number;
}

export interface FullTextChunk {
  section_label: string | null;
  section_path: string | null;
  chunk_index: number | null;
  page_start: number | null;
  page_end: number | null;
  content_type: string | null;
  pipeline_version: string | null;
  content_hash: string | null;
  chunk_text: string;
  char_count: number;
}

export interface FullTextResponse {
  project_paper_id: string;
  title: string;
  full_text_status: string | null;
  total_chars: number;
  total_chunks: number;
  chunks: FullTextChunk[];
  crawled_markdown: string | null;
}

// ── Literature Matrix ───────────────────────────────────────────────────

export interface MatrixRowResponse {
  id: string;
  project_id: string;
  project_paper_id: string;
  paper_title: string | null;
  research_problem: string | null;
  method: string | null;
  dataset_or_context: string | null;
  key_result: string | null;
  limitation: string | null;
  contribution: string | null;
  relevance: string | null;
  extraction_confidence: string;
  created_by: string;
  updated_at: string | null;
}

export interface MatrixListResponse {
  items: MatrixRowResponse[];
}

export interface MatrixRowUpdate {
  research_problem?: string;
  method?: string;
  dataset_or_context?: string;
  key_result?: string;
  limitation?: string;
  contribution?: string;
  relevance?: string;
  extraction_confidence?: string;
}

export interface MatrixGenerateResponse {
  status: string;
  created_count: number;
  skipped_count: number;
}

// ── Research Gaps ──────────────────────────────────────────────────────

export interface GapEvidenceResponse {
  project_paper_id: string;
  title: string;
  evidence_type: string;
  note: string;
}

export interface GapResponse {
  id: string;
  title: string;
  description: string;
  suggested_direction: string;
  evidence_summary: string;
  confidence: string;
  evidence: GapEvidenceResponse[];
}

export interface GapListResponse {
  items: GapResponse[];
  total: number;
}

// ── Conflicting Findings ───────────────────────────────────────────────

export interface ConflictResponse {
  id: string;
  title: string;
  description: string;
  paper_a_id: string;
  paper_a_title: string;
  paper_b_id: string;
  paper_b_title: string;
  shared_context: string | null;
  claim_a: string | null;
  claim_b: string | null;
  possible_explanation: string | null;
  confidence: string;
}

export interface ConflictListResponse {
  items: ConflictResponse[];
  total: number;
}

// ── Review Reports ──────────────────────────────────────────────────────

export interface ReferenceResponse {
  citation_label: string;
  project_paper_id: string;
  title: string;
  authors: string[];
  year: number | null;
  url: string | null;
}

export interface CitationAuditResponse {
  total_citations: number;
  invalid_citations: number;
  valid_citations: number;
  uncited_saved_papers: number;
}

export interface ReportResponse {
  id: string;
  title: string;
  validation_status: string;
  content_markdown: string;
  references: ReferenceResponse[];
  citation_audit: CitationAuditResponse;
}

export interface ReportListResponse {
  items: ReportResponse[];
  total: number;
}

export interface ReportDetailResponse extends ReportResponse {
  created_at: string;
}

export interface CreateReportRequest {
  title?: string;
  include_gap_section?: boolean;
  selected_gap_ids?: string[];
}

// ── Knowledge Graph ──────────────────────────────────────────────────────

export interface GraphNodeResponse {
  id: string;
  label: string;
  full_label?: string | null;
  type: string;
  year?: number | null;
  abstract?: string | null;
  authors?: string | null;
  venue?: string | null;
  url?: string | null;
  project_paper_id?: string | null;
  connections: number;
}

export interface GraphLinkResponse {
  source: string;
  target: string;
  relation: string;
}

export interface GraphStatsResponse {
  paper_count: number;
  method_count: number;
  dataset_count: number;
  limitation_count: number;
  total_edges: number;
}

export interface KnowledgeGraphResponse {
  nodes: GraphNodeResponse[];
  links: GraphLinkResponse[];
  stats: GraphStatsResponse;
}

// ── User / Admin ──────────────────────────────────────────────────────────

export interface UserProfile {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
}

export interface AdminUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

// ── AI Assistant types ──

export type PipelineStep =
  | "create_project"
  | "search_papers"
  | "save_papers"
  | "normalization"
  | "matrix"
  | "gaps"
  | "conflicts"
  | "report";

export type AgentStatus =
  | "idle"
  | "thinking"
  | "running"
  | "needs_confirmation"
  | "stopped"
  | "done"
  | "error";

export interface ChatMessageFE {
  id?: string;
  role: "user" | "assistant" | "system" | "tool_log";
  content: string;
  tool_name?: string | null;
  tool_call_id?: string | null;
  tool_args?: Record<string, unknown> | null;
  tool_summary?: string | null;
  tool_duration_ms?: number | null;
  tool_ok?: boolean | null;
  tool_status?: "running" | "ok" | "error";
  created_at?: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  tool: string;
  args: Record<string, unknown>;
  call_id: string;
}

export interface ToolResultEvent {
  type: "tool_result";
  tool: string;
  call_id: string;
  summary: string;
  duration_ms: number;
  ok: boolean;
}

export interface ProgressEvent {
  type: "progress";
  step: PipelineStep | string;
  status: "pending" | "running" | "done" | "failed";
  percent: number;
  label?: string;
}

export interface MarkdownUpdatedEvent {
  type: "markdown_updated";
  content: string;
  version: number;
  section_changed: number | null;
}

export interface LogEvent {
  type: "log";
  level: "info" | "warn" | "error";
  message: string;
}

export interface AgentChunkEvent {
  type: "agent_chunk";
  delta: string;
  call_id: string;
}

export interface ConnectedEvent {
  type: "connected";
  session_id: string;
  project_id: string | null;
  document_id: string | null;
  resumed: boolean;
}

export interface ProjectCreatedEvent {
  type: "project_created";
  project_id: string;
  document_id: string;
}

export interface DoneEvent {
  type: "done";
  iterations: number;
  total_duration_ms: number;
  reason?: "max_iterations" | "stopped" | "completed";
}

export interface ErrorEvent {
  type: "error";
  message: string;
  code: string;
}

export type AssistantEvent =
  | ConnectedEvent
  | ProjectCreatedEvent
  | ProgressEvent
  | LogEvent
  | ToolCallEvent
  | ToolResultEvent
  | AgentChunkEvent
  | MarkdownUpdatedEvent
  | { type: "agent_message"; content: string; role: "assistant" }
  | DoneEvent
  | ErrorEvent
  | { type: "stopped" }
  | { type: "needs_confirmation"; prompt: string; options: string[]; request_id: string }
  | { type: "markdown_snapshot"; content: string; version: number; title: string }
  | { type: "message_history"; messages: ChatMessageFE[] }
  | { type: "pong" };

export interface ChatDocumentResponse {
  id: string;
  project_id: string;
  title: string;
  content_md: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ChatDocumentListResponse {
  items: ChatDocumentResponse[];
  total: number;
}

export interface ChatDocumentDetailResponse extends ChatDocumentResponse {
  messages: ChatMessageFE[];
}

// ── Sandbox subsystem ───────────────────────────────────────────────────

export type SandboxMode = "docker" | "stub" | "disabled" | string;

export interface SandboxConfigFE {
  mode: SandboxMode;
  enabled: boolean;
  image: string;
  port: number;
  memory_limit: string;
  cpu_limit: number;
  idle_ttl_seconds: number;
  spawn_timeout_seconds: number;
  network: string;
  workspace_root: string;
}

export interface SandboxHandleFE {
  project_id: string;
  mode: string;
  container_id: string | null;
  base_url: string | null;
  workspace: string;
  last_used: number;
  idle_for_seconds: number;
  workspace_bytes: number;
  workspace_files: number;
}

export interface WorkspaceEntryFE {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number | null;
  modified_ts: number;
}

export interface SandboxStatusFE {
  config: SandboxConfigFE;
  handles: SandboxHandleFE[];
  active_projects: number;
  project_id?: string;
  workspace_exists?: boolean;
  files?: WorkspaceEntryFE[];
}

export interface SandboxFileReadFE {
  path: string;
  size_bytes: number;
  truncated: boolean;
  content: string;
}
