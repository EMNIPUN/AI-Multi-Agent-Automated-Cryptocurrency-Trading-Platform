"""Structure Agent — swing HH/HL vs LH/LL and range break/fail (signals only)."""

from __future__ import annotations

from agent.multi_agent.types import AgentContribution, MarketSnapshot, TrendBias

AGENT_ID = "structure"
AGENT_VERSION = "6.0.0"


def _swing_points(highs: list[float], lows: list[float], *, wing: int = 2) -> tuple[list[float], list[float]]:
    """Return recent swing highs/lows using a simple fractal wing."""
    swing_highs: list[float] = []
    swing_lows: list[float] = []
    n = len(highs)
    for i in range(wing, n - wing):
        left_h = highs[i - wing : i]
        right_h = highs[i + 1 : i + 1 + wing]
        left_l = lows[i - wing : i]
        right_l = lows[i + 1 : i + 1 + wing]
        if highs[i] >= max(left_h) and highs[i] >= max(right_h):
            swing_highs.append(highs[i])
        if lows[i] <= min(left_l) and lows[i] <= min(right_l):
            swing_lows.append(lows[i])
    return swing_highs, swing_lows


def evaluate_structure(snapshot: MarketSnapshot, *, lookback: int = 40) -> AgentContribution:
    candles = list(snapshot.candles)
    if len(candles) < lookback:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=TrendBias.INSUFFICIENT_DATA.value,
            confidence=0.0,
            reason_codes=("INSUFFICIENT_DATA",),
            explanation=f"Need ≥{lookback} confirmed bars for swing structure",
            indicators={"bar_count": len(candles), "lookback": lookback},
        )

    window = candles[-lookback:]
    highs = [c.high for c in window]
    lows = [c.low for c in window]
    closes = [c.close for c in window]
    swing_highs, swing_lows = _swing_points(highs, lows, wing=2)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return AgentContribution(
            agent_id=AGENT_ID,
            agent_version=AGENT_VERSION,
            bias=TrendBias.NEUTRAL.value,
            confidence=0.2,
            reason_codes=("STRUCTURE_UNCLEAR",),
            explanation="Fewer than two swing highs/lows — structure unclear",
            indicators={
                "swing_high_count": len(swing_highs),
                "swing_low_count": len(swing_lows),
                "lookback": lookback,
            },
        )

    sh1, sh0 = swing_highs[-2], swing_highs[-1]
    sl1, sl0 = swing_lows[-2], swing_lows[-1]
    hh = sh0 > sh1
    hl = sl0 > sl1
    lh = sh0 < sh1
    ll = sl0 < sl1
    last = closes[-1]
    range_high = max(highs[-10:])
    range_low = min(lows[-10:])
    reasons: list[str] = []

    if hh and hl:
        bias = TrendBias.BULLISH
        conf = 0.65
        reasons.append("SWING_HH_HL")
    elif lh and ll:
        bias = TrendBias.BEARISH
        conf = 0.65
        reasons.append("SWING_LH_LL")
    elif hh and not hl:
        bias = TrendBias.NEUTRAL
        conf = 0.35
        reasons.append("SWING_HH_WITHOUT_HL")
    elif ll and not lh:
        bias = TrendBias.NEUTRAL
        conf = 0.35
        reasons.append("SWING_LL_WITHOUT_LH")
    else:
        bias = TrendBias.NEUTRAL
        conf = 0.3
        reasons.append("SWING_MIXED")

    # Range break / fail confirmation adjusts confidence, not bias alone.
    if last > range_high and bias is TrendBias.BULLISH:
        conf = min(1.0, conf + 0.15)
        reasons.append("RANGE_BREAK_UP")
    elif last < range_low and bias is TrendBias.BEARISH:
        conf = min(1.0, conf + 0.15)
        reasons.append("RANGE_BREAK_DOWN")
    elif last > range_high and bias is not TrendBias.BULLISH:
        reasons.append("RANGE_BREAK_UP_UNCONFIRMED")
        conf = max(0.2, conf - 0.1)
    elif last < range_low and bias is not TrendBias.BEARISH:
        reasons.append("RANGE_BREAK_DOWN_UNCONFIRMED")
        conf = max(0.2, conf - 0.1)
    else:
        reasons.append("INSIDE_RECENT_RANGE")

    return AgentContribution(
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        bias=bias.value,
        confidence=conf,
        reason_codes=tuple(reasons),
        explanation=(
            f"structure={reasons[0]} last={last:.6g} "
            f"swings H:{sh1:.6g}->{sh0:.6g} L:{sl1:.6g}->{sl0:.6g}"
        ),
        indicators={
            "hh": hh,
            "hl": hl,
            "lh": lh,
            "ll": ll,
            "last_swing_high": sh0,
            "prev_swing_high": sh1,
            "last_swing_low": sl0,
            "prev_swing_low": sl1,
            "range_high_10": range_high,
            "range_low_10": range_low,
            "lookback": lookback,
            "score_kind": "descriptive_not_probability",
        },
    )
