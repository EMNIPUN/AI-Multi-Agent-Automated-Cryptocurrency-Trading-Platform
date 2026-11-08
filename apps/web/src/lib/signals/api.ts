import type { SignalEvaluateResponse, SignalHistoryItem } from "@/lib/signals/types";

export async function fetchSignalStatus(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/signals/status", { cache: "no-store" });
  if (!res.ok) throw new Error(`signals_status_${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function fetchPublicSignalEvaluate(opts: {
  symbol: string;
  category: string;
  interval: string;
}): Promise<SignalEvaluateResponse> {
  const qs = new URLSearchParams({
    symbol: opts.symbol,
    category: opts.category,
    interval: opts.interval,
  });
  const res = await fetch(`/api/signals/evaluate?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`signals_evaluate_${res.status}`);
  return (await res.json()) as SignalEvaluateResponse;
}

export async function fetchSignalHistory(opts?: {
  symbol?: string;
  interval?: string;
  action?: string;
  limit?: number;
}): Promise<{ items: SignalHistoryItem[] }> {
  const qs = new URLSearchParams();
  if (opts?.symbol) qs.set("symbol", opts.symbol);
  if (opts?.interval) qs.set("interval", opts.interval);
  if (opts?.action) qs.set("action", opts.action);
  qs.set("limit", String(opts?.limit ?? 40));
  const res = await fetch(`/api/signals/history?${qs}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`signals_history_${res.status}`);
  return (await res.json()) as { items: SignalHistoryItem[] };
}

export async function fetchSignalAnalytics(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/signals/analytics", { cache: "no-store" });
  if (!res.ok) throw new Error(`signals_analytics_${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function fetchAutoEngineStatus(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/signals/engine/status", { cache: "no-store" });
  if (!res.ok) throw new Error(`signals_engine_status_${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function startAutoEngine(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/signals/engine/start", {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`signals_engine_start_${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function stopAutoEngine(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/signals/engine/stop", {
    method: "POST",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`signals_engine_stop_${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

export async function fetchSignalSyncStatus(): Promise<Record<string, unknown>> {
  const res = await fetch("/api/signals/sync/status", { cache: "no-store" });
  if (!res.ok) throw new Error(`signals_sync_status_${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}
