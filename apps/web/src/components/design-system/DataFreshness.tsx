"use client";

import { Clock3 } from "lucide-react";

import { useNow } from "@/hooks/use-polled-resource";
import { formatIso, formatRelative, isValidMs } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

export type DataFreshnessProps = {
  /** Timestamp (ms) of the data being described. */
  at: number | null | undefined;
  /** Age after which the data counts as stale. */
  staleAfterMs?: number;
  /** Prefix such as "Candle" or "Heartbeat". */
  label?: string;
  /** Text when `at` is missing. */
  missingLabel?: string;
  className?: string;
  size?: "xs" | "sm";
};

/**
 * Live-ticking freshness pill. Fresh / stale is computed on every tick so a
 * screen left open does not keep claiming "fresh".
 */
export function DataFreshness({
  at,
  staleAfterMs = 60_000,
  label,
  missingLabel = "No timestamp",
  className,
  size = "xs",
}: DataFreshnessProps) {
  const now = useNow(1000);
  const valid = isValidMs(at);
  const age = valid ? now - at : null;
  const stale = !valid || (age !== null && age > staleAfterMs);
  const text = valid ? `${label ? `${label} ` : ""}${formatRelative(at, now)}` : missingLabel;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium",
        size === "xs" ? "text-[10px]" : "text-[11px]",
        stale
          ? "border-stale-data/40 bg-stale-data/10 text-muted-foreground"
          : "border-profit/30 bg-profit/10 text-foreground",
        className,
      )}
      title={valid ? formatIso(at) : undefined}
      aria-label={`${stale ? "Stale" : "Fresh"}: ${text}`}
    >
      <Clock3 className="h-3 w-3" aria-hidden />
      <span>{stale ? "Stale · " : ""}{text}</span>
    </span>
  );
}
