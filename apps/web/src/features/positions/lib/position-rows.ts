import type { PaperJournalReport } from "@/lib/orchestrator/autonomy";
import type { PaperPosition as ReadApiPosition } from "@/lib/paper/types";

export type PositionMode = "PAPER" | "TESTNET" | "MAINNET";
export type PositionSource = "supervisor_journal" | "paper_read_api";

/** One normalized row for the positions grid. Decimal fields stay strings. */
export type PositionRow = {
  key: string;
  mode: PositionMode;
  source: PositionSource;
  session_id: string | null;
  symbol: string;
  market: string;
  side: string;
  status: string;
  quantity: string | null;
  entry_price: string | null;
  mark_price: string | null;
  exit_price: string | null;
  unrealized_pnl: string | null;
  realized_pnl: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  opened_ms: number | null;
  closed_ms: number | null;
  updated_ms: number | null;
  exit_reason: string | null;
  entry_signal_id: string | null;
  raw: Record<string, unknown>;
};

export function rowsFromSupervisorReport(report: PaperJournalReport | null | undefined, sessionId: string | null): PositionRow[] {
  if (!report) return [];
  const open = (report.positions ?? []).map<PositionRow>((p) => ({
    key: `sup-open-${p.position_id}`,
    mode: "PAPER",
    source: "supervisor_journal",
    session_id: sessionId,
    symbol: p.symbol,
    market: p.category,
    side: "LONG",
    status: p.status || "OPEN",
    quantity: p.quantity,
    entry_price: p.entry_price,
    mark_price: p.mark_price,
    exit_price: null,
    unrealized_pnl: p.unrealized_pnl,
    realized_pnl: null,
    stop_loss: p.stop_loss,
    take_profit: p.take_profit,
    opened_ms: p.opened_ms,
    closed_ms: null,
    updated_ms: p.opened_ms,
    exit_reason: null,
    entry_signal_id: null,
    raw: p as unknown as Record<string, unknown>,
  }));
  const closed = (report.recent_trades ?? []).map<PositionRow>((t) => ({
    key: `sup-closed-${t.position_id}`,
    mode: "PAPER",
    source: "supervisor_journal",
    session_id: sessionId,
    symbol: t.symbol,
    market: "linear",
    side: "LONG",
    status: "CLOSED",
    quantity: t.quantity,
    entry_price: t.entry_price,
    mark_price: null,
    exit_price: t.exit_price,
    unrealized_pnl: null,
    realized_pnl: t.realized_pnl,
    stop_loss: null,
    take_profit: null,
    opened_ms: t.opened_ms,
    closed_ms: t.closed_ms,
    updated_ms: t.closed_ms,
    exit_reason: t.exit_reason,
    entry_signal_id: null,
    raw: t as unknown as Record<string, unknown>,
  }));
  return [...open, ...closed];
}

export function rowsFromReadApi(positions: ReadApiPosition[]): PositionRow[] {
  return positions.map<PositionRow>((p) => ({
    key: `api-${p.position_id}`,
    mode: "PAPER",
    source: "paper_read_api",
    session_id: p.session_id,
    symbol: p.symbol,
    market: p.category,
    side: p.side,
    status: p.status,
    quantity: p.quantity,
    entry_price: p.entry_price,
    mark_price: p.unrealized_pnl_status === "ok" ? p.mark_price : null,
    exit_price: p.exit_price,
    unrealized_pnl: p.unrealized_pnl_status === "ok" ? p.unrealized_pnl : null,
    realized_pnl: p.status === "CLOSED" ? p.realized_pnl : null,
    stop_loss: p.stop_loss,
    take_profit: p.take_profit,
    opened_ms: p.opened_ms,
    closed_ms: p.closed_ms,
    updated_ms: p.closed_ms ?? p.opened_ms,
    exit_reason: p.exit_reason,
    entry_signal_id: p.entry_signal_id,
    raw: p as unknown as Record<string, unknown>,
  }));
}

export type PositionFilters = { status: "all" | "open" | "closed"; market: "all" | "spot" | "linear"; mode: "all" | PositionMode };

export function filterRows(rows: PositionRow[], f: PositionFilters): PositionRow[] {
  return rows.filter((r) => {
    if (f.status === "open" && r.status.toUpperCase() !== "OPEN") return false;
    if (f.status === "closed" && r.status.toUpperCase() !== "CLOSED") return false;
    if (f.market !== "all" && r.market.toLowerCase() !== f.market) return false;
    if (f.mode !== "all" && r.mode !== f.mode) return false;
    return true;
  });
}
