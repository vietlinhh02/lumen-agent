export interface ProjectCreate {
  title: string;
  topic: string;
  research_question?: string | null;
  review_protocol?: ReviewProtocol;
}

export interface ReviewProtocol {
  research_questions: string[];
  inclusion_criteria: string[];
  exclusion_criteria: string[];
  population: string | null;
  intervention_or_topic: string | null;
  comparison: string | null;
  outcome: string | null;
  date_range: string | null;
  source_list: string[];
  notes: string | null;
}

export interface ProjectResponse {
  id: string;
  owner_id: string;
  title: string;
  topic: string;
  research_question: string | null;
  review_protocol: ReviewProtocol;
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
  exclusion_reason: string | null;
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
  source_names: string[];
}

// ── Upload Papers (PDF / Markdown) ───────────────────────────────────────

export interface UploadDraftItem {
  filename: string;
  status: "pending" | "rejected" | "duplicate";
  project_paper_id: string | null;
  paper_id: string | null;
  reason: string | null;
}

export interface UploadResponse {
  drafts: UploadDraftItem[];
}

export interface UploadStatusItem {
  project_paper_id: string;
  filename: string;
  full_text_status: string | null;
  title: string;
  authors: Array<{ name: string }>;
  year: number | null;
  venue: string | null;
  abstract: string | null;
}

export interface ConfirmUploadItem {
  project_paper_id: string;
  title: string;
  authors: Array<{ name: string }>;
  year: number | null;
  venue: string | null;
  abstract: string | null;
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
  /**
   * Static metadata flag — true if the paper has any known route to a PDF
   * (arxiv_id or S2 open-access URL). No guarantee the download will
   * actually succeed, but useful for sorting and for the "Download" button
   * affordance.
   */
  can_download?: boolean;
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
  status?: string | null;
  exclusion_reason?: string | null;
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

export interface SuggestQueriesRequest {
  title?: string;
  topic: string;
  research_question?: string;
  review_protocol?: ReviewProtocol;
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
  // T4: project-defined typed field values keyed by schema ``key``.
  custom_fields: Record<string, string | number | boolean | string[] | null>;
  extraction_confidence: string;
  created_by: string;
  updated_at: string | null;
}

export interface MatrixListResponse {
  items: MatrixRowResponse[];
  schema: ExtractionSchemaResponse | null;
}

export interface MatrixRowUpdate {
  research_problem?: string;
  method?: string;
  dataset_or_context?: string;
  key_result?: string;
  limitation?: string;
  contribution?: string;
  relevance?: string;
  custom_fields?: Record<string, string | number | boolean | string[] | null>;
  extraction_confidence?: string;
}

// ── T4: Custom Extraction Schema ──────────────────────────────────────────

export type ExtractionFieldType =
  | "text"
  | "number"
  | "enum"
  | "multi_select"
  | "boolean"
  | "quote"
  | "citation";

export interface ExtractionField {
  key: string;
  label: string;
  type: ExtractionFieldType;
  description: string | null;
  required: boolean;
  enum_values: string[] | null;
}

export interface ExtractionSchemaResponse {
  project_id: string;
  version: number;
  fields: ExtractionField[];
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExtractionSchemaUpdateRequest {
  fields: ExtractionField[];
}

export interface ExtractionSchemaSuggestRequest {
  max_fields?: number;
  sample_abstracts?: string[] | null;
}

export interface ExtractionSchemaSuggestResponse {
  fields: ExtractionField[];
  rationale: string | null;
}

export interface MatrixFilterRequest {
  field: string;
  op: "eq" | "neq" | "contains" | "gt" | "gte" | "lt" | "lte" | "in";
  value: string | number | boolean | string[] | null;
}

export interface MatrixFilterResponse {
  row_ids: string[];
  total: number;
}

export interface MatrixAggregateBucket {
  key: string;
  count: number;
}

export interface MatrixAggregateResponse {
  field: string;
  group_by: string | null;
  buckets: MatrixAggregateBucket[];
  total: number;
}

export interface MatrixGenerateResponse {
  status: string;
  created_count: number;
  skipped_count: number;
}

// ── Evidence (T3 full-text evidence viewer) ────────────────────────────

export interface EvidenceChunk {
  chunk_id: string;
  project_paper_id: string | null;
  chunk_text: string;
  section_label: string | null;
  content_type: string | null;
  page_start: number | null;
  page_end: number | null;
  score: number;
}

// ── Evidence ratings (T3 Phase 3) ──────────────────────────────────────

export type EvidenceSourceKind =
  | "matrix_row"
  | "gap"
  | "conflict"
  | "report_paragraph";

export type EvidenceRatingValue = "accepted" | "weak" | "wrong";

export interface EvidenceRatingCreate {
  source_kind: EvidenceSourceKind;
  source_id: string;
  project_paper_id: string;
  chunk_id: string;
  rating: EvidenceRatingValue;
  note?: string | null;
}

export interface EvidenceRatingResponse {
  id: string;
  source_kind: EvidenceSourceKind;
  source_id: string;
  project_paper_id: string;
  chunk_id: string;
  rating: EvidenceRatingValue;
  note: string | null;
  updated_at: string | null;
}

export interface EvidenceRatingListResponse {
  items: EvidenceRatingResponse[];
}

export interface EvidenceRatingSummary {
  accepted: number;
  weak: number;
  wrong: number;
}

export interface MatrixEvidenceResponse {
  project_paper_id: string;
  paper_title: string | null;
  items: EvidenceChunk[];
}

// Gap evidence reuses the same per-paper shape as the matrix endpoint.
export type EvidenceListResponse = MatrixEvidenceResponse;

export interface ConflictEvidenceResponse {
  paper_a_title: string;
  paper_b_title: string;
  claim_a: EvidenceChunk[];
  claim_b: EvidenceChunk[];
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
// -- T7: Claim and Consensus Synthesis

export interface ClaimEvidenceResponse {
  id: string;
  project_paper_id: string;
  paper_title: string;
  polarity: 'support' | 'contradict' | 'neutral';
  snippet: string | null;
}

export interface ClaimResponse {
  id: string;
  canonical_text: string;
  claim_type: 'support' | 'contradict' | 'mixed' | 'weak';
  support_count: number;
  contradict_count: number;
  neutral_count: number;
  confidence: 'low' | 'medium' | 'high';
  field_origin: string | null;
  source_type: 'matrix' | 'conflict';
  evidence: ClaimEvidenceResponse[];
}

export interface ClaimListResponse {
  items: ClaimResponse[];
  total: number;
}

export interface ClaimAggregateResponse {
  support: number;
  contradict: number;
  mixed: number;
  weak: number;
}



// ── Review Reports ──────────────────────────────────────────────────────

export interface ReferenceResponse {
  citation_label: string;
  project_paper_id: string;
  title: string;
  authors: string[];
  year: number | null;
  url: string | null;
  /** Served PDF URL when a local file exists; null otherwise. */
  pdf_path: string | null;
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
  display_name: string | null;
  role: string;
  is_active: boolean;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
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

// ── PRISMA-style project audit (T2) ─────────────────────────────────────

export interface AuditSourceCount {
  source: string;
  count: number;
}

export interface AuditExclusionReason {
  reason: string;
  label: string;
  count: number;
}

export interface AuditHistogramPoint {
  key: string;
  count: number;
}

export interface AuditTimelinePoint {
  date: string; // ISO date YYYY-MM-DD
  count: number;
}

export interface AuditSearchSessionSummary {
  id: string;
  user_query: string;
  total_results: number;
  screened_count: number;
  high_score_count: number;
  created_at: string;
}

export interface AuditQualityMetrics {
  matrix_avg_confidence: number | null;
  matrix_confidence_breakdown: Record<string, number>;
  full_text_success_rate: number | null;
  full_text_breakdown: Record<string, number>;
  citation_validity_rate: number | null;
  reports_by_validation: Record<string, number>;
}

export interface AuditFieldCoverage {
  key: string;
  label: string;
  type: string;
  is_reserved: boolean;
  required: boolean;
  populated: number;
  rows_total: number;
  coverage_rate: number;
}

export interface AuditExtractionSchema {
  is_default: boolean;
  version: number;
  fields_total: number;
  custom_fields_total: number;
  fields: AuditFieldCoverage[];
}

export interface PrismaAuditResponse {
  project_id: string;
  project_title: string;
  project_topic: string;
  research_question: string | null;
  generated_at: string;
  identified_by_source: AuditSourceCount[];
  records_identified: number;
  duplicates_removed: number;
  records_screened: number;
  records_excluded_screening: number;
  screening_score_distribution: Record<string, number>;
  full_text_assessed: number;
  full_text_not_retrieved: number;
  records_included: number;
  records_uncertain: number;
  records_excluded_final: number;
  exclusion_reasons: AuditExclusionReason[];
  matrix_rows: number;
  reports_generated: number;
  cited_in_reports: number;
  protocol_notes: string | null;
  // ── Enrichment layer ────────────────────────────────────────────────
  year_distribution: AuditHistogramPoint[];
  top_venues: AuditHistogramPoint[];
  year_min: number | null;
  year_max: number | null;
  inclusion_timeline: AuditTimelinePoint[];
  recent_search_sessions: AuditSearchSessionSummary[];
  quality_metrics: AuditQualityMetrics;
  // T4: per-field coverage of the project's effective extraction schema.
  extraction_schema: AuditExtractionSchema | null;
}

// ── Auto search & save ──────────────────────────────────────────────

export interface AutoSearchRequest {
  query?: string; // optional — backend auto-generates from project if blank
  target_count: 25 | 50 | 100;
}

export interface AutoSearchResponse {
  job_id: string;
  session_id: string;
  target_count: number;
  status: "running";
  query?: string;
  query_was_generated?: boolean;
}

export type AutoSearchPhase =
  | "queued"
  | "searching"
  | "scoring"
  | "filtering"
  | "saving"
  | "done"
  | "failed";

export interface AutoSearchProgressJson {
  phase: AutoSearchPhase;
  target_count?: number;
  current_source?: string;
  papers_found?: number;
  batches_completed?: number;
  batches_total?: number;
  papers_scored?: number;
  papers_total?: number;
  kept?: number;
  saved?: number;
  skipped?: number;
  total?: number;
  current_paper?: string;
  /** Number of queries the worker is fanning out (Phase 1) */
  queries_total?: number;
  /** Number of queries the worker has finished searching (Phase 1) */
  queries_done?: number;
  /** Papers that were matched by 2+ queries (robust relevance signal) */
  multi_match_papers?: number;
  percent: number;
  error?: string;
}
