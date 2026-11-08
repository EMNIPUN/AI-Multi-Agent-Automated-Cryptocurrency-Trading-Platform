/** Typed contracts for Prompt 68B backtest read API (saved 68A artifacts). */

export type OptionalMetric = {
  value: string | null;
  status: string;
  reason: string | null;
};

export type BacktestStatus = {
  enabled: boolean;
  results_dir: string;
  results_dir_exists: boolean;
  run_count: number;
  performance_label: string;
  note: string;
  mutations: boolean;
  runs_backtests: boolean;
  run_api_enabled?: boolean;
};

export type BacktestRunCapabilities = {
  run_api_enabled: boolean;
  read_api_enabled: boolean;
  symbols: string[];
  market_types: string[];
  intervals: string[];
  risk_modes: string[];
  data_sources: string[];
  max_candles_per_run: number;
  max_range_ms: number;
  max_simultaneous_runs: number;
  max_queued_runs: number;
  max_runtime_seconds: number;
  performance_label: string;
  linear_note: string;
  note: string;
};

export type BacktestRunRequest = {
  symbol: string;
  market_type: "spot" | "linear";
  interval: string;
  start_ms: number;
  end_ms: number;
  initial_capital: string;
  fee_rate: string;
  slippage_bps: string;
  risk_mode: "signal_only" | "portfolio";
  data_source: "bybit_public" | "offline_fixture";
  dataset_hash?: string;
  idempotency_key?: string;
  grace_ms?: number;
};

export type BacktestRunAccepted = {
  job_id: string;
  status: string;
  message: string;
  performance_label: string;
  estimated_candles?: number | null;
  idempotent_replay: boolean;
};

export type BacktestJobStatus = {
  job_id: string;
  status: string;
  run_id?: string | null;
  created_ms: number;
  started_ms?: number | null;
  finished_ms?: number | null;
  phase?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  request_summary: Record<string, unknown>;
  dataset_hash?: string | null;
  result_hash?: string | null;
  performance_label: string;
  linear_limitation?: string | null;
};

export type BacktestRunSummary = {
  run_id: string;
  status: string;
  symbol?: string | null;
  market_type?: string | null;
  interval?: string | null;
  first_start_ms?: number | null;
  last_start_ms?: number | null;
  candle_count?: number | null;
  provenance?: string | null;
  source_kind?: string | null;
  dataset_label?: string | null;
  engine_version?: string | null;
  pipeline_version?: string | null;
  dataset_hash?: string | null;
  result_hash?: string | null;
  created_ms?: number | null;
  closed_trades?: number | null;
  open_positions?: number | null;
  net_realized_pnl?: string | null;
  performance_label?: string | null;
};

export type BacktestRunDetail = {
  run_id: string;
  status: string;
  performance_label: string;
  effective_config: Record<string, unknown>;
  dataset: Record<string, unknown>;
  dataset_label: string;
  counters: Record<string, number | string>;
  eligible_candles?: number | null;
  warm_up_candles?: number | null;
  open_positions?: number | null;
  final_available_balance?: string | null;
  final_reserved_capital?: string | null;
  final_marked_equity?: string | null;
  data_quality_warnings: string[];
  result_hash?: string | null;
  created_ms?: number | null;
  error?: string | null;
  assumptions: string[];
  decision_trace_note: string;
  reconciliation_note: string;
  extras?: Record<string, unknown>;
};

export type BacktestMetrics = {
  run_id: string;
  performance_label: string;
  counters: Record<string, number | string>;
  analytics: Record<string, unknown> | null;
  final_available_balance?: string | null;
  final_reserved_capital?: string | null;
  final_marked_equity?: string | null;
  open_positions?: number | null;
  data_quality_warnings: string[];
};

export type BacktestTradesResponse = {
  run_id: string;
  items: Record<string, unknown>[];
  open_positions: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
  note: string;
};

export type BacktestEquityResponse = {
  run_id: string;
  marked_equity: { as_of_ms: number; value: string; valuation_status?: string }[];
  realized_balance: { as_of_ms: number; value: string; valuation_status?: string }[];
  note?: string | null;
  data_quality_warnings: string[];
  drawdown_note: string;
};

export type BacktestDecisionsResponse = {
  run_id: string;
  items: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
  note: string;
};

export type BacktestOrdersResponse = {
  run_id: string;
  items: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
  rejection_breakdown: Record<string, number>;
  note: string;
};

export type BacktestFetchResult<T> =
  | { ok: true; data: T; status: number }
  | { ok: false; status: number; detail: string; message?: string };
