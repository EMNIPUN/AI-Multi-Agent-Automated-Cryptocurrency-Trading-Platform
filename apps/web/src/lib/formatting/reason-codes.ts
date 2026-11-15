/**
 * Human explanations for backend reason codes.
 *
 * Codes come from `agent/multi_agent/*`, `agent/supervisor/*`, and the
 * orchestrator. Unknown codes fall back to a humanized label so nothing is
 * hidden — but nothing is invented either.
 */

export type ReasonSeverity = "info" | "ok" | "warn" | "block";

export type ReasonExplanation = {
  code: string;
  title: string;
  detail: string;
  severity: ReasonSeverity;
};

const CATALOG: Record<string, Omit<ReasonExplanation, "code">> = {
  // Market / data quality
  MARKET_OK: { title: "Market data OK", detail: "Confirmed candles are fresh and continuous.", severity: "ok" },
  MARKET_QUALITY_GATE: { title: "Market quality gate", detail: "Candle data did not meet the quality threshold, so no directional signal was allowed.", severity: "block" },
  STALE_DATA: { title: "Stale data", detail: "The newest confirmed candle is older than the allowed staleness window.", severity: "block" },
  STALE_OR_INVALID_MARKET: { title: "Stale or invalid market", detail: "The risk engine refused to size a trade on stale or invalid candles.", severity: "block" },
  CANDLE_SEQUENCE_GAP: { title: "Candle gap", detail: "A gap was found in the confirmed candle sequence.", severity: "warn" },
  CANDLE_FILTER_REJECT: { title: "Candles rejected", detail: "Incoming candles failed validation (malformed or forming bars).", severity: "block" },
  NON_POSITIVE_PRICE: { title: "Bad price", detail: "A candle contained a zero or negative price.", severity: "block" },
  INSUFFICIENT_BARS: { title: "Not enough bars", detail: "Fewer confirmed candles than the strategy needs.", severity: "warn" },
  INSUFFICIENT_DATA: { title: "Insufficient data", detail: "Indicators need more history before they can form a bias (EMA200 needs 210+ closes).", severity: "warn" },
  INDICATORS_WARMING: { title: "Indicators warming", detail: "Indicator series are not ready yet.", severity: "warn" },
  INVALID_CATEGORY: { title: "Invalid market category", detail: "Only spot and linear perpetual markets are supported.", severity: "block" },
  market_data_unavailable: { title: "Market data unavailable", detail: "The worker could not fetch public candles. New exposure is blocked until data returns.", severity: "block" },
  invalid_candles: { title: "Invalid candles", detail: "Candle ordering or values were invalid for this cycle.", severity: "block" },

  // Coordinator
  COORD_BUY: { title: "Coordinator proposed BUY", detail: "Directional conviction met the buy threshold.", severity: "ok" },
  COORD_SELL: { title: "Coordinator proposed SELL", detail: "Directional conviction met the sell threshold.", severity: "ok" },
  COORD_HOLD: { title: "Neutral conviction", detail: "Weighted agent conviction stayed inside the neutral band.", severity: "info" },
  AGENT_CONFLICT: { title: "Agents disagree", detail: "Directional agents pointed in opposite directions, so the coordinator abstained.", severity: "warn" },
  REGIME_UNAVAILABLE: { title: "Regime unavailable", detail: "The regime agent could not confirm the market structure.", severity: "warn" },
  RANGING_MARKET_ABSTENTION: { title: "Ranging market", detail: "The trend strategy abstains when the regime agent reports a range.", severity: "info" },
  CONSENSUS_INSUFFICIENT: { title: "Not enough agreement", detail: "Fewer agents supported the direction than the consensus minimum requires.", severity: "warn" },
  REGIME_TRENDING: { title: "Trending regime", detail: "Price efficiency indicates a directional market.", severity: "ok" },
  REGIME_RANGING: { title: "Ranging regime", detail: "Price efficiency indicates a sideways market.", severity: "info" },
  REGIME_TRANSITIONAL: { title: "Transitional regime", detail: "Market structure is between ranging and trending.", severity: "info" },
  REGIME_HIGH_VOLATILITY: { title: "High volatility", detail: "ATR relative to price exceeds the strategy's volatility cap.", severity: "warn" },

  // Risk engine
  RISK_OK: { title: "Risk approved", detail: "Paper sizing fits the per-trade risk budget and stop distance.", severity: "ok" },
  NO_TRADE_PROPOSAL: { title: "No trade proposed", detail: "HOLD or BLOCKED needs no sizing.", severity: "info" },
  DUPLICATE_SIGNAL: { title: "Duplicate signal", detail: "This candle already produced the same signal — suppressed.", severity: "info" },
  COOLDOWN_ACTIVE: { title: "Cooldown active", detail: "A recent signal is still inside the cooldown window.", severity: "info" },
  ATR_UNAVAILABLE: { title: "ATR unavailable", detail: "Not enough bars to measure volatility, so a stop cannot be sized.", severity: "block" },
  VOLATILITY_FILTER: { title: "Volatility filter", detail: "ATR/price is above the maximum the strategy will trade.", severity: "block" },
  RISK_REWARD_BELOW_MIN: { title: "Reward too small", detail: "Reward-to-risk fell below the strategy minimum.", severity: "block" },
  TREND_CONFLICT_VETO: { title: "Trend conflict veto", detail: "The proposal went against the dominant trend; the risk engine vetoed it.", severity: "block" },
  DAILY_HYPOTHETICAL_LOSS_HALT: { title: "Daily loss halt", detail: "Hypothetical daily loss hit the halt threshold.", severity: "block" },
  PERSISTENCE_FAILED: { title: "Persistence failed", detail: "The decision could not be written durably, so it was converted to BLOCKED (fail closed).", severity: "block" },

  // Supervisor / paper broker
  NOT_ACTIONABLE: { title: "Not actionable", detail: "The decision was HOLD, BLOCKED, or vetoed — no paper order was created.", severity: "info" },
  FLAT_BUDGET: { title: "Budget too small", detail: "The authorized risk budget cannot fit exchange minimum size. Leverage was not raised.", severity: "warn" },
  BLOCKED_INSUFFICIENT_RISK_BUDGET: { title: "Insufficient risk budget", detail: "Minimum quantity and notional exceed the risk budget — stays flat.", severity: "warn" },
  INVALID_ENTRY_RISK: { title: "Invalid entry levels", detail: "Entry, stop, and target were not consistent, so the paper entry was skipped.", severity: "warn" },
  DECISION_SCOPE_MISMATCH: { title: "Scope mismatch", detail: "The decision's symbol or interval did not match the authorized session.", severity: "warn" },
  MISSING_DECISION: { title: "Missing decision", detail: "No decision reached the paper trader for this candle.", severity: "warn" },
  DAILY_LOSS_LIMIT: { title: "Daily loss limit", detail: "Paper equity fell 3% from the day's start; new entries are halted.", severity: "block" },
  DRAWDOWN_LIMIT: { title: "Drawdown limit", detail: "Paper equity fell 10% from its peak; new entries are halted.", severity: "block" },
  EQUITY_EXHAUSTED: { title: "Equity exhausted", detail: "Paper equity reached zero.", severity: "block" },
  HALTED_BLOCKED_ENTRY: { title: "Halted", detail: "Emergency halt blocks new entries; protective exits still run.", severity: "block" },
  PAUSED_PROTECTIVE_MONITORING: { title: "Paused", detail: "New entries paused; open positions remain monitored.", severity: "info" },
  STOPPING_CLOSE_REQUESTED: { title: "Closing", detail: "Stop requested — open positions close on the next eligible candle.", severity: "info" },
  session_expired: { title: "Session expired", detail: "The authorized session window ended; no new entries.", severity: "info" },
  journal_write_failed: { title: "Journal write failed", detail: "The paper journal could not be updated. New exposure is blocked.", severity: "block" },
  unknown_position_state: { title: "Unknown position state", detail: "Open positions could not be read; the supervisor failed closed.", severity: "block" },
  journal_session_mismatch: { title: "Journal mismatch", detail: "Supervisor state and journal session id drifted.", severity: "block" },
  journal_unavailable: { title: "Journal unavailable", detail: "The paper journal file could not be opened.", severity: "block" },
  supervisor_worker_busy: { title: "Worker busy", detail: "Another worker holds the supervisor lease.", severity: "warn" },
  supervisor_state_corrupt: { title: "State corrupt", detail: "Supervisor state file is unreadable; manual recovery needed.", severity: "block" },
  authorization_change_requires_new_journal: { title: "New journal required", detail: "Changing symbol/capital needs a fresh journal — stop first.", severity: "warn" },
  session_already_active: { title: "Session active", detail: "A session is already running.", severity: "info" },
  command_not_allowed: { title: "Command not allowed", detail: "That command is not valid in the current state.", severity: "warn" },
  duplicate_candle: { title: "Duplicate candle", detail: "This candle was already evaluated.", severity: "info" },
  out_of_order_candle: { title: "Out-of-order candle", detail: "An older candle arrived after a newer one — ignored.", severity: "info" },

  // Trend / momentum / volume / structure evidence
  EMA_STACK_BULL: { title: "Bullish EMA stack", detail: "EMA20 > EMA50 > EMA200 with price above EMA20.", severity: "ok" },
  EMA_STACK_BEAR: { title: "Bearish EMA stack", detail: "EMA20 < EMA50 < EMA200 with price below EMA20.", severity: "ok" },
  PRICE_ABOVE_EMA200_FAST_ABOVE_SLOW: { title: "Above EMA200", detail: "Price above EMA200 with fast EMA above slow.", severity: "ok" },
  PRICE_BELOW_EMA200_FAST_BELOW_SLOW: { title: "Below EMA200", detail: "Price below EMA200 with fast EMA below slow.", severity: "ok" },
  MIXED_STRUCTURE: { title: "Mixed structure", detail: "EMAs are not aligned.", severity: "info" },
  EMA20_CROSS_ABOVE_EMA50: { title: "Bullish cross", detail: "EMA20 crossed above EMA50 on the last bar.", severity: "ok" },
  EMA20_CROSS_BELOW_EMA50: { title: "Bearish cross", detail: "EMA20 crossed below EMA50 on the last bar.", severity: "ok" },
  RSI_MID_BULL_MOMENTUM: { title: "Bullish momentum", detail: "RSI mid-range with positive 5-bar momentum.", severity: "ok" },
  RSI_MID_BEAR_MOMENTUM: { title: "Bearish momentum", detail: "RSI mid-range with negative 5-bar momentum.", severity: "ok" },
  RSI_OVERBOUGHT_CAUTION: { title: "Overbought caution", detail: "RSI ≥ 70 — exhaustion risk, not an automatic sell.", severity: "warn" },
  RSI_OVERSOLD_CAUTION: { title: "Oversold caution", detail: "RSI ≤ 30 — exhaustion risk, not an automatic buy.", severity: "warn" },
  PRICE_UP_RSI_RISING: { title: "Price up, RSI rising", detail: "Momentum confirmation.", severity: "ok" },
  PRICE_DOWN_RSI_FALLING: { title: "Price down, RSI falling", detail: "Momentum confirmation.", severity: "ok" },
  MOMENTUM_FLAT: { title: "Flat momentum", detail: "No directional momentum evidence.", severity: "info" },
  VOLUME_CONFIRMED: { title: "Volume confirmed", detail: "Last volume at or above 80% of the 20-bar average.", severity: "ok" },
  VOLUME_WEAK_OR_UNAVAILABLE: { title: "Weak volume", detail: "Volume below average or unavailable.", severity: "info" },
  VOLUME_EXPANSION_UP: { title: "Volume expansion up", detail: "Relative volume ≥ 1.4× with a rising close.", severity: "ok" },
  VOLUME_EXPANSION_DOWN: { title: "Volume expansion down", detail: "Relative volume ≥ 1.4× with a falling close.", severity: "ok" },
  VOLUME_DRYUP: { title: "Volume dry-up", detail: "Relative volume below 0.7×.", severity: "info" },
  VOLUME_NEUTRAL: { title: "Neutral volume", detail: "No volume edge either way.", severity: "info" },
  SWING_HH_HL: { title: "Higher highs / higher lows", detail: "Bullish swing structure.", severity: "ok" },
  SWING_LH_LL: { title: "Lower highs / lower lows", detail: "Bearish swing structure.", severity: "ok" },
  SWING_MIXED: { title: "Mixed swings", detail: "No clear swing structure.", severity: "info" },
  STRUCTURE_UNCLEAR: { title: "Structure unclear", detail: "Fewer than two swing highs/lows in the window.", severity: "info" },
  RANGE_BREAK_UP: { title: "Range break up", detail: "Close above the 10-bar range high with bullish structure.", severity: "ok" },
  RANGE_BREAK_DOWN: { title: "Range break down", detail: "Close below the 10-bar range low with bearish structure.", severity: "ok" },
  INSIDE_RECENT_RANGE: { title: "Inside range", detail: "Close is inside the recent 10-bar range.", severity: "info" },
  AGENT_TIMEOUT: { title: "Agent timed out", detail: "The agent exceeded its time budget and failed closed.", severity: "warn" },
  AGENT_EXCEPTION: { title: "Agent error", detail: "The agent raised an error and failed closed.", severity: "warn" },

  // Orchestrator / API
  prompt_injection_refused: { title: "Request refused", detail: "The message matched a prompt-injection pattern.", severity: "block" },
  live_escalation_refused: { title: "Live escalation refused", detail: "Live env flags and silent auto-submit cannot be changed from chat.", severity: "block" },
  tool_not_allowed: { title: "Tool not allowed", detail: "The requested tool is outside the allowlist for this mode.", severity: "block" },
  tool_arguments_invalid: { title: "Invalid arguments", detail: "The tool call had invalid or missing arguments.", severity: "warn" },
  tool_argument_forbidden: { title: "Forbidden argument", detail: "A forbidden argument (keys, leverage, live flags) was rejected.", severity: "block" },
  openai_spend_gate_closed: { title: "OpenAI spend gate closed", detail: "Paid calls are off; the local planner answered instead.", severity: "warn" },
  openai_budget_exhausted: { title: "OpenAI budget exhausted", detail: "The daily or monthly budget is used up; the local planner answered instead.", severity: "warn" },
  llm_timeout: { title: "Model timed out", detail: "OpenAI did not answer in time; the local planner answered instead.", severity: "warn" },
  llm_unavailable: { title: "Model unavailable", detail: "OpenAI could not be reached; the local planner answered instead.", severity: "warn" },
  live_gates_off: { title: "Live gates off", detail: "Live env gates are not armed — nothing was sent to Bybit.", severity: "block" },
  live_execution_disabled: { title: "Live execution disabled", detail: "The live adapter refused the call because gates are off.", severity: "block" },
  supervisor_disabled: { title: "Supervisor disabled", detail: "CRYPTONOVA_PAPER_SUPERVISOR is off on the API.", severity: "block" },
  operator_local_proxy_disabled: { title: "Operator proxy disabled", detail: "OPERATOR_LOCAL_BROWSER_PROXY_ENABLED is off on the web server.", severity: "block" },
  operator_local_only: { title: "Local only", detail: "Operator controls only work from localhost.", severity: "block" },
  api_unreachable: { title: "API unreachable", detail: "FastAPI did not respond. Start it and refresh.", severity: "block" },
  authentication_required: { title: "Sign-in required", detail: "This endpoint needs a verified session token.", severity: "block" },
  invalid_json: { title: "Invalid response", detail: "The API returned a response that could not be parsed.", severity: "warn" },
};

function humanize(code: string): string {
  return code
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function explainReason(code: string | null | undefined): ReasonExplanation {
  const key = String(code ?? "").trim();
  if (!key) return { code: "", title: "—", detail: "", severity: "info" };
  const hit = CATALOG[key] ?? CATALOG[key.toUpperCase()] ?? CATALOG[key.toLowerCase()];
  if (hit) return { code: key, ...hit };
  return { code: key, title: humanize(key), detail: "", severity: "info" };
}

export function explainReasons(codes: readonly unknown[] | null | undefined): ReasonExplanation[] {
  if (!Array.isArray(codes)) return [];
  const seen = new Set<string>();
  const out: ReasonExplanation[] = [];
  for (const raw of codes) {
    const code = String(raw ?? "").trim();
    if (!code || seen.has(code)) continue;
    seen.add(code);
    out.push(explainReason(code));
  }
  return out;
}

/** The most severe reason first — useful for a one-line "why". */
export function primaryReason(codes: readonly unknown[] | null | undefined): ReasonExplanation | null {
  const rank: Record<ReasonSeverity, number> = { block: 0, warn: 1, info: 2, ok: 3 };
  const list = explainReasons(codes);
  if (list.length === 0) return null;
  return [...list].sort((a, b) => rank[a.severity] - rank[b.severity])[0];
}
