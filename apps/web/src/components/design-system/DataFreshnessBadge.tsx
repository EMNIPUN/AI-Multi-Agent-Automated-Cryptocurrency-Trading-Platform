import { StatusBadge } from "@/components/design-system/StatusBadge";

export function DataFreshnessBadge({
  at,
  staleAfterMs = 60_000,
  label,
}: {
  at: number | Date | null | undefined;
  staleAfterMs?: number;
  label?: string;
}) {
  if (at == null) {
    return <StatusBadge label={label ?? "No timestamp"} tone="stale" />;
  }
  const ms = typeof at === "number" ? at : at.getTime();
  const age = Date.now() - ms;
  const stale = !Number.isFinite(ms) || age > staleAfterMs;
  const seconds = Math.max(0, Math.round(age / 1000));
  return (
    <StatusBadge
      label={stale ? `Stale · ${seconds}s` : label ?? `Fresh · ${seconds}s`}
      tone={stale ? "stale" : "ok"}
    />
  );
}
