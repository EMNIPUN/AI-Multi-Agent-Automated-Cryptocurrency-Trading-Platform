/** Display helpers for 68B — reuse 67A semantics; no fixture fallback. */

import {
  formatDecimalDisplay,
  formatHoldingDuration,
  formatOptionalMetric as formatPaperOptionalMetric,
  formatUtcMs,
  signedMoneyClass,
} from "@/lib/paper/analytics-format";
import type { OptionalMetric as PaperOptionalMetric } from "@/lib/paper/types";

import type { OptionalMetric } from "@/lib/backtest/types";

export {
  formatDecimalDisplay,
  formatHoldingDuration,
  formatUtcMs,
  signedMoneyClass,
};

export function asOptionalMetric(raw: unknown): OptionalMetric | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  return {
    value: o.value == null ? null : String(o.value),
    status: String(o.status || "unavailable"),
    reason: o.reason == null ? null : String(o.reason),
  };
}

export function formatOptionalMetric(
  metric: OptionalMetric | null | undefined,
  options?: { suffix?: string; unboundedLabel?: string },
): string {
  return formatPaperOptionalMetric(metric as PaperOptionalMetric | null | undefined, options);
}

export function assertNoFixturePayload(label: string | null | undefined): boolean {
  if (!label) return true;
  const lower = label.toLowerCase();
  return !(lower.includes("sample") && lower.includes("fixture") && lower.includes("demo live"));
}

export const SIM_LABEL =
  "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE";

export const HISTORICAL_SIM_LABEL = "Historical Simulation — Not Live Trading";

export const ADVISORY_UNCHANGED_LABEL = "Advisory Only — Trading Decisions Unchanged";

export function shadowComparisonAllowed(provenance: string | null | undefined): boolean {
  return provenance === "complete";
}
