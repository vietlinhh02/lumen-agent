"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type {
  ReportResponse,
  ReportListResponse,
  ReportDetailResponse,
} from "@/lib/types";

interface ReportsState {
  // State
  selectedProjectId: string;
  reports: ReportResponse[];
  loading: boolean;
  generating: boolean;
  selectedId: string | null;
  detail: ReportDetailResponse | null;
  loadingDetail: boolean;
  searchQuery: string;
  activeSection: string | null;

  // Actions
  setSelectedProjectId: (id: string) => void;
  setSelectedId: (id: string | null) => void;
  setSearchQuery: (q: string) => void;
  setActiveSection: (id: string | null) => void;
  fetchReports: (projectId: string) => Promise<void>;
  fetchDetail: (projectId: string, reportId: string) => Promise<void>;
  generate: (
    projectId: string,
    onPoll?: (jobId: string) => Promise<unknown>,
  ) => Promise<void>;
  exportReport: (projectId: string, reportId: string) => Promise<void>;
  reset: () => void;
}

export const useReportsStore = create<ReportsState>()((set, get) => ({
  selectedProjectId: "",
  reports: [],
  loading: false,
  generating: false,
  selectedId: null,
  detail: null,
  loadingDetail: false,
  searchQuery: "",
  activeSection: null,

  setSelectedProjectId(id) {
    set({ selectedProjectId: id, selectedId: null, detail: null });
  },
  setSelectedId(id) {
    set({ selectedId: id });
  },
  setSearchQuery(q) {
    set({ searchQuery: q });
  },
  setActiveSection(id) {
    set({ activeSection: id });
  },

  async fetchReports(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    // Only clear the current selection if we're switching projects. If the
    // caller is just refreshing the list (e.g. after a successful generate
    // where the user has already been auto-redirected to the new report),
    // we MUST keep the selectedId intact — otherwise the auto-selected
    // report's detail gets wiped out a frame later and the page renders
    // blank.
    const state = get();
    const projectChanged = state.selectedProjectId !== projectId;
    set({
      loading: true,
      ...(projectChanged
        ? { selectedId: null, detail: null }
        : {}),
    });
    try {
      const data = await apiFetch<ReportListResponse>(
        `/projects/${projectId}/reports`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ reports: data.items || [] });
    } catch {
      set({ reports: [] });
    } finally {
      set({ loading: false });
    }
  },

  async fetchDetail(projectId, reportId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingDetail: true, detail: null, activeSection: null, searchQuery: "" });
    try {
      const d = await apiFetch<ReportDetailResponse>(
        `/projects/${projectId}/reports/${reportId}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ detail: d });
    } finally {
      set({ loadingDetail: false });
    }
  },

  async generate(projectId, onPoll) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ generating: true });
    try {
      const result = await apiFetch<{ job_id?: string; status?: string }>(
        `/projects/${projectId}/reports`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ include_gap_section: true }),
        },
      );
      if (result.job_id && result.status === "running" && onPoll) {
        await onPoll(result.job_id);
      }
      await get().fetchReports(projectId);
    } finally {
      set({ generating: false });
    }
  },

  async exportReport(projectId, reportId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    const r = await apiFetch<{ title: string; content: string }>(
      `/projects/${projectId}/reports/${reportId}/export`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const blob = new Blob([r.content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${r.title.replace(/[^a-zA-Z0-9]/g, "_")}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },

  reset() {
    set({
      selectedProjectId: "",
      reports: [],
      loading: false,
      generating: false,
      selectedId: null,
      detail: null,
      loadingDetail: false,
      searchQuery: "",
      activeSection: null,
    });
  },
}));
