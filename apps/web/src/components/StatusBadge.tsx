import type { AgentRuntimeStatus } from "@/lib/observability/types";

export function StatusBadge({ status }: { status: AgentRuntimeStatus }) {
  const cls =
    status === "RUNNING"
      ? "ok"
      : status === "HALTED"
        ? "danger"
        : status === "OFFLINE" || status === "UNKNOWN"
          ? "warn"
          : "muted";
  return <span className={`badge ${cls}`}>{status}</span>;
}
