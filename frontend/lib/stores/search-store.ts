"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import { useProjectsStore } from "./projects-store";
import type {
  PaperResult,
  SavePaperRequest,
  SavePaperResponse,
  SuggestQueriesRequest,
  SuggestQueriesResponse,
  SessionListResponse,
  SessionDetailResponse,
  SessionListItem,
} from "@/lib/types";

interface SearchState {
  // State
  query: string;
  loading: boolean;
  pageLoading: boolean;
  savingId: string | null;
  selectedProjectId: string | null;
  sessionId: string | null;
  sessionData: SessionDetailResponse | null;
  page: number;
  screening: boolean;
  autoSaving: boolean;
  sessions: SessionListItem[];
  suggestedQueries: string[];
  suggestingLabels: boolean;
  savedIds: Set<string>;
  rejectedIds: Set<string>;

  // Actions
  setQuery: (q: string) => void;
  setSelectedProjectId: (id: string | null) => void;
  setSessionId: (id: string | null) => void;
  setSessionData: (d: SessionDetailResponse | null) => void;
  setPage: (p: number) => void;

  loadSession: (sid: string, p: number) => Promise<void>;
  loadPage: (p: number) => Promise<void>;
  search: (q?: string) => Promise<void>;
  startSearch: (q?: string) => Promise<{ job_id: string; session_id: string; status: string } | null>;
  loadSessions: () => Promise<void>;
  suggestQueries: (params: {
    title: string;
    topic: string;
    research_question: string;
  }) => Promise<void>;
  screen: () => Promise<void>;
  autoSave: (onPoll: (jobId: string) => Promise<unknown>) => Promise<void>;
  savePaper: (
    paper: PaperResult,
    projectId: string,
  ) => Promise<SavePaperResponse | null>;
  rejectPaper: (
    paper: PaperResult,
    projectId: string,
    exclusionReason: string,
  ) => Promise<SavePaperResponse | null>;
  unsavePaper: (paper: PaperResult) => Promise<boolean>;

  isSaved: (paper: PaperResult) => boolean;
  isRejected: (paper: PaperResult) => boolean;
  reset: () => void;
}

function paperKey(paper: PaperResult) {
  return paper.semantic_scholar_id || paper.doi || paper.arxiv_id || paper.title;
}

const initialState = {
  query: "",
  loading: false,
  pageLoading: false,
  savingId: null as string | null,
  selectedProjectId: null as string | null,
  sessionId: null as string | null,
  sessionData: null as SessionDetailResponse | null,
  page: 1,
  screening: false,
  autoSaving: false,
  sessions: [] as SessionListItem[],
  suggestedQueries: [] as string[],
  suggestingLabels: false,
  savedIds: new Set<string>(),
  rejectedIds: new Set<string>(),
};

export const useSearchStore = create<SearchState>()((set, get) => ({
  ...initialState,

  setQuery(q) {
    set({ query: q });
  },
  setSelectedProjectId(id) {
    set({ selectedProjectId: id });
  },
  setSessionId(id) {
    set({ sessionId: id });
  },
  setSessionData(d) {
    set({ sessionData: d });
    if (d?.saved_paper_ids) {
      set({ savedIds: new Set(d.saved_paper_ids) });
    }
  },
  setPage(p) {
    set({ page: p });
  },

  async loadSession(sid, p) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loading: true, sessionId: sid, page: p });
    try {
      const data = await apiFetch<SessionDetailResponse>(
        `/papers/search/sessions/${sid}?page=${p}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({
        sessionData: data,
        savedIds: new Set(data.saved_paper_ids || []),
        rejectedIds: new Set(),
      });
    } finally {
      set({ loading: false });
    }
  },

  async loadPage(p) {
    const { sessionId } = get();
    const token = useAuthStore.getState().token;
    if (!token || !sessionId) return;
    set({ pageLoading: true, page: p });
    try {
      const data = await apiFetch<SessionDetailResponse>(
        `/papers/search/sessions/${sessionId}?page=${p}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ sessionData: data });
    } finally {
      set({ pageLoading: false });
    }
  },

  async startSearch(q) {
    const { query, selectedProjectId, setQuery } = get();
    const token = useAuthStore.getState().token;
    const qs = (q ?? query).trim();
    if (!qs || !selectedProjectId || !token) return null;
    if (q) setQuery(q);

    set({
      loading: true,
      sessionId: null,
        sessionData: null,
        page: 1,
        savedIds: new Set(),
        rejectedIds: new Set(),
      });

    try {
      const data = await apiFetch<{ job_id: string; session_id: string; status: string }>(
        "/papers/search/sessions",
        {
          method: "POST",
          body: JSON.stringify({
            project_id: selectedProjectId,
            query: qs,
            limit: 100,
          }),
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      set({ sessionId: data.session_id });
      return data;
    } catch (err) {
      set({ loading: false });
      throw err;
    }
  },

  async search(q) {
    // Convenience wrapper that calls startSearch and persists to URL
    const data = await get().startSearch(q);
    if (data && typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("session", data.session_id);
      url.searchParams.set("page", "1");
      window.history.pushState({}, "", url.toString());
    }
  },

  async loadSessions() {
    const { selectedProjectId } = get();
    const token = useAuthStore.getState().token;
    if (!selectedProjectId || !token) return;
    try {
      const data = await apiFetch<SessionListResponse>(
        `/papers/search/sessions?project_id=${selectedProjectId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ sessions: data.sessions });
    } catch {
      // silent
    }
  },

  async suggestQueries({ title, topic, research_question }) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    // Lấy review_protocol của project đang chọn để LLM anchor gợi ý query
    const projectId = useProjectsStore.getState().selectedProjectId;
    const currentProject = useProjectsStore
      .getState()
      .projects.find((p) => p.id === projectId);
    const reviewProtocol = currentProject?.review_protocol;

    set({ suggestingLabels: true });
    try {
      const body: SuggestQueriesRequest = {
        title,
        topic,
        research_question,
        review_protocol: reviewProtocol,
      };
      const data = await apiFetch<SuggestQueriesResponse>("/papers/suggest-queries", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ suggestedQueries: data.queries });
    } finally {
      set({ suggestingLabels: false });
    }
  },

  async screen() {
    const { sessionId } = get();
    const token = useAuthStore.getState().token;
    if (!token || !sessionId) return;
    set({ screening: true });
    try {
      const data = await apiFetch<{ scores: string[] }>(
        `/papers/search/sessions/${sessionId}/screen`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      set((s) =>
        s.sessionData
          ? { sessionData: { ...s.sessionData, screening_scores: data.scores } }
          : s,
      );
    } finally {
      set({ screening: false });
    }
  },

  async autoSave(onPoll) {
    const { sessionId, page } = get();
    const token = useAuthStore.getState().token;
    if (!token || !sessionId) return;
    set({ autoSaving: true });
    try {
      const data = await apiFetch<{ job_id?: string; status?: string; total?: number; saved?: number }>(
        `/papers/search/sessions/${sessionId}/auto-save`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } },
      );
      if (data.job_id && data.status === "running" && onPoll) {
        await onPoll(data.job_id);
      }
      // refresh session
      const fresh = await apiFetch<SessionDetailResponse>(
        `/papers/search/sessions/${sessionId}?page=${page}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ sessionData: fresh, savedIds: new Set(fresh.saved_paper_ids || []) });
    } finally {
      set({ autoSaving: false });
    }
  },

  async savePaper(paper, projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    const key = paperKey(paper);
    set({ savingId: key });
    try {
      const body: SavePaperRequest = {
        paper_title: paper.title,
        paper_abstract: paper.abstract,
        paper_year: paper.year,
        paper_venue: paper.venue,
        paper_doi: paper.doi,
        paper_arxiv_id: paper.arxiv_id,
        paper_semantic_scholar_id: paper.semantic_scholar_id,
        paper_url: paper.url,
        paper_citation_count: paper.citation_count,
        paper_authors: paper.authors.map((a) => ({
          name: a.name,
          author_id: a.author_id ?? "",
        })),
        paper_source_names:
          paper.source_names.length > 0 ? paper.source_names : ["paperhub"],
        download_pdf: true,
        source_specific: paper.source_specific,
      };
      const result = await apiFetch<SavePaperResponse>(
        `/projects/${projectId}/papers`,
        {
          method: "POST",
          body: JSON.stringify(body),
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      set((s) => {
        const next = new Set(s.savedIds);
        next.add(key);
        const rejected = new Set(s.rejectedIds);
        rejected.delete(key);
        return { savedIds: next, rejectedIds: rejected };
      });
      return result;
    } catch {
      return null;
    } finally {
      set({ savingId: null });
    }
  },

  async rejectPaper(paper, projectId, exclusionReason) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    const key = paperKey(paper);
    set({ savingId: key });
    try {
      const body: SavePaperRequest = {
        paper_title: paper.title,
        paper_abstract: paper.abstract,
        paper_year: paper.year,
        paper_venue: paper.venue,
        paper_doi: paper.doi,
        paper_arxiv_id: paper.arxiv_id,
        paper_semantic_scholar_id: paper.semantic_scholar_id,
        paper_url: paper.url,
        paper_citation_count: paper.citation_count,
        paper_authors: paper.authors.map((a) => ({
          name: a.name,
          author_id: a.author_id ?? "",
        })),
        paper_source_names:
          paper.source_names.length > 0 ? paper.source_names : ["paperhub"],
        source_specific: paper.source_specific,
        status: "rejected",
        exclusion_reason: exclusionReason,
      };
      const result = await apiFetch<SavePaperResponse>(
        `/projects/${projectId}/papers`,
        {
          method: "POST",
          body: JSON.stringify(body),
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      set((s) => {
        const rejected = new Set(s.rejectedIds);
        rejected.add(key);
        const saved = new Set(s.savedIds);
        saved.delete(key);
        return { rejectedIds: rejected, savedIds: saved };
      });
      return result;
    } catch {
      return null;
    } finally {
      set({ savingId: null });
    }
  },

  async unsavePaper(paper) {
    const { sessionId } = get();
    const token = useAuthStore.getState().token;
    if (!token || !sessionId) return false;
    const key = paperKey(paper);
    set({ savingId: key });
    try {
      await apiFetch(`/papers/search/sessions/${sessionId}/unsave`, {
        method: "DELETE",
        body: JSON.stringify({
          semantic_scholar_id: paper.semantic_scholar_id,
          doi: paper.doi,
          arxiv_id: paper.arxiv_id,
        }),
        headers: { Authorization: `Bearer ${token}` },
      });
      set((s) => {
        const next = new Set(s.savedIds);
        next.delete(key);
        return { savedIds: next };
      });
      return true;
    } catch {
      return false;
    } finally {
      set({ savingId: null });
    }
  },

  isSaved(paper) {
    const key = paperKey(paper);
    return get().savedIds.has(key);
  },

  isRejected(paper) {
    const key = paperKey(paper);
    return get().rejectedIds.has(key);
  },

  reset() {
    set({ ...initialState, savedIds: new Set(), rejectedIds: new Set() });
  },
}));
