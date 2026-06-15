import type {
  ChatDocumentDetailResponse,
  ChatDocumentListResponse,
  ChatDocumentResponse,
  SandboxFileReadFE,
  SandboxStatusFE,
} from "@/lib/types";
import { apiFetch } from "@/lib/api";

export async function createDocument(token: string): Promise<ChatDocumentResponse> {
  return apiFetch<ChatDocumentResponse>("/assistant/documents", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ title: "New assistant session" }),
  });
}

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

// ── Sandbox subsystem ──────────────────────────────────────────────────

export async function getSandboxStatus(
  token: string,
  projectId: string | null,
): Promise<SandboxStatusFE> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return apiFetch<SandboxStatusFE>(`/sandbox/status${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function readSandboxFile(
  token: string,
  projectId: string,
  path: string,
  maxBytes = 200_000,
): Promise<SandboxFileReadFE> {
  const qs = new URLSearchParams({
    project_id: projectId,
    path,
    max_bytes: String(maxBytes),
  });
  return apiFetch<SandboxFileReadFE>(`/sandbox/files?${qs.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}
