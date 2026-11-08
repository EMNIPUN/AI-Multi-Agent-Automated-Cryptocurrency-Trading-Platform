export type SignalAction = "BUY" | "SELL" | "HOLD" | "BLOCKED";

export interface SignalContribution {
  agent_id: string;
  agent_version: string;
  bias: string;
  confidence: number;
  reason_codes: string[];
  explanation: string;
  indicators: Record<string, unknown>;
  timed_out?: boolean;
  error?: string | null;
}

export interface SignalHistoryItem {
  decision_id: string;
  idempotent_key: string;
  correlation_id: string;
  timestamp_ms: number;
  symbol: string;
  category: string;
  interval: string;
  strategy_version: string;
  config_hash: string;
  action: SignalAction | string;
  signal_strength: number;
  directional_conviction: number;
  market_quality: number;
  risk_verdict: string;
  source_mode: string;
  explanation: string;
  reason_codes: string[];
  contributions: SignalContribution[];
  risk: Record<string, unknown>;
  levels: Record<string, unknown>;
  market: Record<string, unknown>;
  indicators: Record<string, unknown>;
}

export interface SignalDecision {
  action: SignalAction;
  symbol: string;
  category: string;
  interval: string;
  timestamp_ms: number;
  strategy_version: string;
  correlation_id: string;
  decision_id: string;
  signal_strength: number;
  signal_strength_note: string;
  directional_conviction?: number;
  market_quality?: number;
  config_hash?: string;
  source_mode?: string;
  reason_codes: string[];
  explanation: string;
  execution_allowed: false;
  not_an_order: true;
  contributions: SignalContribution[];
  risk: {
    verdict: string;
    reason_codes: string[];
    explanation: string;
    paper_balance: number;
    risk_fraction: number;
    position_notional: number | null;
    stop_distance_pct: number | null;
    reward_distance_pct: number | null;
    risk_reward: number | null;
    cooldown_remaining_ms?: number;
    indicators?: Record<string, unknown>;
  };
  levels: {
    entry: number | null;
    stop_loss: number | null;
    take_profit: number | null;
    note: string;
  };
  market: {
    symbol: string;
    category: string;
    interval: string;
    bar_count: number;
    newest_close_ms: number;
    as_of_ms: number;
    data_fresh: boolean;
    data_path: string;
    last_price: number;
    valid: boolean;
    reason_codes: string[];
  };
  idempotent_key: string;
  news_changed_decision?: false;
  news_influence_label?: string;
  news_advisory?: {
    enabled?: boolean;
    consumed?: boolean;
    news_changed_decision?: false;
    label?: string;
    freshness?: string;
    storage_availability?: string;
    context_status?: string;
    source_event_ids?: string[];
    warnings?: string[];
    technical_news_conflict?: string | null;
    llm_recommendation?: null;
    events?: Array<Record<string, unknown>>;
  } | null;
}

export interface SignalEvaluateResponse {
  decision: SignalDecision;
  execution_allowed: boolean;
  trading_enabled: boolean;
  private_api_used: boolean;
  note: string;
}
