"use client";

import { Badge } from "@/components/ui/badge";
import type { MarketConnectionState } from "@/lib/market/types";

export function MarketConnectionBadge({
  state,
  stale,
}: {
  state: MarketConnectionState | string;
  stale?: boolean;
}) {
  const label = stale || state === "stale" ? "STALE" : state.toUpperCase();
  const variant =
    state === "connected" && !stale
      ? "outline"
      : state === "connecting" || state === "reconnecting"
        ? "warning"
        : state === "stale" || stale
          ? "warning"
          : "danger";
  return <Badge variant={variant as "outline" | "warning" | "danger"}>{label}</Badge>;
}
