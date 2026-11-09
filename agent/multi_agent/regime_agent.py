"""Deterministic market-regime evidence from confirmed bars only.

These statistics describe observed prices. They are not a prediction model or
a calibrated probability of a profitable trade.
"""

from __future__ import annotations

import math
import statistics

from agent.multi_agent.config import RegimeConfig
from agent.multi_agent.types import AgentContribution, MarketSnapshot


def evaluate_regime(
    snapshot: MarketSnapshot, config: RegimeConfig, *, max_atr_pct: float
) -> AgentContribution:
    lookback = config.lookback
    if not snapshot.valid or len(snapshot.candles) < lookback + 1:
        return AgentContribution(
            agent_id="regime", agent_version="1.0.0", bias="INSUFFICIENT_DATA",
            confidence=0.0, reason_codes=("REGIME_UNAVAILABLE",),
            explanation="Regime needs a valid, continuous confirmed-candle window.",
            indicators={"regime": "UNAVAILABLE", "lookback": lookback},
        )

    bars = snapshot.candles[-(lookback + 1):]
    closes = [bar.close for bar in bars]
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    path = sum(abs(change) for change in changes)
    net = closes[-1] - closes[0]
    efficiency = abs(net) / path if path > 0 else 0.0
    returns = [math.log(current / previous) for previous, current in zip(closes, closes[1:])]
    volatility = statistics.pstdev(returns)
    true_ranges = [
        max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close))
        for previous, current in zip(bars, bars[1:])
    ]
    atr_pct = statistics.fmean(true_ranges) / closes[-1]
    if efficiency >= config.trend_efficiency:
        structure = "TRENDING"
        bias = "BULLISH" if net > 0 else "BEARISH"
    elif efficiency <= config.range_efficiency:
        structure, bias = "RANGING", "NEUTRAL"
    else:
        structure, bias = "TRANSITIONAL", "NEUTRAL"
    regime = "HIGH_VOLATILITY" if atr_pct > max_atr_pct else structure
    return AgentContribution(
        agent_id="regime", agent_version="1.0.0", bias=bias,
        confidence=efficiency if bias != "NEUTRAL" else 0.0,
        reason_codes=(f"REGIME_{regime}",),
        explanation=(
            f"{regime}: {lookback}-bar efficiency={efficiency:.3f}, "
            f"ATR/price={atr_pct:.3%}, observed return={net / closes[0]:.3%}."
        ),
        indicators={
            "regime": regime, "structure": structure, "lookback": lookback,
            "efficiency_ratio": efficiency, "atr_pct": atr_pct,
            "realized_volatility_per_bar": volatility,
            "observed_return": net / closes[0],
            "score_kind": "descriptive_not_probability",
        },
    )
