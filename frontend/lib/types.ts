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
