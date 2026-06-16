"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type {
  MatrixRowResponse,
  MatrixListResponse,
} from "@/lib/types";

interface MatrixState {
  // State
  rows: MatrixRowResponse[];
  loading: boolean;
  generating: boolean;
  selectedProjectId: string;

  // Actions
  setSelectedProjectId: (id: string) => void;
  fetchRows: (projectId: string) => Promise<void>;
  generate: (projectId: string, onPoll?: (jobId: string) => Promise<unknown>) => Promise<void>;
  editRow: (
    projectId: string,
    rowId: string,
    field: string,
    value: string,
  ) => Promise<MatrixRowResponse | null>;
  deleteRow: (projectId: string, rowId: string) => Promise<boolean>;
  reset: () => void;
}

export const useMatrixStore = create<MatrixState>()((set, get) => ({
  rows: [],
  loading: false,
  generating: false,
  selectedProjectId: "",

  setSelectedProjectId(id) {
    set({ selectedProjectId: id });
  },

  async fetchRows(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ loading: true });
    try {
      const data = await apiFetch<MatrixListResponse>(
        `/projects/${projectId}/matrix`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ rows: data.items || [] });
    } finally {
      set({ loading: false });
    }
  },

  async generate(projectId, onPoll) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    set({ generating: true });
    try {
      const result = await apiFetch<{ job_id?: string; status?: string; total?: number }>(
        `/projects/${projectId}/matrix:generate`,
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
      // Refresh rows
      await get().fetchRows(projectId);
    } finally {
      set({ generating: false });
    }
  },

  async editRow(projectId, rowId, field, value) {
    const token = useAuthStore.getState().token;
    if (!token) return null;
    try {
      const updated = await apiFetch<MatrixRowResponse>(
        `/projects/${projectId}/matrix/${rowId}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ [field]: value }),
        },
      );
      set({
        rows: get().rows.map((r) => (r.id === rowId ? { ...r, ...updated } : r)),
      });
      return updated;
    } catch {
      return null;
    }
  },

  async deleteRow(projectId, rowId) {
    const token = useAuthStore.getState().token;
    if (!token) return false;
    try {
      await apiFetch(`/projects/${projectId}/matrix/${rowId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ rows: get().rows.filter((r) => r.id !== rowId) });
      return true;
    } catch {
      return false;
    }
  },

  reset() {
    set({ rows: [], loading: false, generating: false, selectedProjectId: "" });
  },
}));
