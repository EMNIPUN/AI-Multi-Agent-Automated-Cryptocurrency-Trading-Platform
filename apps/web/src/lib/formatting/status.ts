/**
 * Canonical status vocabulary for the UI.
 *
 * Backend components report state with different words (RUNNING, ACTIVE,
 * IDLE, DISABLED, ERROR…). `normalizeStatus` maps them onto one set so every
 * indicator in the app reads the same way.
 */

export type StatusKind =
  | "running"
  | "idle"
  | "paused"
  | "stopped"
  | "failed"
  | "blocked"
  | "unknown"
  | "stale"
  | "ok";

export const STATUS_LABEL: Record<StatusKind, string> = {
  running: "Running",
  idle: "Idle",
  paused: "Paused",
  stopped: "Stopped",
  failed: "Failed",
  blocked: "Blocked",
  unknown: "Unknown",
  stale: "Stale",
  ok: "OK",
};

const MAP: Record<string, StatusKind> = {
  RUNNING: "running",
  ACTIVE: "running",
  STREAMING: "running",
  CONNECTED: "running",
  HEALTHY: "running",
  ONLINE: "running",
  STARTING: "running",
  RECONCILING: "running",
  RECOVERING: "running",
  IDLE: "idle",
  WAITING: "idle",
  READY: "idle",
  CONNECTING: "idle",
  PAUSED: "paused",
  STOPPED: "stopped",
  STOPPING: "stopped",
  DISABLED: "stopped",
  OFF: "stopped",
  OFFLINE: "stopped",
  DISCONNECTED: "stopped",
  ERROR: "failed",
  FAILED: "failed",
  DEGRADED: "failed",
  DOWN: "failed",
  TIMEOUT: "failed",
  HALTED: "blocked",
  BLOCKED: "blocked",
  VETO: "blocked",
  LOCKED: "blocked",
  DENIED: "blocked",
  UNKNOWN: "unknown",
  STALE: "stale",
  OK: "ok",
  APPROVED: "ok",
  SUCCESS: "ok",
  COMPLETE: "ok",
  COMPLETED: "ok",
  FILLED: "ok",
};

export function normalizeStatus(value: unknown): StatusKind {
  if (typeof value === "boolean") return value ? "ok" : "stopped";
  const key = String(value ?? "").trim().toUpperCase();
  if (!key) return "unknown";
  return MAP[key] ?? "unknown";
}

/** Which supervisor commands make sense for a canonical state. Mirrors backend `allowedCommands`. */
export function isTerminalStatus(kind: StatusKind): boolean {
  return kind === "stopped" || kind === "failed";
}
