# CryptoNova — Backtest Assumptions (Prompt 68A)

**Label:** HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE

## Information availability

| Rule | Behavior |
| --- | --- |
| Confirmed bars only | At candle index `N`, agents see candles `[0..N]` with `now_ms = close(N) + grace_ms` |
| No look-ahead | Candle `N+1` is never passed into indicators or agents for decision `N` |
| Entry timing | Eligible fill is the **next** confirmed candle open (65A), via `signal_candle_start_ms = N.start` |
| Marks | Missing marks are never replaced with future prices or entry prices |
| End of data | Open positions remain open; no silent force-close (`force_close_at_end=False`) |

## Execution (65A reuse)

- Spot-like unleveraged longs only; no shorts, leverage, funding, or liquidation.
- Fees charged once per fill side; adverse slippage on entries/exits.
- Same-bar SL/TP: **stop-loss first**.
- Gap through stop: executable at candle open (+ adverse slippage).
- Backtest-only **cash-cap**: signal-risk notionals larger than spendable cash are capped to `available / (1 + fee_rate)` before submit. This does not invent leverage; it prevents permanent `MAX_EXPOSURE`/`INSUFFICIENT_FUNDS` dead-ends when stop distance implies notionals above capital.

## Risk modes

| Mode | Behavior |
| --- | --- |
| `signal_only` | Existing Signal Risk Agent only |
| `portfolio` | Injects `PortfolioRiskConfig` into an isolated `PaperBroker` instance |

Global flags stay **OFF**: `PAPER_BROKER_AUTO_ATTACH`, `PAPER_PORTFOLIO_RISK_ENABLED`, `PAPER_READ_API_ENABLED`, `AGENT_ALLOW_LIVE`, `LLM_AGENTS_ENABLED`.

## Metrics (67A reuse)

Closed-trade win rate, profit factor, expectancy, fees, and observed snapshot drawdown use Prompt 67A definitions (`empty` / `unavailable` / `unbounded`). Open positions are not closed trades.

## Isolation

- Ephemeral `bt68a_*.sqlite3` journals under `data/backtests/`
- `SUPABASE_SOT_ENABLED=false` for backtest persistence
- No writes to the operator paper journal or remote SoT
- Pipeline runs with `persist=False` (no signal-history pollution)

## Known limitations

1. Optional live Bybit public pagination loader is not implemented in 68A; use fixture/inline offline datasets.
2. Observed drawdown is snapshot-based, not true intraperiod maximum.
3. Cash-cap alters notional vs raw signal-risk output when stops are tight relative to capital.
4. Thread-pooled agent evaluation inherits pipeline timeouts; pathological timeouts could differ under extreme load (not expected for offline fixtures).
