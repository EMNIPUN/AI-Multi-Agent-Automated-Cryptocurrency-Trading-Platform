import type {
  BacktestDecisionsResponse,
  BacktestEquityResponse,
  BacktestFetchResult,
  BacktestJobStatus,
  BacktestMetrics,
  BacktestOrdersResponse,
  BacktestRunAccepted,
  BacktestRunCapabilities,
  BacktestRunDetail,
  BacktestRunRequest,
  BacktestRunSummary,
  BacktestStatus,
  BacktestTradesResponse,
} from "@/lib/backtest/types";

function parseErrorPayload(payload: Record<string, unknown>, status: number) {
  const detailObj =
    typeof payload.detail === "object" && payload.detail ? (payload.detail as Record<string, unknown>) : null;
  const detail =
    typeof payload.detail === "string"
      ? payload.detail
      : detailObj && "code" in detailObj
        ? String(detailObj.code || "error")
        : detailObj && "detail" in detailObj
          ? String(detailObj.detail || "error")
          : `http_${status}`;
  const message =
    typeof payload.message === "string"
      ? payload.message
      : detailObj && typeof detailObj.message === "string"
        ? detailObj.message
        : undefined;
  return { detail, message };
}

async function getJson<T>(path: string): Promise<BacktestFetchResult<T>> {
  try {
    const res = await fetch(path, { method: "GET", cache: "no-store" });
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) {
      const { detail, message } = parseErrorPayload(payload, res.status);
      return { ok: false, status: res.status, detail, message };
    }
    return { ok: true, data: payload as T, status: res.status };
  } catch {
    return {
      ok: false,
      status: 0,
      detail: "network_error",
      message: "Network failure talking to backtest proxy",
    };
  }
}

async function postJson<T>(
  path: string,
  body: unknown,
  idempotencyKey?: string,
): Promise<BacktestFetchResult<T>> {
  try {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "Content-Type": "application/json",
    };
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    const res = await fetch(path, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) {
      const { detail, message } = parseErrorPayload(payload, res.status);
      return { ok: false, status: res.status, detail, message };
    }
    return { ok: true, data: payload as T, status: res.status };
  } catch {
    return {
      ok: false,
      status: 0,
      detail: "network_error",
      message: "Network failure talking to backtest proxy",
    };
  }
}

export function resolveBacktestUiMode(status: BacktestStatus | null, errStatus?: number) {
  if (errStatus === 503 || (status && !status.enabled)) return "disabled" as const;
  if (errStatus === 0) return "unreachable" as const;
  if (status && status.enabled && !status.results_dir_exists) return "missing_dir" as const;
  if (status && status.enabled && status.run_count === 0) return "empty" as const;
  return "ready" as const;
}

export async function fetchBacktestStatus() {
  return getJson<BacktestStatus>("/api/backtests/status");
}

export async function fetchBacktestRuns(limit = 50, offset = 0) {
  return getJson<{ items: BacktestRunSummary[]; total: number; limit: number; offset: number }>(
    `/api/backtests/runs?limit=${limit}&offset=${offset}`,
  );
}

export async function fetchBacktestRun(runId: string) {
  return getJson<BacktestRunDetail>(`/api/backtests/runs/${encodeURIComponent(runId)}`);
}

export async function fetchBacktestMetrics(runId: string) {
  return getJson<BacktestMetrics>(`/api/backtests/runs/${encodeURIComponent(runId)}/metrics`);
}

export async function fetchBacktestTrades(runId: string, limit = 25, offset = 0) {
  return getJson<BacktestTradesResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/trades?limit=${limit}&offset=${offset}`,
  );
}

export async function fetchBacktestEquity(runId: string) {
  return getJson<BacktestEquityResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/equity`,
  );
}

export async function fetchBacktestDecisions(runId: string, limit = 25, offset = 0) {
  return getJson<BacktestDecisionsResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/decisions?limit=${limit}&offset=${offset}`,
  );
}

export async function fetchBacktestOrders(runId: string, limit = 50, offset = 0) {
  return getJson<BacktestOrdersResponse>(
    `/api/backtests/runs/${encodeURIComponent(runId)}/orders?limit=${limit}&offset=${offset}`,
  );
}

export async function fetchBacktestRunCapabilities() {
  return getJson<BacktestRunCapabilities>("/api/backtests/run-capabilities");
}

export async function submitBacktestRun(body: BacktestRunRequest, idempotencyKey?: string) {
  return postJson<BacktestRunAccepted>("/api/backtests/runs", body, idempotencyKey);
}

export async function fetchBacktestJobStatus(jobId: string) {
  return getJson<BacktestJobStatus>(`/api/backtests/jobs/${encodeURIComponent(jobId)}`);
}

/** Estimate confirmed bars in [start, end] for minute intervals (no network). */
export function estimateCandleCount(startMs: number, endMs: number, interval: string): number {
  const minutes = Number(interval);
  if (!Number.isFinite(minutes) || minutes <= 0) return 0;
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return 0;
  const step = minutes * 60_000;
  return Math.max(0, Math.floor((endMs - startMs) / step) + 1);
}
