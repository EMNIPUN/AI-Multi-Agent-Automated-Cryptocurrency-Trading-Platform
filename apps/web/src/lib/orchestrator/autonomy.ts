import type { PAPER_COMMANDS } from "./commands";

export type SupervisorCommand = (typeof PAPER_COMMANDS)[number];

export type SessionAuthorization = {
  symbol: string;
  category: "spot" | "linear";
  interval: string;
  capital_usdt: string;
  risk_fraction: string;
  duration_hours: number;
  started_at_ms?: number;
  expires_at_ms?: number;
  risk_budget_usdt?: string;
};

export type AgentEvidence = {
  agent_id: string;
  bias: string;
  confidence: number;
  explanation: string;
  reason_codes: string[];
  timed_out?: boolean;
  error?: string | null;
};

export type DecisionEvidence = {
  decision_id: string;
  action: string;
  timestamp_ms: number;
  explanation: string;
  signal_strength: number;
  market_quality: number;
  reason_codes: string[];
  contributions: AgentEvidence[];
  risk: { verdict: string; explanation: string; risk_reward?: number | null; position_notional?: number | null };
  market: { data_fresh: boolean; last_price: number; newest_close_ms: number; bar_count: number };
};

export type SupervisorStatus = {
  enabled: boolean;
  state: string;
  mode: "PAPER";
  session_id?: string | null;
  authorization?: SessionAuthorization | null;
  block_new_exposure?: boolean;
  protective_monitoring?: boolean;
  worker_running?: boolean;
  heartbeat_ms?: number;
  last_cycle_ms?: number;
  last_candle_start?: number | null;
  last_action?: string | null;
  last_reason?: string | null;
  last_error?: string | null;
  latest_decision?: DecisionEvidence | null;
};

export type PaperPosition = {
  position_id: string;
  symbol: string;
  category: string;
  status: string;
  quantity: string;
  entry_price: string;
  mark_price: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  unrealized_pnl: string;
  opened_ms: number;
};

export type PaperClosedTrade = {
  position_id: string;
  symbol: string;
  quantity: string;
  entry_price: string;
  exit_price: string;
  realized_pnl: string;
  exit_reason: string;
  opened_ms: number;
  closed_ms: number;
};

export type PaperJournalReport = {
  available?: boolean;
  equity?: string;
  currency?: string;
  initial_balance?: string;
  realized_pnl?: string;
  unrealized_pnl?: string;
  fees_paid?: string;
  drawdown?: string;
  open_positions?: number;
  closed_trades?: number;
  winning_trades?: number;
  win_rate?: number | null;
  positions?: PaperPosition[];
  recent_trades?: PaperClosedTrade[];
  pending_orders?: { order_id: string; symbol: string; side: string; quantity: string; status: string; created_ms: number }[];
  recent_events?: { event_id: string; event_type: string; created_ms: number; payload: Record<string, unknown> }[];
};

export const SESSION_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D"] as const;

export function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formatMoney(value: unknown, digits = 2): string {
  const n = finiteNumber(value);
  return n === null ? "—" : n.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function formatTime(value: number | undefined | null): string {
  if (!value || !Number.isFinite(value)) return "Not received";
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function scorePercent(value: unknown): number | null {
  const n = finiteNumber(value);
  return n === null || n < 0 || n > 1 ? null : Math.round(n * 100);
}

export function allowedCommands(state: string): SupervisorCommand[] {
  switch (state) {
    case "STOPPED": return ["start"];
    case "RUNNING": return ["pause", "stop", "halt"];
    case "PAUSED": return ["resume", "stop", "halt"];
    case "HALTED": return ["stop"];
    case "ERROR": return ["stop", "halt"];
    case "STARTING": case "RECONCILING": case "RECOVERING": return ["stop", "halt"];
    case "STOPPING": return ["halt"];
    default: return [];
  }
}

export function validateAuthorization(auth: SessionAuthorization): string | null {
  if (!/^[A-Z0-9]{2,20}USDT$/.test(auth.symbol)) return "Use a USDT symbol such as BTCUSDT.";
  if (!["spot", "linear"].includes(auth.category)) return "Select a supported market.";
  if (!(SESSION_INTERVALS as readonly string[]).includes(auth.interval)) return "Select a supported candle interval.";
  const capital = finiteNumber(auth.capital_usdt);
  const risk = finiteNumber(auth.risk_fraction);
  if (capital === null || capital < 1 || capital > 1_000_000) return "Paper capital must be between 1 and 1,000,000 USDT.";
  if (risk === null || risk <= 0 || risk > 0.02) return "Risk per trade must be greater than 0% and at most 2%.";
  if (!Number.isInteger(auth.duration_hours) || auth.duration_hours < 1 || auth.duration_hours > 168) return "Session duration must be a whole number from 1 to 168 hours.";
  return null;
}

export function sessionProgress(auth: SessionAuthorization | null | undefined, now: number): number | null {
  if (!auth?.started_at_ms || !auth.expires_at_ms || auth.expires_at_ms <= auth.started_at_ms) return null;
  return Math.max(0, Math.min(100, 100 * (now - auth.started_at_ms) / (auth.expires_at_ms - auth.started_at_ms)));
}

/** Freshness describes an observed worker heartbeat, never an invented agent heartbeat. */
export function workerHealth(status: SupervisorStatus | null, now: number): "offline" | "waiting" | "healthy" | "stale" {
  if (!status?.enabled || !status.worker_running) return "offline";
  const heartbeat = status.heartbeat_ms;
  if (!heartbeat) return "waiting";
  return now - heartbeat > 180_000 || heartbeat > now + 30_000 ? "stale" : "healthy";
}
