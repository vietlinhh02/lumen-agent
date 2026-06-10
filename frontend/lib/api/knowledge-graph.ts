import { apiFetch } from "@/lib/api";
import type { KnowledgeGraphResponse } from "@/lib/types";

export async function fetchKnowledgeGraph(
  projectId: string,
  token: string,
  options?: { nodeTypes?: string[]; minConnections?: number },
): Promise<KnowledgeGraphResponse> {
  const params = new URLSearchParams();
  if (options?.nodeTypes?.length) {
    params.set("node_types", options.nodeTypes.join(","));
  }
  if (options?.minConnections && options.minConnections > 1) {
    params.set("min_connections", String(options.minConnections));
  }
  const qs = params.toString();
  const path = `/projects/${projectId}/knowledge-graph${qs ? `?${qs}` : ""}`;
  return apiFetch<KnowledgeGraphResponse>(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
}
