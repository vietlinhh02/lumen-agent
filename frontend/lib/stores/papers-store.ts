"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import { useProjectsStore } from "./projects-store";
import type { PaperItem, SortKey } from "@/components/papers";

interface PapersState {
  // State
  papers: PaperItem[];
  loading: boolean;
  search: string;
  projectFilter: string;
  sortKey: SortKey;
  sortAsc: boolean;
  page: number;

  // Actions
  fetchPapers: () => Promise<void>;
  setSearch: (s: string) => void;
  setProjectFilter: (id: string) => void;
  toggleSort: (key: SortKey) => void;
  setPage: (p: number) => void;
  reset: () => void;
}

export const usePapersStore = create<PapersState>()((set, get) => ({
  papers: [],
  loading: false,
  search: "",
  projectFilter: "",
  sortKey: "saved_at",
  sortAsc: false,
  page: 1,

  async fetchPapers() {
    const state = get();
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loading: true });

    const limit = 50;
    const offset = (state.page - 1) * limit;

    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString(),
      sort_key: state.sortKey,
      sort_asc: String(state.sortAsc),
    });
    
    if (state.search.trim()) params.append("search", state.search.trim());
    if (state.projectFilter) params.append("project_id", state.projectFilter);

    try {
      const data = await apiFetch<{ items: PaperItem[]; total: number }>(
        `/papers/all?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ papers: data.items || [] });
    } catch {
      // caller toasts
    } finally {
      set({ loading: false });
    }
  },

  setSearch(s) {
    set({ search: s, page: 1 });
    // setTimeout acts as a simple debounce for typing
    setTimeout(() => {
      if (get().search === s) get().fetchPapers();
    }, 300);
  },
  setProjectFilter(id) {
    set({ projectFilter: id, page: 1 });
    void get().fetchPapers();
  },
  toggleSort(key) {
    if (get().sortKey === key) {
      set({ sortAsc: !get().sortAsc });
    } else {
      set({ sortKey: key, sortAsc: false });
    }
    set({ page: 1 });
    void get().fetchPapers();
  },
  setPage(p) {
    set({ page: p });
    void get().fetchPapers();
  },
  reset() {
    set({
      papers: [],
      loading: false,
      search: "",
      projectFilter: "",
      sortKey: "saved_at",
      sortAsc: false,
      page: 1,
    });
  },
}));

/** Derived selector: returns papers filtered + sorted according to current state */
export function useFilteredPapers() {
  const papers = usePapersStore((s) => s.papers);
  
  // Use projects from useProjectsStore for the dropdown so it's not limited by pagination
  const projects = useProjectsStore((s) => s.projects);
  const projectList = projects.map(p => ({ id: p.id, title: p.title }));

  // Backend does the filtering, so we just return the raw fetched papers
  return { filtered: papers, projectList };
}
