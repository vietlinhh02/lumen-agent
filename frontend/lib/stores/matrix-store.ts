"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import { getExtractionSchema } from "@/lib/api/extraction-schema";
import type {
  ExtractionSchemaResponse,
  MatrixRowResponse,
  MatrixListResponse,
  MatrixEvidenceResponse,
} from "@/lib/types";

interface MatrixState {
  // State
  rows: MatrixRowResponse[];
  schema: ExtractionSchemaResponse | null;
  loading: boolean;
  generating: boolean;
  selectedProjectId: string;
  lowCount: number;

  // Actions
  setSelectedProjectId: (id: string) => void;
  fetchRows: (projectId: string) => Promise<void>;
  fetchSchema: (projectId: string) => Promise<void>;
  fetchLowCount: (projectId: string) => Promise<void>;
  generate: (
    projectId: string,
    onPoll?: (jobId: string, total?: number) => Promise<unknown>,
  ) => Promise<void>;
  editRow: (
    projectId: string,
    rowId: string,
    field: string,
    value: string | number | boolean | string[] | null,
  ) => Promise<MatrixRowResponse | null>;
  deleteRow: (projectId: string, rowId: string) => Promise<boolean>;
  bulkDeleteLow: (projectId: string) => Promise<number>;
  fetchRowEvidence: (
    projectId: string,
    rowId: string,
  ) => Promise<MatrixEvidenceResponse>;
  reset: () => void;
}

export const useMatrixStore = create<MatrixState>()((set, get) => ({
  rows: [],
  schema: null,
  loading: false,
  generating: false,
  selectedProjectId: "",
  lowCount: 0,

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
      set({ rows: data.items || [], schema: data.schema ?? null });
      // Refresh the low-confidence badge in the same pass so the
      // "Remove Low" button shows the right count without an extra round-trip.
      void get().fetchLowCount(projectId);
    } finally {
      set({ loading: false });
    }
  },

  async fetchSchema(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    try {
      const schema = await getExtractionSchema(token, projectId);
      set({ schema });
    } catch {
      // Non-fatal — keep the prior schema on transient errors.
    }
  },

  async fetchLowCount(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return;
    try {
      const data = await apiFetch<{ count: number }>(
        `/projects/${projectId}/matrix:low-count`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      set({ lowCount: data.count });
    } catch {
      // Non-fatal — keep stale count.
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
        await onPoll(result.job_id, result.total);
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
    // For T4 custom fields, merge into custom_fields rather than sending
    // a top-level field. Reserved fields continue to use the top-level
    // patch path so existing edits keep working.
    const isReservedField = [
      "research_problem",
      "method",
      "dataset_or_context",
      "key_result",
      "limitation",
      "contribution",
      "relevance",
      "extraction_confidence",
    ].includes(field);
    const body: Record<string, unknown> = isReservedField
      ? { [field]: value }
      : { custom_fields: { [field]: value } };
    try {
      const updated = await apiFetch<MatrixRowResponse>(
        `/projects/${projectId}/matrix/${rowId}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
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

  async bulkDeleteLow(projectId) {
    const token = useAuthStore.getState().token;
    if (!token) return 0;
    try {
      const data = await apiFetch<{ deleted_count: number }>(
        `/projects/${projectId}/matrix:bulk-delete-low`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        },
      );
      // Refresh both the row list and the low-count badge so the UI stays
      // consistent (some deleted rows may have been re-counted in lowCount).
      await get().fetchRows(projectId);
      return data.deleted_count;
    } catch {
      return 0;
    }
  },

  async fetchRowEvidence(projectId, rowId) {
    const token = useAuthStore.getState().token;
    return await apiFetch<MatrixEvidenceResponse>(
      `/projects/${projectId}/matrix/${rowId}/evidence?limit=5`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
  },

  reset() {
    set({
      rows: [],
      schema: null,
      loading: false,
      generating: false,
      selectedProjectId: "",
      lowCount: 0,
    });
  },
}));
