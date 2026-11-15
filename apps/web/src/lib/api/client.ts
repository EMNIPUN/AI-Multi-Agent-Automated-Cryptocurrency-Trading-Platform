/**
 * Minimal typed fetch helpers for the same-origin Next.js API routes.
 *
 * Every call returns a discriminated `ApiResult` instead of throwing, so pages
 * can render honest unavailable/error states without try/catch noise. The
 * helpers never attach credentials beyond what the caller passes in `init`.
 */

export type ApiError = {
  ok: false;
  status: number;
  /** Stable machine code when the backend supplies one (`detail`), else a synthetic code. */
  code: string;
  /** Human-readable message when provided. */
  message: string;
  /** When the request failed (ms). */
  at: number;
};

export type ApiOk<T> = { ok: true; status: number; data: T; at: number };

export type ApiResult<T> = ApiOk<T> | ApiError;

function extractCode(body: unknown, status: number): { code: string; message: string } {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    const detail = b.detail;
    if (typeof detail === "string") return { code: detail, message: String(b.message ?? detail) };
    if (detail && typeof detail === "object") {
      const d = detail as Record<string, unknown>;
      const code = String(d.error ?? d.code ?? d.detail ?? `http_${status}`);
      return { code, message: String(d.message ?? code) };
    }
    if (typeof b.error === "string") return { code: b.error, message: String(b.message ?? b.error) };
  }
  return { code: status === 0 ? "api_unreachable" : `http_${status}`, message: status === 0 ? "Network error" : `HTTP ${status}` };
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  return requestJson<T>(path, { ...init, method: "GET" });
}

export async function postJson<T>(path: string, body: unknown, init?: RequestInit): Promise<ApiResult<T>> {
  return requestJson<T>(path, {
    ...init,
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    body: JSON.stringify(body ?? {}),
  });
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const at = Date.now();
  try {
    const res = await fetch(path, { cache: "no-store", ...init });
    const body = (await res.json().catch(() => null)) as unknown;
    if (!res.ok) {
      const { code, message } = extractCode(body, res.status);
      return { ok: false, status: res.status, code, message, at };
    }
    // Some operator endpoints answer 200 with an `error` field; surface it as a failure.
    if (body && typeof body === "object" && typeof (body as Record<string, unknown>).error === "string") {
      const b = body as Record<string, unknown>;
      return { ok: false, status: res.status, code: String(b.error), message: String(b.summary ?? b.message ?? b.error), at };
    }
    return { ok: true, status: res.status, data: body as T, at };
  } catch (err) {
    if ((err as Error)?.name === "AbortError") {
      return { ok: false, status: 0, code: "aborted", message: "Request cancelled", at };
    }
    return { ok: false, status: 0, code: "api_unreachable", message: "API unreachable", at };
  }
}

export function isAbort(result: ApiResult<unknown>): boolean {
  return !result.ok && result.code === "aborted";
}
