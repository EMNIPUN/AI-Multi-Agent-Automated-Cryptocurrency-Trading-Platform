/**
 * Strategy catalog — a documented mirror of the backend configuration.
 *
 * Source of truth: `agent/multi_agent/config.py` (SignalPipelineConfig,
 * PaperRiskConfig, RegimeConfig) and the agent modules under
 * `agent/multi_agent/`. The UI compares `version` with the live
 * `strategy_version` from `/api/signals/status` and warns on mismatch, so a
 * stale copy is visible instead of silently wrong.
 */

export type StrategyParam = { label: string; value: string; note?: string };

export type StrategyEntry = {
  id: string;
  name: string;
  version: string;
  status: "product" | "legacy";
  summary: string;
  markets: string[];
  intervals: string[];
  source: string;
  agents: { id: string; name: string; weight: string | null; rule: string }[];
  decision: StrategyParam[];
  risk: StrategyParam[];
  regime: StrategyParam[];
  limits: string[];
};

export const STRATEGY_CATALOG: readonly StrategyEntry[] = [
  {
    id: "multi_agent_signal_pipeline",
    name: "Multi-agent SignalPipeline",
    version: "6.0.0",
    status: "product",
    summary:
      "Market data validates confirmed candles; trend, momentum, volume and structure agents score direction in parallel; the coordinator combines them; a regime gate and a deterministic risk engine can turn any proposal into HOLD or BLOCKED.",
    markets: ["linear (USDT perpetual, long-only in paper)", "spot"],
    intervals: ["1m", "5m", "15m", "1h", "4h", "1D"],
    source: "agent/multi_agent/",
    agents: [
      { id: "market_data", name: "Market Data", weight: null, rule: "Confirmed bars only; gaps, stale data or bad prices make the snapshot invalid (BLOCKED)." },
      { id: "trend", name: "Trend", weight: "0.40", rule: "EMA20/50/200 stack and EMA20×EMA50 crossovers; needs ≥210 closes." },
      { id: "momentum", name: "Momentum", weight: "0.30", rule: "RSI14 band plus 5-bar price momentum; overbought/oversold is caution, never an automatic entry." },
      { id: "volume", name: "Volume", weight: "0.15", rule: "Relative volume vs 20-bar average and price/volume agreement." },
      { id: "structure", name: "Structure", weight: "0.15", rule: "Swing HH/HL vs LH/LL and 10-bar range breaks." },
      { id: "regime", name: "Regime", weight: null, rule: "Efficiency ratio over 20 bars; ranging markets abstain. Gate only, not a directional weight." },
    ],
    decision: [
      { label: "Buy threshold", value: "conviction ≥ 0.35", note: "Weighted signed conviction in [-1, 1]" },
      { label: "Sell threshold", value: "conviction ≤ -0.35" },
      { label: "Market quality gate", value: "1.0", note: "Data must be fully valid and fresh" },
      { label: "Minimum supporting agents", value: "2" },
      { label: "Trend/momentum conflict", value: "HOLD" },
      { label: "Minimum history", value: "210 confirmed bars" },
    ],
    risk: [
      { label: "Risk per trade", value: "1% of paper equity" },
      { label: "Stop distance", value: "ATR×1.2, clamped 0.4%–3%" },
      { label: "Take profit", value: "2× stop distance" },
      { label: "Volatility cap", value: "ATR/price ≤ 6%" },
      { label: "Cooldown", value: "15 minutes between approved signals" },
      { label: "Daily loss halt", value: "3% (signal risk + supervisor)" },
      { label: "Drawdown halt", value: "10% from peak (supervisor)" },
      { label: "Agent timeout", value: "250 ms, fail closed" },
    ],
    regime: [
      { label: "Lookback", value: "20 bars" },
      { label: "Trending if efficiency", value: "≥ 0.35" },
      { label: "Ranging if efficiency", value: "≤ 0.15" },
    ],
    limits: [
      "Scores are qualitative agreement, not calibrated win probability.",
      "Paper linear simulation is long-only; funding and liquidation are not modelled.",
      "News and LLM output are advisory and cannot change BUY/SELL.",
      "Signal APIs always return execution_allowed = false.",
    ],
  },
  {
    id: "ema_rsi",
    name: "EMA crossover + RSI filter",
    version: "legacy",
    status: "legacy",
    summary: "Original single-strategy agent run by `run_agent.py` (AgentRunner). Kept for research; not the product path.",
    markets: ["linear", "spot"],
    intervals: ["configured by AGENT_INTERVAL"],
    source: "agent/strategies/ema_rsi.py",
    agents: [],
    decision: [
      { label: "Fast / slow EMA", value: "9 / 21 (AGENT_EMA_FAST / AGENT_EMA_SLOW)" },
      { label: "RSI period", value: "14, bounds 30 / 70" },
    ],
    risk: [
      { label: "Risk per trade", value: "AGENT_RISK_PCT of equity" },
      { label: "TP / SL", value: "AGENT_TP_PCT / AGENT_SL_PCT" },
      { label: "Daily loss kill switch", value: "AGENT_DAILY_LOSS_PCT" },
    ],
    regime: [],
    limits: [
      "Places real exchange orders when AGENT_DRY_RUN=false and live gates allow it — this UI never starts it.",
    ],
  },
];

export function versionMatches(entry: StrategyEntry, liveVersion: string | null | undefined): boolean | null {
  if (!liveVersion || entry.status !== "product") return null;
  return entry.version === liveVersion;
}
