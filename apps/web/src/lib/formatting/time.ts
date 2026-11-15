/** Time formatting helpers. All inputs are epoch milliseconds unless noted. */

export function isValidMs(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/** "Nov 14, 22:18:03" in the viewer's locale. */
export function formatDateTime(ms: number | null | undefined, fallback = "—"): string {
  if (!isValidMs(ms)) return fallback;
  return new Date(ms).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** "22:18:03" in the viewer's locale. */
export function formatClock(ms: number | null | undefined, fallback = "—"): string {
  if (!isValidMs(ms)) return fallback;
  return new Date(ms).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** ISO string for tooltips / audit copy. */
export function formatIso(ms: number | null | undefined, fallback = "—"): string {
  if (!isValidMs(ms)) return fallback;
  return new Date(ms).toISOString();
}

/** "12s ago", "3m ago", "2h ago", "4d ago" — or "in 5m" for future timestamps. */
export function formatRelative(ms: number | null | undefined, now = Date.now(), fallback = "—"): string {
  if (!isValidMs(ms)) return fallback;
  const delta = now - ms;
  const abs = Math.abs(delta);
  const suffix = delta >= 0 ? " ago" : "";
  const prefix = delta < 0 ? "in " : "";
  if (abs < 5_000) return delta >= 0 ? "just now" : "now";
  if (abs < 60_000) return `${prefix}${Math.round(abs / 1000)}s${suffix}`;
  if (abs < 3_600_000) return `${prefix}${Math.round(abs / 60_000)}m${suffix}`;
  if (abs < 86_400_000) return `${prefix}${Math.round(abs / 3_600_000)}h${suffix}`;
  return `${prefix}${Math.round(abs / 86_400_000)}d${suffix}`;
}

/** Human duration from milliseconds: "1h 12m", "45s", "3d 4h". */
export function formatDuration(ms: number | null | undefined, fallback = "—"): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return fallback;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

/** Candle interval label from the Bybit interval code. */
export function intervalLabel(interval: string | null | undefined): string {
  if (!interval) return "—";
  if (interval === "D") return "1D";
  if (interval === "W") return "1W";
  if (interval === "M") return "1M";
  const n = Number(interval);
  if (!Number.isFinite(n)) return interval;
  if (n >= 60 && n % 60 === 0) return `${n / 60}H`;
  return `${n}m`;
}
