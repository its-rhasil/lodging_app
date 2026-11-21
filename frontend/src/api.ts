// Thin fetch wrapper. Every request sends the session cookie; errors become ApiError with the
// backend's stable {code, message, details} body.

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(status: number, code: string, message: string, details: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type Query = Record<string, string | number | undefined | null>;

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  let url = BASE + path;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    }
    const text = params.toString();
    if (text) url += "?" + text;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      credentials: "include",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check the connection.", null);
  }

  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const message = data?.message ?? `Request failed (${res.status}).`;
    if (res.status === 401) window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(res.status, data?.code ?? "http_error", message, data?.details ?? null);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

export function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "invalid_request" && Array.isArray(err.details)) {
      const first = err.details[0] as { loc?: string[]; msg?: string } | undefined;
      if (first) return `${(first.loc ?? []).slice(1).join(".")}: ${first.msg}`;
    }
    return err.message;
  }
  return "Something went wrong.";
}
