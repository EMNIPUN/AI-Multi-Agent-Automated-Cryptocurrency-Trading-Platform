# Phase 4A — Strategy Specification

## Strategy version

`4A.1.0`

## Market Data Agent

- Input: raw OHLCV list + symbol + category (`spot`|`linear`) + interval + `now_ms`
- Uses `filter_confirmed_candles` (forming bars excluded)
- Rejects invalid category, malformed OHLCV, insufficient bars, stale series
- Output: immutable `MarketSnapshot` + contribution (`OK` / `DEGRADED` / `INVALID`)

## Trend Agent

Indicators: EMA20, EMA50, EMA200 on confirmed closes only.

| Bias | Rule (summary) |
|------|----------------|
| BULLISH | EMA stack `20>50>200` and price `> EMA20`, or price above EMA200 with fast>slow |
| BEARISH | Inverse stack / price below EMA200 with fast<slow |
| NEUTRAL | Mixed structure or conflicting cross |
| INSUFFICIENT_DATA | `<210` bars or EMA not ready |

Cross annotations: `EMA20_CROSS_ABOVE_EMA50` / `EMA20_CROSS_BELOW_EMA50`.

## Momentum Agent

- RSI14 level + slope
- 5-bar price momentum
- Optional volume confirmation vs 20-bar average

**Important:** RSI overbought/oversold alone is never an automatic BUY/SELL. Those regimes emit caution codes (`RSI_OVERBOUGHT_CAUTION` / `RSI_OVERSOLD_CAUTION`).

## Coordinator

Weights (default, normalized): Trend `0.45`, Momentum `0.35`, Market quality `0.20`.

```
score = trend_signed*w_t + momentum_signed*w_m + market_quality*w_q
```

- `score >= buy_threshold` (default `0.35`) → propose BUY (unless trend BEARISH)
- `score <= sell_threshold` (default `-0.35`) → propose SELL (unless trend BULLISH)
- else HOLD
- Trend/momentum conflict on a directional proposal → HOLD
- Invalid market → BLOCKED before risk

`signal_strength = abs(score)` clipped to `[0,1]` — **qualitative agreement**, not win probability.

## Hypothetical levels

When a directional proposal is risk-approved:

- Entry ≈ last confirmed close
- Stop distance from ATR-based paper risk config
- Take profit at configured RR multiple (default 2.0)

Levels remain labeled hypothetical / not an order even if later BLOCKED for display audit.
