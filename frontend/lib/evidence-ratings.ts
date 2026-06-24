"use client";

import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth-store";
import type {
  EvidenceRatingCreate,
  EvidenceRatingListResponse,
  EvidenceRatingResponse,
  EvidenceRatingSummary,
  EvidenceSourceKind,
} from "@/lib/types";

function authHeaders(): Record<string, string> {
  const token = useAuthStore.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** This user's ratings for one claim surface — loaded when the drawer opens. */
export async function fetchEvidenceRatings(
  projectId: string,
  sourceKind: EvidenceSourceKind,
  sourceId: string,
): Promise<EvidenceRatingListResponse> {
  return apiFetch<EvidenceRatingListResponse>(
    `/projects/${projectId}/evidence-ratings?source_kind=${sourceKind}&source_id=${sourceId}`,
    { headers: authHeaders() },
  );
}

/** Create or update this user's rating for one chunk. */
export async function upsertEvidenceRating(
  projectId: string,
  body: EvidenceRatingCreate,
): Promise<EvidenceRatingResponse> {
  return apiFetch<EvidenceRatingResponse>(
    `/projects/${projectId}/evidence-ratings`,
    {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    },
  );
}

/** Per-user tally across the project — drives the header chip. */
export async function fetchRatingSummary(
  projectId: string,
): Promise<EvidenceRatingSummary> {
  return apiFetch<EvidenceRatingSummary>(
    `/projects/${projectId}/evidence-ratings/summary`,
    { headers: authHeaders() },
  );
}
