export const NEWS_ADVISORY_LABEL = "News Advisory Only — Trading Decisions Unchanged";

export type NewsViewState = "loading" | "disabled" | "error" | "empty" | "stale" | "ready";

export type NewsFilters = {
  symbol: string;
  severity: string;
  category: string;
  verification: string;
  fromMs: number | null;
  toMs: number | null;
};

export function newsViewState(input: {
  loading: boolean;
  disabled: boolean;
  error: boolean;
  count: number;
  stale: boolean;
}): NewsViewState {
  if (input.loading) return "loading";
  if (input.disabled) return "disabled";
  if (input.error) return "error";
  if (input.count === 0) return "empty";
  if (input.stale) return "stale";
  return "ready";
}

export function isStaleNews(row: { warnings?: string[]; freshness?: string }) {
  if (row.freshness === "stale") return true;
  return (row.warnings || []).some((w) => w.includes("stale") || w.includes("delayed"));
}

export function filterNewsRows<T extends {
  symbols?: string[];
  assets?: string[];
  asset_hints?: string[];
  severity?: string;
  category?: string;
  verification?: string;
  published_at_ms?: number | null;
  available_at_ms?: number | null;
  detected_at_ms?: number | null;
}>(rows: T[], filters: NewsFilters): T[] {
  return rows.filter((row) => {
    const symbols = [
      ...(row.symbols || []),
      ...(row.assets || []),
      ...(row.asset_hints || []),
    ].map((s) => s.toUpperCase());
    if (filters.symbol && filters.symbol !== "ALL" && !symbols.includes(filters.symbol)) {
      return false;
    }
    if (filters.severity && filters.severity !== "ALL" && row.severity !== filters.severity) {
      return false;
    }
    if (filters.category && filters.category !== "ALL" && row.category !== filters.category) {
      return false;
    }
    if (
      filters.verification &&
      filters.verification !== "ALL" &&
      row.verification !== filters.verification
    ) {
      return false;
    }
    const stamp = row.published_at_ms || row.detected_at_ms || row.available_at_ms || null;
    if (filters.fromMs != null && (stamp == null || stamp < filters.fromMs)) return false;
    if (filters.toMs != null && (stamp == null || stamp > filters.toMs)) return false;
    return true;
  });
}

export function severityBadge(severity: string | undefined) {
  if (severity === "CRITICAL") return "danger" as const;
  if (severity === "HIGH") return "warning" as const;
  if (severity === "MEDIUM") return "ai" as const;
  return "outline" as const;
}

export function formatMs(value: number | null | undefined) {
  if (value == null) return "unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unavailable";
  return date.toISOString();
}
