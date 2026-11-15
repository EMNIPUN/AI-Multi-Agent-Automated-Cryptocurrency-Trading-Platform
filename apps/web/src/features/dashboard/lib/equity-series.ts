import { toNumber } from "@/lib/formatting/decimal";
import type { PaperJournalReport } from "@/lib/orchestrator/autonomy";

export type EquityPoint = { t: number; value: number; label?: string };

/**
 * Realized paper equity over time, reconstructed from the journal report:
 * initial balance, then each closed trade's realized PnL in close order.
 *
 * This is *realized* equity (closed trades only). Open-position mark-to-market
 * is not part of the series, and the caller labels it that way.
 */
export function realizedEquitySeries(report: PaperJournalReport | null | undefined): EquityPoint[] {
  if (!report) return [];
  const initial = toNumber(report.initial_balance);
  const trades = Array.isArray(report.recent_trades) ? report.recent_trades : [];
  if (initial === null) return [];
  const sorted = trades
    .map((t) => ({ closed: toNumber(t.closed_ms), pnl: toNumber(t.realized_pnl), symbol: t.symbol, reason: t.exit_reason }))
    .filter((t): t is { closed: number; pnl: number; symbol: string; reason: string } => t.closed !== null && t.pnl !== null)
    .sort((a, b) => a.closed - b.closed);
  if (sorted.length === 0) return [];
  const points: EquityPoint[] = [];
  let equity = initial;
  // Anchor the curve at the first trade's open-ish time so the chart has a start.
  const firstOpen = toNumber(trades.find((t) => toNumber(t.closed_ms) === sorted[0].closed)?.opened_ms);
  points.push({ t: firstOpen ?? sorted[0].closed - 1, value: equity, label: "Session start" });
  for (const trade of sorted) {
    equity += trade.pnl;
    points.push({ t: trade.closed, value: equity, label: `${trade.symbol} · ${trade.reason || "close"}` });
  }
  return points;
}
