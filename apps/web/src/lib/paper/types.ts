/** Paper read API DTOs — decimal fields are strings. */

export type PaperDataLabel = "SIMULATED / PAPER ONLY";

export interface PaperStatus {
  paper_read_api_enabled: boolean;
  broker_auto_attach: boolean;
  execution_allowed: boolean;
  trading_endpoints: boolean;
  db_configured: boolean;
  db_present: boolean;
  schema_version: number | null;
  session_count: number | null;
  note: string;
  data_label: PaperDataLabel;
}

export interface PaperSessionSummary {
  session_id: string;
  status: string;
  currency: string;
  initial_balance: string;
  available_balance: string;
  reserved_capital: string;
  realized_pnl: string;
  fees_paid: string;
  created_ms: number;
  updated_ms: number;
  open_position_count?: number | null;
  data_label: PaperDataLabel;
  simulated: boolean;
}

export interface PaperAccount {
  session_id: string;
  status: string;
  currency: string;
  initial_balance: string;
  available_balance: string;
  reserved_capital: string;
  realized_pnl: string;
  fees_paid: string;
  open_position_count: number;
  unrealized_pnl: string | null;
  unrealized_pnl_status: "ok" | "unavailable" | "stale_or_partial" | "none";
  marked_equity: string | null;
  marked_equity_status: "ok" | "unavailable" | "stale_or_partial";
  created_ms: number;
  updated_ms: number;
  note: string;
  data_label: PaperDataLabel;
  simulated: boolean;
}

export interface PaperPosition {
  position_id: string;
  session_id: string;
  symbol: string;
  category: string;
  side: "LONG";
  status: string;
  quantity: string;
  entry_price: string;
  entry_fee: string;
  stop_loss: string | null;
  take_profit: string | null;
  opened_ms: number;
  closed_ms: number | null;
  exit_price: string | null;
  exit_fee: string;
  exit_reason: string | null;
  realized_pnl: string;
  mark_price: string | null;
  unrealized_pnl: string | null;
  unrealized_pnl_status: "ok" | "unavailable";
  entry_signal_id: string;
  entry_order_id: string;
  exit_order_id: string | null;
  data_label: PaperDataLabel;
  simulated: boolean;
}

export interface PaperOrder {
  order_id: string;
  session_id: string;
  source_signal_id: string;
  symbol: string;
  category: string;
  side: string;
  quantity: string;
  intended_entry_price: string;
  status: string;
  created_ms: number;
  filled_ms: number | null;
  fill_price: string | null;
  fee: string;
  slippage: string;
  rejection_reason: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  data_label: PaperDataLabel;
  simulated: boolean;
}

export interface PaperSignalLink {
  source_signal_id: string;
  linked: boolean;
  orders: PaperOrder[];
  message: string;
  data_label: PaperDataLabel;
}

/** Prompt 67A analytics DTOs — decimals are strings; optional metrics carry status. */

export type MetricAvailabilityStatus =
  | "available"
  | "unavailable"
  | "unbounded"
  | "empty";

export interface OptionalMetric {
  value: string | null;
  status: MetricAvailabilityStatus | string;
  reason: string | null;
}

export interface DrawdownApi {
  max_drawdown_pct: OptionalMetric;
  max_drawdown_amount: OptionalMetric;
  peak_ms: number | null;
  trough_ms: number | null;
  series_type: string;
  observation_count: number;
  sparse_warning: boolean;
  label: string;
  notes: string[];
}

export interface SymbolBreakdownApi {
  symbol: string;
  closed_trades: number;
  winners: number;
  losers: number;
  breakeven: number;
  net_realized_pnl: string;
  fees: string;
  win_rate_pct: OptionalMetric;
}

export interface PaperAnalyticsResponse {
  session_id: string;
  currency: string;
  initial_balance: string;
  closed_trades: number;
  open_positions: number;
  winning_trades: number;
  losing_trades: number;
  breakeven_trades: number;
  win_rate_pct: OptionalMetric;
  gross_profit: string;
  gross_loss: string;
  net_realized_pnl: string;
  total_fees: string;
  profit_factor: OptionalMetric;
  average_win: OptionalMetric;
  average_loss: OptionalMetric;
  expectancy: OptionalMetric;
  average_trade_pnl: OptionalMetric;
  best_trade_pnl: OptionalMetric;
  worst_trade_pnl: OptionalMetric;
  average_holding_ms: OptionalMetric;
  realized_return_pct: OptionalMetric;
  fee_drag: string;
  equity_observation_count: number;
  marked_equity_observation_count: number;
  realized_balance_observation_count: number;
  max_drawdown_marked: DrawdownApi | null;
  max_drawdown_realized_balance: DrawdownApi | null;
  symbol_breakdown: SymbolBreakdownApi[];
  data_quality_warnings: string[];
  note: string;
  data_label: PaperDataLabel;
  simulated: boolean;
}

export interface PaperAnalyticsTradeItem {
  position_id: string;
  session_id: string;
  symbol: string;
  category: string;
  quantity: string;
  entry_price: string;
  exit_price: string;
  entry_fee: string;
  exit_fee: string;
  gross_realized_pnl: string;
  net_realized_pnl: string;
  exit_reason: string | null;
  opened_ms: number;
  closed_ms: number;
  holding_duration_ms: number;
  data_label: PaperDataLabel;
}

export interface PaperAnalyticsTradesResponse {
  items: PaperAnalyticsTradeItem[];
  limit: number;
  offset: number;
  warnings: string[];
  data_label: PaperDataLabel;
}

export interface PaperEquityPointApi {
  as_of_ms: number;
  value: string;
  valuation_status: string;
  series_type: string;
}

export interface PaperAnalyticsEquityResponse {
  series_type: string;
  points: PaperEquityPointApi[];
  warnings: string[];
  data_label: PaperDataLabel;
}

export interface PaperAnalyticsSymbolsResponse {
  items: SymbolBreakdownApi[];
  data_label: PaperDataLabel;
}
