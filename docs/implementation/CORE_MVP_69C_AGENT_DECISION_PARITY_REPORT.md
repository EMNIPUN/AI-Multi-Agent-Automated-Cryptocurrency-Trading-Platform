# Agent Decision Parity (69C)

The technical path is unchanged:

Market snapshot → Trend → Momentum → Coordinator proposal → Risk veto → final action.

News is attached only as `indicators["news_observation"]` and `decision.news_advisory`. Those fields are not inputs to EMA, RSI, conviction, thresholds, position notional, or risk verdicts.

## Proof

`tests/test_core_news_69c.py::test_advisory_disabled_by_default_and_decision_parity` evaluates the same candles three ways:

| Run | News | Action / risk / strength |
| --- | --- | --- |
| Advisory off | Not consulted | Baseline |
| Advisory on with a CRITICAL negative event | Observation recorded | Identical to baseline |
| Advisory on and the context loader raises | Storage marked unavailable | Identical to baseline |

`news_changed_decision` is false in the public decision payload. `execution_allowed` stays false. `AGENT_ALLOW_LIVE` stays false.

Market, Trend, and Momentum biases match the advisory-off run. Risk `position_notional` matches. Sentiment conflicts are recorded as text and do not veto or resize.
