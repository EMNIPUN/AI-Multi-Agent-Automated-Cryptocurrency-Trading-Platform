"""Trend Agent — deterministic EMA20/50/200 structure (signals only)."""

from __future__ import annotations

from agent.market_data import ema
from agent.multi_agent.types import AgentContribution, MarketSnapshot, TrendBias

AGENT_ID = "trend"
AGENT_VERSION = "4A.1"


def _last(vals: list[float | None]) -> float | None:
    for v in reversed(vals):
        if v is not None:
            return float(v)
    return None


def evaluate_trend(snapshot: MarketSnapshot, *, news_context=None) -> AgentContribution:
    from agent.multi_agent.news_advisory import with_news_observation

    return with_news_observation(
        _evaluate_trend_core(snapshot),
        news_context,
        enabled=news_context is not None,
    )


def _evaluate_trend_core(snapshot: MarketSnapshot) -> AgentContribution:
    closes = list(snapshot.closes)
    if len(closes) < 210:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=TrendBias.INSUFFICIENT_DATA.value,
            confidence=0.0,
            reason_codes=("INSUFFICIENT_DATA",),
            explanation="Need ≥210 confirmed closes for EMA200 alignment",
            indicators={"bar_count": len(closes)},
        )

    e20 = ema(closes, 20)
    e50 = ema(closes, 50)
    e200 = ema(closes, 200)
    v20, v50, v200 = _last(e20), _last(e50), _last(e200)
    price = closes[-1]
    if v20 is None or v50 is None or v200 is None:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=TrendBias.INSUFFICIENT_DATA.value,
            confidence=0.0,
            reason_codes=("INDICATORS_WARMING",),
            explanation="EMA series not ready",
            indicators={},
        )

    # Prior bar EMAs for crossover state
    i = len(closes) - 1
    prev = i - 1
    cross_up = (
        e20[prev] is not None
        and e50[prev] is not None
        and e20[prev] <= e50[prev]
        and v20 > v50
    )
    cross_down = (
        e20[prev] is not None
        and e50[prev] is not None
        and e20[prev] >= e50[prev]
        and v20 < v50
    )

    stacked_bull = v20 > v50 > v200 and price > v20
    stacked_bear = v20 < v50 < v200 and price < v20
    price_above_200 = price > v200
    price_below_200 = price < v200

    reasons: list[str] = []
    if stacked_bull:
        bias = TrendBias.BULLISH
        reasons.append("EMA_STACK_BULL")
        conf = 0.85
    elif stacked_bear:
        bias = TrendBias.BEARISH
        reasons.append("EMA_STACK_BEAR")
        conf = 0.85
    elif price_above_200 and v20 > v50:
        bias = TrendBias.BULLISH
        reasons.append("PRICE_ABOVE_EMA200_FAST_ABOVE_SLOW")
        conf = 0.55
    elif price_below_200 and v20 < v50:
        bias = TrendBias.BEARISH
        reasons.append("PRICE_BELOW_EMA200_FAST_BELOW_SLOW")
        conf = 0.55
    else:
        bias = TrendBias.NEUTRAL
        reasons.append("MIXED_STRUCTURE")
        conf = 0.25

    if cross_up:
        reasons.append("EMA20_CROSS_ABOVE_EMA50")
        if bias is TrendBias.BEARISH:
            bias = TrendBias.NEUTRAL
            conf = 0.3
        else:
            conf = min(1.0, conf + 0.1)
    if cross_down:
        reasons.append("EMA20_CROSS_BELOW_EMA50")
        if bias is TrendBias.BULLISH:
            bias = TrendBias.NEUTRAL
            conf = 0.3
        else:
            conf = min(1.0, conf + 0.1)

    return AgentContribution(
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        bias=bias.value,
        confidence=conf,
        reason_codes=tuple(reasons),
        explanation=(
            f"price={price:.6g} EMA20={v20:.6g} EMA50={v50:.6g} EMA200={v200:.6g}"
        ),
        indicators={
            "ema_20": v20,
            "ema_50": v50,
            "ema_200": v200,
            "price": price,
            "cross_up": cross_up,
            "cross_down": cross_down,
            "stacked_bull": stacked_bull,
            "stacked_bear": stacked_bear,
        },
    )
