const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL 
  ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
  : "/api";

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  // For FormData bodies let the browser set the multipart Content-Type (with
  // boundary); forcing application/json would break the upload.
  const isFormData =
    typeof FormData !== "undefined" && init?.body instanceof FormData;
  const headers = isFormData
    ? { ...init?.headers }
    : { "Content-Type": "application/json", ...init?.headers };
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    let message: string;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object" && "message" in detail) {
      message = String(detail.message);
    } else if (Array.isArray(detail)) {
      message = detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    } else {
      message = `Request failed (${res.status})`;
    }
    throw new Error(message);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}
