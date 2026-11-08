# Phase 4B — Strategy Validation

## Finding (4A scoring bias)

4A formula:

```text
score = trend_signed*0.45 + momentum_signed*0.35 + market_quality*0.20
```

When market data was `OK`, `market_quality` contributed **+0.20** to the score regardless of direction. That is a structural bullish bias (a healthy market made BUY easier than SELL for equal-magnitude trend/momentum).

## 4B.1.0 model (intentional change)

Separated concerns:

| Component | Range | Role |
|-----------|-------|------|
| `directional_conviction` | [-1, 1] | Trend + momentum only (renormalized weights 0.56 / 0.44) |
| `market_quality` | [0, 1] | Gate only — never added as signed bias |
| Risk eligibility | APPROVED / VETO / HALTED | Independent paper Risk Agent |

```text
directional = trend_signed*w_t + momentum_signed*w_m
if market_quality < min_market_quality → BLOCKED
else use directional vs buy/sell thresholds
signal_strength = |directional| × market_quality
```

Strategy version bumped: **`4A.1.0` → `4B.1.0`**.

## Claims boundary

This change improves **directional symmetry** of the decision rule. It does **not** claim profitability, edge, win rate, or Sharpe. Those require outcome evaluation / backtesting (out of scope for 4B).
