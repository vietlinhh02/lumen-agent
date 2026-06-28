"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type {
  ProjectListResponse,
  ProjectResponse,
  ProjectCreate,
  ReviewProtocol,
} from "@/lib/types";

export type ProjectFilter = "all" | "active" | "archived";

export interface StatsData {
  project_count: number;
  paper_count: number;
  matrix_count: number;
  gap_count: number;
  report_count: number;
  recent_projects: Array<{
    id: string;
    title: string;
    status: string;
    updated_at: string;
  }>;
  project_workflows?: ProjectWorkflowStatus[];
}

export interface ProjectWorkflowStatus {
  id: string;
  title: string;
  topic: string;
  status: string;
  updated_at: string;
  paper_count: number;
  full_text_count: number;
  raw_text_count: number;
  matrix_count: number;
  gap_count: number;
  conflict_count: number;
  report_count: number;
}

/** How long the cached projects list is considered "fresh" (ms). */
const CACHE_TTL_MS = 30_000;

interface ProjectsState {
  // State
  projects: ProjectResponse[];
  loading: boolean;
  filter: ProjectFilter;
  selectedProjectId: string;
  stats: StatsData | null;
  loadingStats: boolean;
  // Per-project detail cache
  currentProject: ProjectResponse | null;
  loadingProject: boolean;
  currentPapers: import("@/lib/types").ProjectPaperResponse[];
  loadingPapers: boolean;

  // Cache metadata
  lastFetchedAt: number;
  // In-flight promise (for dedup)
  _inflight: Promise<void> | null;

  // Computed
  filteredProjects: () => ProjectResponse[];
  selectedProject: () => ProjectResponse | undefined;

  // Actions
  fetchProjects: (opts?: { force?: boolean }) => Promise<void>;
  fetchStats: (opts?: { force?: boolean }) => Promise<void>;
  setFilter: (f: ProjectFilter) => void;
  setSelectedProjectId: (id: string) => void;
  createProject: (data: ProjectCreate) => Promise<ProjectResponse | null>;
  updateProject: (
    id: string,
    body: Partial<{
      title: string;
      topic: string;
      research_question: string | null;
      status: string;
      review_protocol: ReviewProtocol;
    }>,
  ) => Promise<ProjectResponse | null>;
  deleteProject: (id: string) => Promise<boolean>;
  fetchProject: (id: string) => Promise<void>;
  fetchProjectPapers: (id: string) => Promise<void>;
  reset: () => void;
}

export const useProjectsStore = create<ProjectsState>()((set, get) => ({
  projects: [],
  loading: false,
  filter: "all",
  selectedProjectId: "",
  stats: null,
  loadingStats: false,
  currentProject: null,
  loadingProject: false,
  currentPapers: [],
  loadingPapers: false,

  lastFetchedAt: 0,
  _inflight: null,

  filteredProjects() {
    const { projects, filter } = get();
    if (filter === "all") return projects;
    return projects.filter((p) => p.status === filter);
  },

  selectedProject() {
    const id = get().selectedProjectId;
    if (!id) return undefined;
    return get().projects.find((p) => p.id === id);
  },

  /**
   * Fetch the projects list. Deduplicates concurrent calls and respects
   * a short TTL cache. Pass `{ force: true }` to bypass the cache.
   */
  async fetchProjects(opts) {
    const { force = false } = opts ?? {};
    const token = useAuthStore.getState().token;
    if (!token) return;

    const { lastFetchedAt, _inflight, projects, loading } = get();

    // 1. Re-use in-flight promise if one is already running
    if (_inflight) {
      return _inflight;
    }

    // 2. Use cache if fresh and non-empty
    const isFresh = Date.now() - lastFetchedAt < CACHE_TTL_MS;
    if (!force && !loading && projects.length > 0 && isFresh) {
      return;
    }

    const promise = (async () => {
      set({ loading: true });
      try {
        const data = await apiFetch<ProjectListResponse>("/projects", {
          headers: { Authorization: `Bearer ${token}` },
        });
        set({
          projects: data.projects || [],
          lastFetchedAt: Date.now(),
        });
      } catch {
        // caller handles toast
      } finally {
        set({ loading: false, _inflight: null });
      }
    })();

    set({ _inflight: promise });
    return promise;
  },

  async fetchStats(opts) {
    const { force = false } = opts ?? {};
    const token = useAuthStore.getState().token;
    if (!token) return;

    const { lastFetchedAt, loadingStats, stats } = get();
    // Re-use the same TTL as fetchProjects (CACHE_TTL_MS)
    const isFresh = Date.now() - lastFetchedAt < CACHE_TTL_MS;
    if (!force && !loadingStats && stats !== null && isFresh) {
      return;
    }

    set({ loadingStats: true });
    try {
      const data = await apiFetch<StatsData>(
        "/stats",
        { headers: { Authorization: `Bearer ${token}` } }
      );
      set({ stats: data, lastFetchedAt: Date.now() });
    } catch {
      // ignored – caller toasts
    } finally {
      set({ loadingStats: false });
    }
  },

  setFilter(f) {
    set({ filter: f });
  },

  setSelectedProjectId(id) {
    set({ selectedProjectId: id });
  },

  async createProject(body) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    try {
      const created = await apiFetch<ProjectResponse>("/projects", {
        method: "POST",
        body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${token}` },
      });
      set({
        projects: [created, ...get().projects],
        lastFetchedAt: Date.now(),
      });
      return created;
    } catch {
      return null;
    }
  },

  async updateProject(id, body) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    try {
      const updated = await apiFetch<ProjectResponse>(`/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
        headers: { Authorization: `Bearer ${token}` },
      });
      set({
        projects: get().projects.map((p) => (p.id === id ? updated : p)),
        currentProject:
          get().currentProject?.id === id ? updated : get().currentProject,
      });
      return updated;
    } catch {
      return null;
    }
  },

  async deleteProject(id) {
    const token = useAuthStore.getState().token;
    if (!token) return false;
    try {
      await apiFetch(`/projects/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ projects: get().projects.filter((p) => p.id !== id) });
      return true;
    } catch {
      return false;
    }
  },

  async fetchProject(id) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingProject: true });
    try {
      const result = await apiFetch<ProjectResponse>(`/projects/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ currentProject: result });
    } catch {
      set({ currentProject: null });
    } finally {
      set({ loadingProject: false });
    }
  },

  async fetchProjectPapers(id) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingPapers: true });
    try {
      const data = await apiFetch<
        import("@/lib/types").ProjectPaperResponse[]
      >(`/projects/${id}/papers`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      set({
        currentPapers: Array.isArray(data) ? data : [],
        loadingPapers: false,
      });
    } catch {
      set({ currentPapers: [], loadingPapers: false });
    }
  },

  reset() {
    set({
      projects: [],
      loading: false,
      filter: "all",
      selectedProjectId: "",
      stats: null,
      loadingStats: false,
      currentProject: null,
      loadingProject: false,
      currentPapers: [],
      loadingPapers: false,
      lastFetchedAt: 0,
      _inflight: null,
    });
  },
}));

/**
 * Convenience hook – returns the projects list (loading + refetch helper).
 * NOTE: this hook no longer auto-fetches; pages should call `fetchProjects`
 * explicitly (or rely on the centralized pre-fetch in `AppLayout`).
 */
export function useProjects() {
  const projects = useProjectsStore((s) => s.projects);
  const loading = useProjectsStore((s) => s.loading);
  const fetchProjects = useProjectsStore((s) => s.fetchProjects);
  return { projects, loading, refetch: fetchProjects };
}
