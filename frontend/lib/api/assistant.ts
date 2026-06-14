import type { ChatDocumentDetailResponse, ChatDocumentListResponse } from "@/lib/types";
import { apiFetch } from "@/lib/api";

export async function listDocuments(token: string): Promise<ChatDocumentListResponse> {
  return apiFetch<ChatDocumentListResponse>("/assistant/documents", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function getDocument(token: string, id: string): Promise<ChatDocumentDetailResponse> {
  return apiFetch<ChatDocumentDetailResponse>(`/assistant/documents/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function exportDocumentUrl(id: string, token: string): string {
  return `/api/assistant/documents/${id}/export?token=${encodeURIComponent(token)}`;
}

export async function deleteDocument(token: string, id: string): Promise<void> {
  await apiFetch<void>(`/assistant/documents/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
}
