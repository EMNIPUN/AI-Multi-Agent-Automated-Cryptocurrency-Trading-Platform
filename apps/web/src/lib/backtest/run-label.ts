import type { BacktestRunSummary } from "@/lib/backtest/types";
import { formatUtcMs } from "@/lib/backtest/format";

export function shortRunId(runId: string): string {
  if (!runId) return "—";
  if (runId.length <= 14) return runId;
  return `${runId.slice(0, 10)}…`;
}

export function humanRunLabel(run: BacktestRunSummary): string {
  const symbol = run.symbol || "Unknown";
  const interval = run.interval ? `${run.interval}m` : "—";
  const pnl =
    run.net_realized_pnl != null && run.net_realized_pnl !== ""
      ? `${Number(run.net_realized_pnl) >= 0 ? "+" : ""}${run.net_realized_pnl} USDT`
      : "no closed PnL";
  const kind =
    run.dataset_label?.includes("SYNTHETIC")
      ? "Synthetic"
      : run.dataset_label?.includes("HISTORICAL")
        ? "Historical"
        : "Offline";
  return `${symbol} · ${interval} · ${kind} · ${pnl}`;
}

export function runDateRange(run: BacktestRunSummary): string {
  if (run.first_start_ms == null || run.last_start_ms == null) return "Date range unavailable";
  return `${formatUtcMs(run.first_start_ms)} → ${formatUtcMs(run.last_start_ms)}`;
}

export function formatRunSnapshot(run: BacktestRunSummary): string {
  return [
    `run_id: ${run.run_id}`,
    `status: ${run.status}`,
    `symbol: ${run.symbol ?? "—"}`,
    `market: ${run.market_type ?? "—"}`,
    `interval: ${run.interval ?? "—"}`,
    `candles: ${run.candle_count ?? "—"}`,
    `dataset: ${run.dataset_label ?? run.source_kind ?? "—"}`,
    `engine: ${run.engine_version ?? "—"}`,
    `pipeline: ${run.pipeline_version ?? "—"}`,
    `closed_trades: ${run.closed_trades ?? "—"}`,
    `open_positions: ${run.open_positions ?? "—"}`,
    `net_realized_pnl: ${run.net_realized_pnl ?? "—"} USDT`,
    `dataset_hash: ${run.dataset_hash ?? "—"}`,
    `result_hash: ${run.result_hash ?? "—"}`,
    `range: ${runDateRange(run)}`,
  ].join("\n");
}
