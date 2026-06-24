"use client";

import { create } from "zustand";
import { fetchRatingSummary } from "@/lib/evidence-ratings";
import type { EvidenceRatingSummary } from "@/lib/types";

interface RatingsState {
  summary: EvidenceRatingSummary | null;
  fetchSummary: (projectId: string) => Promise<void>;
  reset: () => void;
}

/**
 * Project-level tally of this user's evidence ratings, shown as a chip in
 * the project header. Refreshed by the drawer after each rating.
 */
export const useRatingsStore = create<RatingsState>()((set) => ({
  summary: null,

  async fetchSummary(projectId) {
    try {
      const summary = await fetchRatingSummary(projectId);
      set({ summary });
    } catch {
      // Non-fatal — the chip just stays stale/hidden.
    }
  },

  reset() {
    set({ summary: null });
  },
}));
