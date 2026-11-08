# Phase 4A — Risk Controls (Paper / Signals)

## Authority

`SignalRiskAgent` (`agent/multi_agent/risk_agent.py`) is independent of live `RiskManager`.

It **never** reads:

- Live Bybit balances
- Live positions
- Wallet proxy endpoints
- Binding credentials

Paper balance default: `10_000` (configurable).

## Fail-closed checks

| Check | Effect |
|-------|--------|
| Stale / invalid market | VETO |
| Duplicate idempotent key | VETO |
| Cooldown active | VETO |
| ATR unavailable | VETO |
| ATR/price > max | VETO (`VOLATILITY_FILTER`) |
| Risk/reward below min | VETO |
| BUY vs BEARISH trend | VETO |
| SELL vs BULLISH trend | VETO |
| Daily hypothetical loss ≥ halt fraction | HALTED |

## Sizing (hypothetical)

```
risk_budget = paper_balance * max_risk_fraction_per_trade
position_notional = risk_budget / stop_distance_pct
```

## Coordinator rule

Risk **VETO** or **HALTED** always forces final action `BLOCKED`.

No LLM, score, or UI control may override a Risk veto.

## Kill switches (must remain)

- `AGENT_ALLOW_LIVE=false`
- `AGENT_DRY_RUN=true` (legacy runner)
- `PRIVATE_DATA_READS_ENABLED=false`
- Binding persistence flags false
- FastAPI `trading_endpoints: false`
