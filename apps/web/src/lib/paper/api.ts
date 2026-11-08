import { buildAnalyticsQuery } from "@/lib/paper/analytics-format";
import type {
  PaperAccount,
  PaperAnalyticsEquityResponse,
  PaperAnalyticsResponse,
  PaperAnalyticsSymbolsResponse,
  PaperAnalyticsTradesResponse,
  PaperOrder,
  PaperPosition,
  PaperSessionSummary,
  PaperSignalLink,
  PaperStatus,
} from "@/lib/paper/types";

async function getJson<T>(path: string): Promise<{ ok: true; data: T } | { ok: false; status: number; detail: string }> {
  try {
    const res = await fetch(path, { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof data?.detail === "string"
          ? data.detail
          : typeof data?.message === "string"
            ? data.message
            : data?.detail?.detail || `http_${res.status}`;
      return { ok: false, status: res.status, detail: String(detail) };
    }
    return { ok: true, data: data as T };
  } catch {
    return { ok: false, status: 503, detail: "api_unreachable" };
  }
}

export function fetchPaperStatus() {
  return getJson<PaperStatus>("/api/paper/status");
}

export function fetchPaperSessions() {
  return getJson<{ items: PaperSessionSummary[]; total: number }>("/api/paper/sessions");
}

export function fetchPaperAccount(sessionId: string) {
  return getJson<PaperAccount>(`/api/paper/sessions/${encodeURIComponent(sessionId)}/account`);
}

export function fetchPaperPositions(
  sessionId: string,
  params: { status?: string; symbol?: string } = {},
) {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.symbol) qs.set("symbol", params.symbol);
  const suffix = qs.toString() ? `?${qs}` : "";
  return getJson<{ items: PaperPosition[] }>(
    `/api/paper/sessions/${encodeURIComponent(sessionId)}/positions${suffix}`,
  );
}

export function fetchPaperOrders(
  sessionId: string,
  params: { symbol?: string; status?: string } = {},
) {
  const qs = new URLSearchParams();
  if (params.symbol) qs.set("symbol", params.symbol);
  if (params.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs}` : "";
  return getJson<{ items: PaperOrder[] }>(
    `/api/paper/sessions/${encodeURIComponent(sessionId)}/orders${suffix}`,
  );
}

export function fetchPaperSignalLink(signalId: string) {
  return getJson<PaperSignalLink>(
    `/api/paper/orders/by-signal/${encodeURIComponent(signalId)}`,
  );
}

export type AnalyticsFilterParams = {
  symbol?: string;
  exitFromMs?: number;
  exitToMs?: number;
};

export function fetchPaperAnalytics(
  sessionId: string,
  params: AnalyticsFilterParams = {},
) {
  const q = buildAnalyticsQuery({
    symbol: params.symbol,
    exitFromMs: params.exitFromMs,
    exitToMs: params.exitToMs,
  });
  return getJson<PaperAnalyticsResponse>(
    `/api/paper/sessions/${encodeURIComponent(sessionId)}/analytics${q}`,
  );
}

export function fetchPaperAnalyticsTrades(
  sessionId: string,
  params: AnalyticsFilterParams & { limit?: number; offset?: number } = {},
) {
  const q = buildAnalyticsQuery({
    symbol: params.symbol,
    exitFromMs: params.exitFromMs,
    exitToMs: params.exitToMs,
    limit: params.limit ?? 50,
    offset: params.offset ?? 0,
  });
  return getJson<PaperAnalyticsTradesResponse>(
    `/api/paper/sessions/${encodeURIComponent(sessionId)}/analytics/trades${q}`,
  );
}

export function fetchPaperAnalyticsEquity(
  sessionId: string,
  series: "marked" | "realized_balance" = "marked",
) {
  const q = buildAnalyticsQuery({ series });
  return getJson<PaperAnalyticsEquityResponse>(
    `/api/paper/sessions/${encodeURIComponent(sessionId)}/analytics/equity${q}`,
  );
}

export function fetchPaperAnalyticsSymbols(
  sessionId: string,
  params: Omit<AnalyticsFilterParams, "symbol"> = {},
) {
  const q = buildAnalyticsQuery({
    exitFromMs: params.exitFromMs,
    exitToMs: params.exitToMs,
  });
  return getJson<PaperAnalyticsSymbolsResponse>(
    `/api/paper/sessions/${encodeURIComponent(sessionId)}/analytics/symbols${q}`,
  );
}

/** Pure helpers for UI state (unit-tested). */
export type PaperUiMode =
  | "loading"
  | "disabled"
  | "unavailable"
  | "no_sessions"
  | "ready"
  | "unsupported_futures"
  | "error";

export function resolvePaperUiMode(input: {
  loading: boolean;
  category: "spot" | "linear" | "inverse" | string;
  statusOk: boolean;
  enabled: boolean;
  apiError: boolean;
  sessionCount: number;
}): PaperUiMode {
  if (input.loading) return "loading";
  if (input.category !== "spot") return "unsupported_futures";
  if (input.apiError) return "unavailable";
  if (!input.statusOk) return "error";
  if (!input.enabled) return "disabled";
  if (input.sessionCount <= 0) return "no_sessions";
  return "ready";
}

export function isSampleMetricLabel(text: string): boolean {
  return /\bSAMPLE\b/i.test(text);
}
