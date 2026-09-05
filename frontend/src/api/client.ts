export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

let csrfToken = "";

export function setCsrfToken(token: string) {
  csrfToken = token;
}

export function getCsrfToken(): string {
  return csrfToken;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(options.method ?? "GET")) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: "include" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(payload.error?.message ?? "The request failed.", response.status);
  return payload.data as T;
}
