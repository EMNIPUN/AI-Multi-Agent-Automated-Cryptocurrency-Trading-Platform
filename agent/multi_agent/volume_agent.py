"""Volume Agent — relative volume and price/volume agreement (signals only)."""

from __future__ import annotations

from agent.multi_agent.types import AgentContribution, MarketSnapshot, MomentumBias

AGENT_ID = "volume"
AGENT_VERSION = "6.0.0"


def evaluate_volume(snapshot: MarketSnapshot) -> AgentContribution:
    volumes = list(snapshot.volumes)
    closes = list(snapshot.closes)
    lookback = 20
    if len(volumes) < lookback + 1 or len(closes) < lookback + 1:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=MomentumBias.INSUFFICIENT_DATA.value,
            confidence=0.0,
            reason_codes=("INSUFFICIENT_DATA",),
            explanation=f"Need ≥{lookback + 1} confirmed bars for relative volume",
            indicators={"bar_count": min(len(volumes), len(closes))},
        )

    window = volumes[-(lookback + 1) : -1]
    avg = sum(window) / float(lookback)
    last = volumes[-1]
    if avg <= 0:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=MomentumBias.NEUTRAL.value,
            confidence=0.2,
            reason_codes=("VOLUME_UNAVAILABLE",),
            explanation="Average volume is zero — no directional volume evidence",
            indicators={"rel_volume": 0.0, "avg_volume": avg, "last_volume": last},
        )

    rel = last / avg
    price_chg = (closes[-1] - closes[-2]) / closes[-2] if closes[-2] else 0.0
    reasons: list[str] = []

    if rel >= 1.4 and price_chg > 0.001:
        bias = MomentumBias.BULLISH
        conf = min(1.0, 0.45 + min(0.4, (rel - 1.0) * 0.25))
        reasons.append("VOLUME_EXPANSION_UP")
    elif rel >= 1.4 and price_chg < -0.001:
        bias = MomentumBias.BEARISH
        conf = min(1.0, 0.45 + min(0.4, (rel - 1.0) * 0.25))
        reasons.append("VOLUME_EXPANSION_DOWN")
    elif rel < 0.7:
        bias = MomentumBias.NEUTRAL
        conf = 0.25
        reasons.append("VOLUME_DRYUP")
    elif price_chg > 0.002 and rel >= 1.0:
        bias = MomentumBias.BULLISH
        conf = 0.4
        reasons.append("PRICE_UP_VOLUME_SUPPORT")
    elif price_chg < -0.002 and rel >= 1.0:
        bias = MomentumBias.BEARISH
        conf = 0.4
        reasons.append("PRICE_DOWN_VOLUME_SUPPORT")
    elif price_chg > 0.002 and rel < 0.9:
        bias = MomentumBias.NEUTRAL
        conf = 0.3
        reasons.append("PRICE_UP_VOLUME_DIVERGENCE")
    elif price_chg < -0.002 and rel < 0.9:
        bias = MomentumBias.NEUTRAL
        conf = 0.3
        reasons.append("PRICE_DOWN_VOLUME_DIVERGENCE")
    else:
        bias = MomentumBias.NEUTRAL
        conf = 0.25
        reasons.append("VOLUME_NEUTRAL")

    return AgentContribution(
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        bias=bias.value,
        confidence=conf,
        reason_codes=tuple(reasons),
        explanation=f"rel_vol={rel:.2f} price_chg={price_chg:.4%} ({reasons[0]})",
        indicators={
            "rel_volume": rel,
            "avg_volume": avg,
            "last_volume": last,
            "price_change": price_chg,
            "score_kind": "descriptive_not_probability",
        },
    )
