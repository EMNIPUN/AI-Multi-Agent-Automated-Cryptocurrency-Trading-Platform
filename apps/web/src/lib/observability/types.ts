export type AgentRuntimeStatus =
  | "RUNNING"
  | "IDLE"
  | "OFFLINE"
  | "HALTED"
  | "UNKNOWN";

export type ExecutionMode = "DRY_RUN" | "PAPER" | "TESTNET" | "MAINNET_READONLY";

export type PipelineStep =
  | "market_data"
  | "confirmed_candle"
  | "strategy"
  | "signal"
  | "risk"
  | "intent"
  | "reconciliation"
  | "position"
  | "blocked"
  | "halted"
  | "unknown";

export type DataMode = "fixture" | "live" | "unavailable";

export interface ObservabilityEvent {
  schema_version: string;
  event_id: string;
  event_type: string;
  occurred_at: string;
  correlation_id?: string | null;
  env_scope: string;
  account_scope_label?: string | null;
  symbol?: string | null;
  interval?: string | null;
  execution_mode: ExecutionMode;
  pipeline_step?: PipelineStep | null;
  message: string;
  payload: Record<string, unknown>;
}

export interface CandleBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
}

export interface SignalMarker {
  time: number;
  action: "BUY" | "SELL" | "HOLD";
  price: number;
  label?: string;
  sample?: boolean;
}

export interface OrderLifecycleItem {
  client_order_id: string;
  state: string;
  side?: string | null;
  qty?: string | null;
  filled_qty?: string | null;
  correlation_id?: string | null;
  updated_at?: string | null;
  sample?: boolean;
}

export interface AgentSnapshot {
  schema_version: string;
  data_mode: DataMode;
  sample_label?: string | null;
  generated_at: string;
  agent_status: AgentRuntimeStatus;
  heartbeat_at?: string | null;
  heartbeat_stale: boolean;
  stale_after_seconds: number;
  symbol: string;
  interval: string;
  execution_mode: ExecutionMode;
  money_view: "paper" | "real_readonly";
  last_confirmed_candle_at?: string | null;
  ema_fast?: number | null;
  ema_slow?: number | null;
  rsi?: number | null;
  signal_action?: "BUY" | "SELL" | "HOLD" | null;
  signal_reason?: string | null;
  risk_verdict: "APPROVED" | "BLOCKED" | "UNKNOWN" | "N/A";
  risk_reasons: string[];
  current_pipeline_step: PipelineStep;
  pipeline_blocked: boolean;
  pipeline_block_reason?: string | null;
  candles: CandleBar[];
  markers: SignalMarker[];
  orders: OrderLifecycleItem[];
  events: ObservabilityEvent[];
  cursor?: string | null;
  notes: string[];
}

export interface PaperWorkspaceSnapshot {
  schema_version: string;
  data_mode: DataMode;
  sample_label: string;
  generated_at: string;
  virtual_equity: number;
  cash: number;
  unrealized_pnl: number;
  realized_pnl: number;
  positions: Array<Record<string, unknown>>;
  simulated_orders: Array<Record<string, unknown>>;
  history: Array<Record<string, unknown>>;
  submit_controls_enabled: boolean;
  broker_implemented: boolean;
  notes: string[];
}

export const PIPELINE_STEPS: { id: PipelineStep; label: string }[] = [
  { id: "market_data", label: "Market Data" },
  { id: "confirmed_candle", label: "Confirmed Candle" },
  { id: "strategy", label: "Strategy" },
  { id: "signal", label: "Signal" },
  { id: "risk", label: "Risk" },
  { id: "intent", label: "Intent" },
  { id: "reconciliation", label: "Reconciliation" },
  { id: "position", label: "Position" },
];
