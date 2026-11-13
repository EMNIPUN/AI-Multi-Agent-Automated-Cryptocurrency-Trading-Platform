/** Display helpers for 67A analytics — no silent zero/NaN fabrication. */

import type { OptionalMetric, PaperAnalyticsTradeItem } from "@/lib/paper/types";

export function formatUtcMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—";
  return new Date(ms).toISOString().replace("T", " ").replace(".000Z", " UTC");
}

export function formatHoldingDuration(ms: string | number | null | undefined): string {
  if (ms == null || ms === "") return "—";
  const n = typeof ms === "number" ? ms : Number(ms);
  if (!Number.isFinite(n) || n < 0) return "unavailable";
  if (n < 1000) return `${Math.round(n)} ms`;
  const sec = n / 1000;
  if (sec < 60) return `${sec.toFixed(1)} s`;
  const min = sec / 60;
  if (min < 60) return `${min.toFixed(1)} min`;
  const hr = min / 60;
  return `${hr.toFixed(2)} h`;
}

/** Keep decimal strings intact; reject NaN/Infinity tokens. */
export function formatDecimalDisplay(
  value: string | null | undefined,
  options?: { suffix?: string },
): string {
  const suffix = options?.suffix ?? "";
  if (value == null || value === "") return "unavailable";
  const trimmed = value.trim();
  if (!trimmed) return "unavailable";
  const lower = trimmed.toLowerCase();
  if (
    lower === "nan" ||
    lower === "infinity" ||
    lower === "-infinity" ||
    lower === "inf" ||
    lower === "-inf"
  ) {
    return "unavailable";
  }
  return suffix ? `${trimmed} ${suffix}` : trimmed;
}

export function formatOptionalMetric(
  metric: OptionalMetric | null | undefined,
  options?: { suffix?: string; unboundedLabel?: string },
): string {
  const suffix = options?.suffix ?? "";
  const unboundedLabel = options?.unboundedLabel ?? "unbounded";
  if (!metric) return "unavailable";
  const status = String(metric.status || "").toLowerCase();
  if (status === "empty") return "n/a (no closed trades)";
  if (status === "unbounded") return unboundedLabel;
  if (status === "unavailable") {
    return metric.reason ? `unavailable (${metric.reason})` : "unavailable";
  }
  return formatDecimalDisplay(metric.value, { suffix });
}

export function signedMoneyClass(value: string | null | undefined): string {
  if (value == null || value === "") return "text-muted-foreground";
  try {
    const n = Number(value);
    if (!Number.isFinite(n) || n === 0) return "font-mono";
    if (n > 0) return "font-mono text-profit";
    return "font-mono text-loss";
  } catch {
    return "font-mono";
  }
}

export function tradeOutcome(net: string): "win" | "loss" | "breakeven" | "unknown" {
  try {
    const n = Number(net);
    if (!Number.isFinite(n)) return "unknown";
    if (n > 0) return "win";
    if (n < 0) return "loss";
    return "breakeven";
  } catch {
    return "unknown";
  }
}

export function localDateInputToUtcMs(
  dateStr: string,
  options?: { endOfDay?: boolean },
): number | null {
  const endOfDay = options?.endOfDay ?? false;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (!y || mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  if (endOfDay) {
    return Date.UTC(y, mo - 1, d, 23, 59, 59, 999);
  }
  return Date.UTC(y, mo - 1, d, 0, 0, 0, 0);
}

export function validateExitDateRange(
  fromDate: string,
  toDate: string,
): { ok: true; fromMs?: number; toMs?: number } | { ok: false; reason: string } {
  const hasFrom = Boolean(fromDate.trim());
  const hasTo = Boolean(toDate.trim());
  let fromMs: number | undefined;
  let toMs: number | undefined;
  if (hasFrom) {
    const v = localDateInputToUtcMs(fromDate, { endOfDay: false });
    if (v == null) return { ok: false, reason: "invalid_exit_from_date" };
    fromMs = v;
  }
  if (hasTo) {
    const v = localDateInputToUtcMs(toDate, { endOfDay: true });
    if (v == null) return { ok: false, reason: "invalid_exit_to_date" };
    toMs = v;
  }
  if (fromMs != null && toMs != null && fromMs > toMs) {
    return { ok: false, reason: "exit_from_after_exit_to" };
  }
  return { ok: true, fromMs, toMs };
}

export function buildAnalyticsQuery(params: {
  symbol?: string;
  exitFromMs?: number;
  exitToMs?: number;
  limit?: number;
  offset?: number;
  series?: "marked" | "realized_balance";
}): string {
  const qs = new URLSearchParams();
  if (params.symbol && params.symbol !== "ALL") qs.set("symbol", params.symbol);
  if (params.exitFromMs != null) qs.set("exit_from_ms", String(params.exitFromMs));
  if (params.exitToMs != null) qs.set("exit_to_ms", String(params.exitToMs));
  if (params.limit != null) qs.set("limit", String(params.limit));
  if (params.offset != null) qs.set("offset", String(params.offset));
  if (params.series) qs.set("series", params.series);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export function assertNoFixturePayload(payload: unknown): boolean {
  const text = JSON.stringify(payload ?? {}).toLowerCase();
  return !text.includes("sample equity") && !/\bfixture\b/.test(text);
}

export function closedTradeRowKey(t: PaperAnalyticsTradeItem): string {
  return t.position_id;
}
