# CryptoNova 76 — Agent Validation

The pipeline under test is:

`build_market_snapshot` → `evaluate_trend` → `evaluate_momentum` → `coordinate` → `evaluate_signal_risk`

No live order path was enabled. `AGENT_ALLOW_LIVE` remained `false`.

## Deterministic coverage

Phase 4A and 4B tests cover:

- confirmed versus insufficient candles
- EMA trend bias
- RSI and momentum context, including the rule that overbought or oversold alone is not a trade
- volume and market-quality inputs to the coordinator
- coordinator BUY, SELL, HOLD, and BLOCKED outcomes
- risk veto on volatility
- HOLD when agents disagree
- BLOCKED on stale or missing data
- replay of the same candle set
- duplicate suppression
- signal persistence and restart on SQLite

Phase 4C covers confirmed-candle triggering, forming-candle rejection, checkpoint recovery, and duplicate event suppression.

## Advisory boundary

`DecisionAction` records keep `execution_allowed` false. The coordinator sets `news_changed_decision` false. The pipeline writes that flag false again after any advisory attachment. `agent/llm_intelligence/service.py` sets `llm_changed_decision` false and does not alter action, risk, size, or execution permission. Tests in `tests/test_core_llm_69d.py` and `tests/test_core_backtest_69e.py` assert those flags.

News and LLM outputs stay advisory. This phase did not call a paid model and does not claim that advice improved returns.
