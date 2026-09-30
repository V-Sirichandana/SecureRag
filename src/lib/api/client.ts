const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const USE_MOCKS = (process.env.NEXT_PUBLIC_USE_MOCKS ?? "true") !== "false";

export class ApiError extends Error {
  readonly status: number;
  readonly details?: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

/**
 * Thin fetch wrapper. The browser always sends the ambient session cookie /
 * bearer token — the frontend never transmits tenant or role information of
 * its own accord; the backend derives it from the authenticated principal.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, headers = {} } = options;

  const response = await fetch(`${API_URL}${path}`, {
    method,
    signal,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "include",
  });

  if (!response.ok) {
    let details: unknown;
    try {
      details = await response.json();
    } catch {
      details = await response.text();
    }
    const message =
      typeof details === "object" && details !== null && "detail" in details
        ? String((details as { detail: unknown }).detail)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
