"use client";

import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "./auth-store";
import type {
    ClaimResponse,
    ClaimListResponse,
    ClaimAggregateResponse,
} from "@/lib/types";

interface ClaimsState {
    // State
    claims: ClaimResponse[];
    aggregate: ClaimAggregateResponse | null;
    loadingClaims: boolean;
    generatingClaims: boolean;
    expandedClaimId: string | null;

    // Actions
    fetchClaims: (projectId: string, claimType?: string) => Promise<void>;
    fetchAggregate: (projectId: string) => Promise<void>;
    generateClaims: (
        projectId: string,
        onPoll?: (jobId: string) => Promise<unknown>
    ) => Promise<void>;
    toggleExpand: (id: string) => void;
    reset: () => void;
}

const INITIAL: Pick<
    ClaimsState,
    "claims" | "aggregate" | "loadingClaims" | "generatingClaims" | "expandedClaimId"
> = {
    claims: [],
    aggregate: null,
    loadingClaims: false,
    generatingClaims: false,
    expandedClaimId: null,
};

export const useClaimsStore = create<ClaimsState>()((set, get) => ({
    ...INITIAL,

    async fetchClaims(projectId, claimType) {
        const token = useAuthStore.getState().token;
        if (!token) return;
        set({ loadingClaims: true });
        try {
            const qs = claimType ? `?claim_type=${claimType}` : "";
            const data = await apiFetch<ClaimListResponse>(
                `/projects/${projectId}/claims${qs}`,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            set({ claims: data.items ?? [] });
        } catch {
            set({ claims: [] });
        } finally {
            set({ loadingClaims: false });
        }
    },

    async fetchAggregate(projectId) {
        const token = useAuthStore.getState().token;
        if (!token) return;
        try {
            const data = await apiFetch<ClaimAggregateResponse>(
                `/projects/${projectId}/claims:aggregate`,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            set({ aggregate: data });
        } catch {
            set({ aggregate: null });
        }
    },

    async generateClaims(projectId, onPoll) {
        const token = useAuthStore.getState().token;
        if (!token) return;
        set({ generatingClaims: true });
        try {
            const result = await apiFetch<{ job_id?: string; status?: string }>(
                `/projects/${projectId}/claims:generate`,
                {
                    method: "POST",
                    headers: {
                        Authorization: `Bearer ${token}`,
                        "Content-Type": "application/json",
                    },
                }
            );
            if (result.job_id && result.status === "running" && onPoll) {
                await onPoll(result.job_id);
            }
            await get().fetchClaims(projectId);
            await get().fetchAggregate(projectId);
        } finally {
            set({ generatingClaims: false });
        }
    },

    toggleExpand(id) {
        set({ expandedClaimId: get().expandedClaimId === id ? null : id });
    },

    reset() {
        set({ ...INITIAL });
    },
}));
