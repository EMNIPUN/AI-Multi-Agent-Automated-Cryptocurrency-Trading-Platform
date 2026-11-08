"""Signal Risk Agent — paper capital only; can veto; never touches live balances."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.multi_agent.config import PaperRiskConfig
from agent.multi_agent.types import (
    DecisionAction,
    MarketSnapshot,
    RiskAssessment,
    RiskVerdict,
    TrendBias,
)

AGENT_ID = "signal_risk"
AGENT_VERSION = "4A.1"


@dataclass
class SignalRiskState:
    """In-process paper risk memory (not exchange state)."""

    day_key: str = ""
    hypothetical_day_pnl: float = 0.0
    last_signal_key: str = ""
    last_signal_ms: int = 0
    halted: bool = False
    seen_keys: set[str] = field(default_factory=set)


def _atr_pct(snapshot: MarketSnapshot, lookback: int) -> float | None:
    bars = snapshot.candles
    if len(bars) < lookback + 1:
        return None
    trs: list[float] = []
    for i in range(-lookback, 0):
        cur = bars[i]
        prev = bars[i - 1]
        tr = max(
            cur.high - cur.low,
            abs(cur.high - prev.close),
            abs(cur.low - prev.close),
        )
        trs.append(tr)
    atr = sum(trs) / len(trs)
    if snapshot.last_price <= 0:
        return None
    return atr / snapshot.last_price


def evaluate_signal_risk(
    *,
    snapshot: MarketSnapshot,
    proposed: DecisionAction,
    trend_bias: str,
    idempotent_key: str,
    config: PaperRiskConfig,
    state: SignalRiskState,
    now_ms: int,
    news_context=None,
) -> RiskAssessment:
    from agent.multi_agent.news_advisory import with_risk_observation

    assessment = _evaluate_signal_risk_core(
        snapshot=snapshot,
        proposed=proposed,
        trend_bias=trend_bias,
        idempotent_key=idempotent_key,
        config=config,
        state=state,
        now_ms=now_ms,
    )
    return with_risk_observation(assessment, news_context, enabled=news_context is not None)


def _evaluate_signal_risk_core(
    *,
    snapshot: MarketSnapshot,
    proposed: DecisionAction,
    trend_bias: str,
    idempotent_key: str,
    config: PaperRiskConfig,
    state: SignalRiskState,
    now_ms: int,
) -> RiskAssessment:
    reasons: list[str] = []
    paper = config.paper_balance

    if state.halted or abs(state.hypothetical_day_pnl) >= paper * config.daily_loss_halt_fraction:
        state.halted = True
        return RiskAssessment(
            verdict=RiskVerdict.HALTED,
            reason_codes=("DAILY_HYPOTHETICAL_LOSS_HALT",),
            explanation="Paper daily loss limit reached — fail closed",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=None,
            reward_distance_pct=None,
            risk_reward=None,
            indicators={"day_pnl": state.hypothetical_day_pnl},
        )

    if not snapshot.valid or not snapshot.data_fresh:
        reasons.append("STALE_OR_INVALID_MARKET")
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=tuple(reasons),
            explanation="Market snapshot not fresh/valid",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=None,
            reward_distance_pct=None,
            risk_reward=None,
        )

    if proposed in {DecisionAction.HOLD, DecisionAction.BLOCKED}:
        return RiskAssessment(
            verdict=RiskVerdict.APPROVED,
            reason_codes=("NO_TRADE_PROPOSAL",),
            explanation="HOLD/BLOCKED — no new exposure sizing required",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=0.0,
            stop_distance_pct=None,
            reward_distance_pct=None,
            risk_reward=None,
        )

    if idempotent_key and idempotent_key in state.seen_keys:
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=("DUPLICATE_SIGNAL",),
            explanation="Duplicate idempotent key suppressed",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=None,
            reward_distance_pct=None,
            risk_reward=None,
        )

    cooldown_left = state.last_signal_ms + config.cooldown_ms - now_ms
    if state.last_signal_ms and cooldown_left > 0:
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=("COOLDOWN_ACTIVE",),
            explanation=f"Cooldown {cooldown_left}ms remaining",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=None,
            reward_distance_pct=None,
            risk_reward=None,
            cooldown_remaining_ms=cooldown_left,
        )

    atr_pct = _atr_pct(snapshot, config.atr_lookback)
    if atr_pct is None:
        reasons.append("ATR_UNAVAILABLE")
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=tuple(reasons),
            explanation="Cannot size stop without ATR",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=None,
            reward_distance_pct=None,
            risk_reward=None,
        )

    if atr_pct > config.max_atr_pct:
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=("VOLATILITY_FILTER",),
            explanation=f"ATR/price {atr_pct:.4%} exceeds max {config.max_atr_pct:.4%}",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=atr_pct,
            reward_distance_pct=None,
            risk_reward=None,
            indicators={"atr_pct": atr_pct},
        )

    stop_pct = min(
        config.max_stop_distance_pct,
        max(config.min_stop_distance_pct, atr_pct * 1.2),
    )
    reward_pct = stop_pct * config.take_profit_rr
    rr = reward_pct / stop_pct if stop_pct > 0 else 0.0
    if rr < config.min_risk_reward:
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=("RISK_REWARD_BELOW_MIN",),
            explanation=f"RR {rr:.2f} < min {config.min_risk_reward}",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=stop_pct,
            reward_distance_pct=reward_pct,
            risk_reward=rr,
        )

    # Trend disagreement soft veto for aggressive proposals
    if proposed is DecisionAction.BUY and trend_bias == TrendBias.BEARISH.value:
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=("TREND_CONFLICT_VETO",),
            explanation="BUY vetoed against BEARISH trend",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=stop_pct,
            reward_distance_pct=reward_pct,
            risk_reward=rr,
        )
    if proposed is DecisionAction.SELL and trend_bias == TrendBias.BULLISH.value:
        return RiskAssessment(
            verdict=RiskVerdict.VETO,
            reason_codes=("TREND_CONFLICT_VETO",),
            explanation="SELL vetoed against BULLISH trend",
            paper_balance=paper,
            risk_fraction=config.max_risk_fraction_per_trade,
            position_notional=None,
            stop_distance_pct=stop_pct,
            reward_distance_pct=reward_pct,
            risk_reward=rr,
        )

    risk_budget = paper * config.max_risk_fraction_per_trade
    notional = risk_budget / stop_pct if stop_pct > 0 else 0.0

    return RiskAssessment(
        verdict=RiskVerdict.APPROVED,
        reason_codes=("RISK_OK",),
        explanation="Paper sizing within limits",
        paper_balance=paper,
        risk_fraction=config.max_risk_fraction_per_trade,
        position_notional=notional,
        stop_distance_pct=stop_pct,
        reward_distance_pct=reward_pct,
        risk_reward=rr,
        indicators={"atr_pct": atr_pct, "risk_budget": risk_budget},
    )


def remember_approved_signal(state: SignalRiskState, *, key: str, now_ms: int) -> None:
    if key:
        state.seen_keys.add(key)
        state.last_signal_key = key
        state.last_signal_ms = now_ms


def record_hypothetical_pnl(state: SignalRiskState, pnl: float, *, day_key: str) -> None:
    if state.day_key != day_key:
        state.day_key = day_key
        state.hypothetical_day_pnl = 0.0
        state.halted = False
    state.hypothetical_day_pnl += pnl
