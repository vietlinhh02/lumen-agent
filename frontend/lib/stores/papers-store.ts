"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type { PaperItem, SortKey } from "@/components/papers";

interface PapersState {
  // State
  papers: PaperItem[];
  loading: boolean;
  search: string;
  projectFilter: string;
  sortKey: SortKey;
  sortAsc: boolean;

  // Actions
  fetchPapers: () => Promise<void>;
  setSearch: (s: string) => void;
  setProjectFilter: (id: string) => void;
  toggleSort: (key: SortKey) => void;
  reset: () => void;
}

export const usePapersStore = create<PapersState>()((set, get) => ({
  papers: [],
  loading: false,
  search: "",
  projectFilter: "",
  sortKey: "saved_at",
  sortAsc: false,

  async fetchPapers() {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loading: true });
    try {
      const data = await apiFetch<{ items: PaperItem[]; total: number }>(
        "/papers/all",
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
    set({ search: s });
  },
  setProjectFilter(id) {
    set({ projectFilter: id });
  },
  toggleSort(key) {
    if (get().sortKey === key) {
      set({ sortAsc: !get().sortAsc });
    } else {
      set({ sortKey: key, sortAsc: false });
    }
  },
  reset() {
    set({
      papers: [],
      loading: false,
      search: "",
      projectFilter: "",
      sortKey: "saved_at",
      sortAsc: false,
    });
  },
}));

/** Derived selector: returns papers filtered + sorted according to current state */
export function useFilteredPapers() {
  const papers = usePapersStore((s) => s.papers);
  const search = usePapersStore((s) => s.search);
  const projectFilter = usePapersStore((s) => s.projectFilter);
  const sortKey = usePapersStore((s) => s.sortKey);
  const sortAsc = usePapersStore((s) => s.sortAsc);

  const projects = new Map<string, string>();
  for (const p of papers) projects.set(p.project_id, p.project_title);
  const projectList = Array.from(projects, ([id, title]) => ({ id, title }));

  let result = papers;
  if (projectFilter) {
    result = result.filter((p) => p.project_id === projectFilter);
  }
  if (search.trim()) {
    const q = search.toLowerCase();
    result = result.filter(
      (p) =>
        p.title.toLowerCase().includes(q) ||
        p.authors.some((a) => a.toLowerCase().includes(q)) ||
        (p.venue && p.venue.toLowerCase().includes(q)) ||
        (p.abstract && p.abstract.toLowerCase().includes(q)),
    );
  }
  result = [...result].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "title":
        cmp = a.title.localeCompare(b.title);
        break;
      case "year":
        cmp = (a.year ?? 0) - (b.year ?? 0);
        break;
      case "citations":
        cmp = (a.citation_count ?? 0) - (b.citation_count ?? 0);
        break;
      case "saved_at":
        cmp =
          new Date(a.saved_at).getTime() - new Date(b.saved_at).getTime();
        break;
    }
    return sortAsc ? cmp : -cmp;
  });

  return { filtered: result, projectList };
}
