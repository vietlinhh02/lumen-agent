"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type {
  GapResponse,
  GapListResponse,
  ConflictResponse,
  ConflictListResponse,
  EvidenceListResponse,
  ConflictEvidenceResponse,
} from "@/lib/types";

type Tab = "gaps" | "conflicts";

interface GapsState {
  // State
  selectedProjectId: string;
  gaps: GapResponse[];
  conflicts: ConflictResponse[];
  loadingGaps: boolean;
  loadingConflicts: boolean;
  generatingGaps: boolean;
  generatingConflicts: boolean;
  expandedGapId: string | null;
  expandedConflictId: string | null;
  activeTab: Tab;

  // Actions
  setSelectedProjectId: (id: string) => void;
  setActiveTab: (t: Tab) => void;
  toggleGapExpand: (id: string) => void;
  toggleConflictExpand: (id: string) => void;
  fetchGaps: (projectId: string) => Promise<void>;
  fetchConflicts: (projectId: string) => Promise<void>;
  generateGaps: (projectId: string, onPoll?: (jobId: string) => Promise<unknown>) => Promise<void>;
  generateConflicts: (projectId: string, onPoll?: (jobId: string) => Promise<unknown>) => Promise<void>;
  deleteGap: (projectId: string, gapId: string) => Promise<boolean>;
  fetchGapEvidence: (
    projectId: string,
    gapId: string,
    projectPaperId: string,
  ) => Promise<EvidenceListResponse>;
  fetchConflictEvidence: (
    projectId: string,
    conflictId: string,
  ) => Promise<ConflictEvidenceResponse>;
  reset: () => void;
}

export const useGapsStore = create<GapsState>()((set, get) => ({
  selectedProjectId: "",
  gaps: [],
  conflicts: [],
  loadingGaps: false,
  loadingConflicts: false,
  generatingGaps: false,
  generatingConflicts: false,
  expandedGapId: null,
  expandedConflictId: null,
  activeTab: "gaps",

  setSelectedProjectId(id) {
    set({ selectedProjectId: id });
  },
  setActiveTab(t) {
    set({ activeTab: t });
  },
  toggleGapExpand(id) {
    set({ expandedGapId: get().expandedGapId === id ? null : id });
  },
  toggleConflictExpand(id) {
    set({
      expandedConflictId: get().expandedConflictId === id ? null : id,
    });
  },

  async fetchGaps(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingGaps: true });
    try {
      const data = await apiFetch<GapListResponse>(
        `/projects/${projectId}/gaps`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ gaps: data.items || [] });
    } catch {
      set({ gaps: [] });
    } finally {
      set({ loadingGaps: false });
    }
  },

  async fetchConflicts(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loadingConflicts: true });
    try {
      const data = await apiFetch<ConflictListResponse>(
        `/projects/${projectId}/conflicts`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ conflicts: data.items || [] });
    } catch {
      set({ conflicts: [] });
    } finally {
      set({ loadingConflicts: false });
    }
  },

  async generateGaps(projectId, onPoll) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ generatingGaps: true });
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number }>(
        `/projects/${projectId}/gaps:generate`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        },
      );
      if (result.job_id && result.status === "running" && onPoll) {
        await onPoll(result.job_id);
      }
      await get().fetchGaps(projectId);
    } finally {
      set({ generatingGaps: false });
    }
  },

  async generateConflicts(projectId, onPoll) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ generatingConflicts: true });
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number }>(
        `/projects/${projectId}/conflicts:generate`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        },
      );
      if (result.job_id && result.status === "running" && onPoll) {
        await onPoll(result.job_id);
      }
      await get().fetchConflicts(projectId);
    } finally {
      set({ generatingConflicts: false });
    }
  },

  async deleteGap(projectId, gapId) {
    const token = useAuthStore.getState().token;
    if (!token) return false;
    try {
      await apiFetch(`/projects/${projectId}/gaps/${gapId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ gaps: get().gaps.filter((g) => g.id !== gapId) });
      return true;
    } catch {
      return false;
    }
  },

  async fetchGapEvidence(projectId, gapId, projectPaperId) {
    const token = useAuthStore.getState().token;
    return await apiFetch<EvidenceListResponse>(
      `/projects/${projectId}/gaps/${gapId}/evidence?project_paper_id=${projectPaperId}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
  },

  async fetchConflictEvidence(projectId, conflictId) {
    const token = useAuthStore.getState().token;
    return await apiFetch<ConflictEvidenceResponse>(
      `/projects/${projectId}/conflicts/${conflictId}/evidence`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
  },

  reset() {
    set({
      selectedProjectId: "",
      gaps: [],
      conflicts: [],
      loadingGaps: false,
      loadingConflicts: false,
      generatingGaps: false,
      generatingConflicts: false,
      expandedGapId: null,
      expandedConflictId: null,
      activeTab: "gaps",
    });
  },
}));
