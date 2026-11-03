const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "true";

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

const AUTH_STORAGE_KEY = "securerag-auth";

/**
 * Session expiry: a 401 from any non-auth endpoint means the backend no longer
 * recognises the session cookie. Drop the locally persisted session and send
 * the user back to /login so the app never keeps showing authenticated UI
 * against an expired server session.
 */
function handleUnauthorized(path: string): void {
  if (typeof window === "undefined") return;
  if (path.startsWith("/auth/")) return; // credential errors are not expiry
  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    // storage unavailable — the redirect below is still enough
  }
  if (!window.location.pathname.startsWith("/login")) {
    window.location.replace("/login");
  }
}

function messageFromDetails(details: unknown, status: number): string {
  if (typeof details === "object" && details !== null && "detail" in details) {
    return String((details as { detail: unknown }).detail);
  }
  return `Request failed with status ${status}`;
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
    if (response.status === 401) handleUnauthorized(path);
    throw new ApiError(messageFromDetails(details, response.status), response.status, details);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export interface UploadRequestOptions {
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

/**
 * Multipart upload with real byte progress (XHR — `fetch` cannot report upload
 * progress). Sends the ambient session cookie exactly like `request`, surfaces
 * the backend's `detail` message on failure, and honours AbortSignal for
 * per-file cancel.
 */
export function uploadRequest<T>(
  path: string,
  formData: FormData,
  options: UploadRequestOptions = {},
): Promise<T> {
  const { onProgress, signal } = options;

  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const xhr = new XMLHttpRequest();
    const onAbort = () => xhr.abort();

    const settleAbort = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };

    xhr.open("POST", `${API_URL}${path}`, true);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable && event.total > 0) {
        onProgress(event.loaded / event.total);
      }
    };

    xhr.onload = () => {
      signal?.removeEventListener("abort", onAbort);
      let details: unknown;
      try {
        details = JSON.parse(xhr.responseText);
      } catch {
        details = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(details as T);
        return;
      }
      if (xhr.status === 401) handleUnauthorized(path);
      reject(new ApiError(messageFromDetails(details, xhr.status), xhr.status, details));
    };

    xhr.onerror = () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new ApiError("The upload could not reach the server.", 0));
    };

    xhr.onabort = settleAbort;

    signal?.addEventListener("abort", onAbort);
    xhr.send(formData);
  });
}
