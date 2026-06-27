/* Frontend API client for the T4 Custom Extraction Schema.
 *
 * Wraps the four REST endpoints exposed by `app.routers.extraction_schema`
 * plus the matrix filter/aggregate endpoints. All calls return a parsed
 * response body; the underlying `apiFetch` raises on HTTP error.
 */

import { apiFetch } from "@/lib/api";
import type {
  ExtractionField,
  ExtractionSchemaResponse,
  ExtractionSchemaSuggestRequest,
  ExtractionSchemaSuggestResponse,
  ExtractionSchemaUpdateRequest,
  MatrixAggregateResponse,
  MatrixFilterRequest,
  MatrixFilterResponse,
} from "@/lib/types";

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function getExtractionSchema(
  token: string,
  projectId: string,
): Promise<ExtractionSchemaResponse> {
  return apiFetch<ExtractionSchemaResponse>(
    `/projects/${projectId}/extraction-schema`,
    { headers: authHeaders(token) },
  );
}

export async function updateExtractionSchema(
  token: string,
  projectId: string,
  fields: ExtractionField[],
): Promise<ExtractionSchemaResponse> {
  const body: ExtractionSchemaUpdateRequest = { fields };
  return apiFetch<ExtractionSchemaResponse>(
    `/projects/${projectId}/extraction-schema`,
    {
      method: "PUT",
      headers: authHeaders(token),
      body: JSON.stringify(body),
    },
  );
}

export async function resetExtractionSchema(
  token: string,
  projectId: string,
): Promise<ExtractionSchemaResponse> {
  return apiFetch<ExtractionSchemaResponse>(
    `/projects/${projectId}/extraction-schema:reset`,
    { method: "POST", headers: authHeaders(token) },
  );
}

export async function suggestExtractionSchema(
  token: string,
  projectId: string,
  req: ExtractionSchemaSuggestRequest = {},
): Promise<ExtractionSchemaSuggestResponse> {
  return apiFetch<ExtractionSchemaSuggestResponse>(
    `/projects/${projectId}/extraction-schema:suggest`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(req),
    },
  );
}

export async function filterMatrix(
  token: string,
  projectId: string,
  req: MatrixFilterRequest,
): Promise<MatrixFilterResponse> {
  return apiFetch<MatrixFilterResponse>(
    `/projects/${projectId}/matrix:filter`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(req),
    },
  );
}

export async function aggregateMatrix(
  token: string,
  projectId: string,
  params: { field: string; group_by?: string | null },
): Promise<MatrixAggregateResponse> {
  const search = new URLSearchParams();
  search.set("field", params.field);
  if (params.group_by) search.set("group_by", params.group_by);
  return apiFetch<MatrixAggregateResponse>(
    `/projects/${projectId}/matrix:aggregate?${search.toString()}`,
    { headers: authHeaders(token) },
  );
}
