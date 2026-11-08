"""Momentum Agent — RSI14 + price/volume context (not auto BUY/SELL on OB/OS)."""

from __future__ import annotations

from agent.market_data import rsi
from agent.multi_agent.types import AgentContribution, MarketSnapshot, MomentumBias

AGENT_ID = "momentum"
AGENT_VERSION = "4A.1"


def evaluate_momentum(snapshot: MarketSnapshot, *, news_context=None) -> AgentContribution:
    from agent.multi_agent.news_advisory import with_news_observation

    return with_news_observation(
        _evaluate_momentum_core(snapshot),
        news_context,
        enabled=news_context is not None,
    )


def _evaluate_momentum_core(snapshot: MarketSnapshot) -> AgentContribution:
    closes = list(snapshot.closes)
    volumes = list(snapshot.volumes)
    if len(closes) < 30:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=MomentumBias.INSUFFICIENT_DATA.value,
            confidence=0.0,
            reason_codes=("INSUFFICIENT_DATA",),
            explanation="Need ≥30 confirmed closes for RSI/momentum",
            indicators={"bar_count": len(closes)},
        )

    series = rsi(closes, 14)
    r_now = series[-1]
    r_prev = series[-2] if len(series) > 1 else None
    if r_now is None:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=MomentumBias.INSUFFICIENT_DATA.value,
            confidence=0.0,
            reason_codes=("INDICATORS_WARMING",),
            explanation="RSI14 not ready",
            indicators={},
        )

    # Price momentum: last close vs close N bars ago
    lookback = 5
    mom = (closes[-1] - closes[-1 - lookback]) / closes[-1 - lookback] if len(closes) > lookback else 0.0

    vol_ok = False
    if len(volumes) >= 20:
        avg = sum(volumes[-20:]) / 20.0
        vol_ok = avg > 0 and volumes[-1] >= avg * 0.8

    reasons: list[str] = []
    # RSI slope / regime — never treat OB/OS alone as entry.
    rsi_rising = r_prev is not None and r_now > r_prev
    rsi_falling = r_prev is not None and r_now < r_prev

    if 45 <= r_now <= 65 and mom > 0:
        bias = MomentumBias.BULLISH
        reasons.append("RSI_MID_BULL_MOMENTUM")
        conf = 0.6
    elif 35 <= r_now <= 55 and mom < 0:
        bias = MomentumBias.BEARISH
        reasons.append("RSI_MID_BEAR_MOMENTUM")
        conf = 0.6
    elif r_now >= 70:
        # Overbought = caution / exhaustion bias, not auto SELL.
        bias = MomentumBias.NEUTRAL if mom >= 0 else MomentumBias.BEARISH
        reasons.append("RSI_OVERBOUGHT_CAUTION")
        conf = 0.35 if bias is MomentumBias.NEUTRAL else 0.45
    elif r_now <= 30:
        bias = MomentumBias.NEUTRAL if mom <= 0 else MomentumBias.BULLISH
        reasons.append("RSI_OVERSOLD_CAUTION")
        conf = 0.35 if bias is MomentumBias.NEUTRAL else 0.45
    elif mom > 0.002 and rsi_rising:
        bias = MomentumBias.BULLISH
        reasons.append("PRICE_UP_RSI_RISING")
        conf = 0.5
    elif mom < -0.002 and rsi_falling:
        bias = MomentumBias.BEARISH
        reasons.append("PRICE_DOWN_RSI_FALLING")
        conf = 0.5
    else:
        bias = MomentumBias.NEUTRAL
        reasons.append("MOMENTUM_FLAT")
        conf = 0.25

    if vol_ok:
        reasons.append("VOLUME_CONFIRMED")
        conf = min(1.0, conf + 0.05)
    else:
        reasons.append("VOLUME_WEAK_OR_UNAVAILABLE")

    return AgentContribution(
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        bias=bias.value,
        confidence=conf,
        reason_codes=tuple(reasons),
        explanation=f"RSI14={r_now:.2f} mom5={mom:.4%} vol_ok={vol_ok}",
        indicators={
            "rsi_14": r_now,
            "rsi_prev": r_prev,
            "momentum_5": mom,
            "volume_confirmed": vol_ok,
            "overbought_caution": r_now >= 70,
            "oversold_caution": r_now <= 30,
        },
    )
