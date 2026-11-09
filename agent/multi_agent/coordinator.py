"""Decision Coordinator — merges agent outputs; never overrides Risk veto."""

from __future__ import annotations

import hashlib

from agent.multi_agent.config import SignalPipelineConfig, config_hash
from agent.multi_agent.types import (
    AgentContribution,
    CoordinatorDecision,
    DecisionAction,
    HypotheticalLevels,
    MarketSnapshot,
    MomentumBias,
    RiskAssessment,
    RiskVerdict,
    TrendBias,
)

SIGNAL_STRENGTH_NOTE = (
    "signal_strength = |directional_conviction| × market_quality (0..1). "
    "When a CalibrationProfile is loaded, thresholds/weights are offline-fitted "
    "historical agreement — still not a guaranteed win probability or PnL forecast."
)


def _signed_directional(bias: str, confidence: float) -> float:
    """Map agent bias to signed conviction. Market OK is NOT directional."""
    if bias in {TrendBias.BULLISH.value, MomentumBias.BULLISH.value}:
        return max(0.0, min(1.0, confidence))
    if bias in {TrendBias.BEARISH.value, MomentumBias.BEARISH.value}:
        return -max(0.0, min(1.0, confidence))
    return 0.0


def market_quality_score(market_contrib: AgentContribution, snapshot: MarketSnapshot) -> float:
    """Non-directional data quality in [0, 1]."""
    if not snapshot.valid or not snapshot.data_fresh:
        return 0.0
    if market_contrib.bias == "OK":
        return max(0.0, min(1.0, market_contrib.confidence))
    if market_contrib.bias == "DEGRADED":
        return max(0.0, min(0.5, market_contrib.confidence * 0.5))
    return 0.0


def directional_conviction(
    trend: AgentContribution,
    momentum: AgentContribution,
    config: SignalPipelineConfig,
    volume: AgentContribution | None = None,
    structure: AgentContribution | None = None,
) -> float:
    """Symmetric directional score in [-1, 1] from trend/momentum/volume/structure."""
    weights = config.weights.normalized()
    score = (
        _signed_directional(trend.bias, trend.confidence) * weights.trend
        + _signed_directional(momentum.bias, momentum.confidence) * weights.momentum
    )
    if volume is not None:
        score += _signed_directional(volume.bias, volume.confidence) * weights.volume
    if structure is not None:
        score += _signed_directional(structure.bias, structure.confidence) * weights.structure
    return max(-1.0, min(1.0, score))


def infer_source_mode(data_path: str) -> str:
    path = (data_path or "").lower()
    if "replay" in path:
        return "REPLAY"
    if any(tok in path for tok in ("fixture", "simulated", "sample")):
        return "SIMULATED"
    if any(tok in path for tok in ("public", "live", "rest", "ws")):
        return "LIVE_PUBLIC"
    return "SIMULATED"


def _levels(
    action: DecisionAction,
    price: float,
    risk: RiskAssessment,
) -> HypotheticalLevels:
    if action not in {DecisionAction.BUY, DecisionAction.SELL}:
        return HypotheticalLevels(None, None, None)
    if risk.stop_distance_pct is None or risk.reward_distance_pct is None:
        return HypotheticalLevels(price, None, None)
    stop = risk.stop_distance_pct
    reward = risk.reward_distance_pct
    if action is DecisionAction.BUY:
        return HypotheticalLevels(
            entry=price,
            stop_loss=price * (1 - stop),
            take_profit=price * (1 + reward),
        )
    return HypotheticalLevels(
        entry=price,
        stop_loss=price * (1 + stop),
        take_profit=price * (1 - reward),
    )


def _ids(
    *,
    symbol: str,
    category: str,
    interval: str,
    close_ms: int,
    action: str,
    version: str,
) -> tuple[str, str, str]:
    base = f"{symbol}|{category}|{interval}|{close_ms}|{action}|{version}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()
    decision_id = f"dec_{digest}"
    correlation_id = f"c{digest[:24]}"
    idempotent_key = f"idem_{digest}"
    return decision_id, correlation_id, idempotent_key


def coordinate(
    *,
    snapshot: MarketSnapshot,
    market_contrib: AgentContribution,
    trend: AgentContribution,
    momentum: AgentContribution,
    config: SignalPipelineConfig,
    risk_fn,
    risk_state,
    news_advisory: dict | None = None,
    regime: AgentContribution | None = None,
    volume: AgentContribution | None = None,
    structure: AgentContribution | None = None,
) -> CoordinatorDecision:
    """
    Explicit order already applied by caller:
    Market → Trend/Momentum/Volume/Structure → (propose) → Risk → finalize.

    Scoring (6.0.0):
    - directional_conviction ∈ [-1, 1] from trend + momentum + volume + structure
    - market_quality ∈ [0, 1] is a gate, never added as bullish bias
    - regime remains a confirmation/abstention gate (not a directional weight)
    - risk eligibility is independent (Risk Agent)
    """
    conviction = directional_conviction(trend, momentum, config, volume=volume, structure=structure)
    quality = market_quality_score(market_contrib, snapshot)
    source_mode = infer_source_mode(snapshot.data_path)
    cfg_hash = config_hash(config)

    if not snapshot.valid or quality < config.min_market_quality:
        proposed = DecisionAction.BLOCKED
        reason = ("MARKET_QUALITY_GATE", *snapshot.reason_codes)
        explanation = "Blocked: market quality below gate (non-directional)"
    elif trend.bias == TrendBias.INSUFFICIENT_DATA.value or momentum.bias == MomentumBias.INSUFFICIENT_DATA.value:
        proposed = DecisionAction.HOLD
        reason = ("INSUFFICIENT_DATA",)
        explanation = "HOLD: insufficient indicator history"
    elif conviction >= config.buy_threshold and trend.bias != TrendBias.BEARISH.value:
        proposed = DecisionAction.BUY
        reason = ("COORD_BUY",)
        explanation = f"Directional conviction {conviction:.3f} ≥ buy threshold"
    elif conviction <= config.sell_threshold and trend.bias != TrendBias.BULLISH.value:
        proposed = DecisionAction.SELL
        reason = ("COORD_SELL",)
        explanation = f"Directional conviction {conviction:.3f} ≤ sell threshold"
    else:
        proposed = DecisionAction.HOLD
        reason = ("COORD_HOLD",)
        explanation = f"Directional conviction {conviction:.3f} in neutral band"

    # Conflicting core agents → prefer HOLD before risk
    if (
        trend.bias == TrendBias.BULLISH.value
        and momentum.bias == MomentumBias.BEARISH.value
        and proposed is DecisionAction.BUY
    ) or (
        trend.bias == TrendBias.BEARISH.value
        and momentum.bias == MomentumBias.BULLISH.value
        and proposed is DecisionAction.SELL
    ):
        proposed = DecisionAction.HOLD
        reason = ("AGENT_CONFLICT",)
        explanation = "HOLD: trend/momentum conflict"

    # Regime is a confirmation/abstention agent, never an extra directional
    # weight. Volume/structure participate in conviction + consensus counts.
    scored = (trend, momentum)
    if volume is not None:
        scored = (*scored, volume)
    if structure is not None:
        scored = (*scored, structure)
    directional_agents = scored + ((regime,) if regime is not None else ())
    desired_bias = "BULLISH" if conviction > 0 else "BEARISH" if conviction < 0 else "NEUTRAL"
    opposite_bias = "BEARISH" if desired_bias == "BULLISH" else "BULLISH" if desired_bias == "BEARISH" else ""
    supporting = [c.agent_id for c in directional_agents if c.bias == desired_bias and desired_bias != "NEUTRAL"]
    opposing = [c.agent_id for c in directional_agents if c.bias == opposite_bias]
    neutral = [c.agent_id for c in directional_agents if c.bias not in {"BULLISH", "BEARISH"}]
    regime_name = regime.indicators.get("regime", "UNAVAILABLE") if regime else "UNAVAILABLE"
    before_regime = proposed.value
    if config.regime.enabled and proposed in {DecisionAction.BUY, DecisionAction.SELL}:
        if regime is None or regime.bias == "INSUFFICIENT_DATA" or regime.error or regime.timed_out:
            proposed = DecisionAction.HOLD
            reason = ("REGIME_UNAVAILABLE",)
            explanation = "HOLD: regime confirmation unavailable"
        elif regime.indicators.get("structure") == "RANGING":
            proposed = DecisionAction.HOLD
            reason = ("RANGING_MARKET_ABSTENTION",)
            explanation = "HOLD: trend strategy abstains in a ranging market"
        elif opposing:
            proposed = DecisionAction.HOLD
            reason = ("AGENT_CONFLICT",)
            explanation = "HOLD: directional agents disagree (" + ", ".join(opposing) + ")"
        elif len(supporting) < config.regime.minimum_supporting_agents:
            proposed = DecisionAction.HOLD
            reason = ("CONSENSUS_INSUFFICIENT",)
            explanation = (
                f"HOLD: {len(supporting)} supporting agents; "
                f"{config.regime.minimum_supporting_agents} required"
            )

    decision_id, correlation_id, idempotent_key = _ids(
        symbol=snapshot.symbol,
        category=snapshot.category.value,
        interval=snapshot.interval,
        close_ms=snapshot.newest_close_ms,
        action=proposed.value,
        version=config.strategy_version,
    )

    risk: RiskAssessment = risk_fn(
        snapshot=snapshot,
        proposed=proposed,
        trend_bias=trend.bias,
        idempotent_key=idempotent_key if proposed in {DecisionAction.BUY, DecisionAction.SELL} else "",
        config=config.risk,
        state=risk_state,
        now_ms=snapshot.as_of_ms,
    )

    final = proposed
    final_reasons = list(reason)
    if risk.verdict is RiskVerdict.VETO and proposed in {DecisionAction.BUY, DecisionAction.SELL}:
        final = DecisionAction.BLOCKED
        final_reasons.extend(risk.reason_codes)
        explanation = f"BLOCKED by Risk Agent: {risk.explanation}"
    elif risk.verdict is RiskVerdict.HALTED:
        final = DecisionAction.BLOCKED
        final_reasons.extend(risk.reason_codes)
        explanation = f"BLOCKED: {risk.explanation}"

    strength = max(0.0, min(1.0, abs(conviction) * quality))
    levels = _levels(
        final if final in {DecisionAction.BUY, DecisionAction.SELL} else proposed,
        snapshot.last_price,
        risk,
    )
    if final is DecisionAction.BLOCKED:
        levels = HypotheticalLevels(
            entry=levels.entry,
            stop_loss=levels.stop_loss,
            take_profit=levels.take_profit,
            note="Hypothetical levels shown for audit only — signal BLOCKED, not an order",
        )

    return CoordinatorDecision(
        action=final,
        symbol=snapshot.symbol,
        category=snapshot.category.value,
        interval=snapshot.interval,
        timestamp_ms=snapshot.as_of_ms,
        strategy_version=config.strategy_version,
        correlation_id=correlation_id,
        decision_id=decision_id,
        signal_strength=strength,
        signal_strength_note=SIGNAL_STRENGTH_NOTE,
        contributions=(market_contrib, *directional_agents),
        risk=risk,
        reason_codes=tuple(final_reasons),
        explanation=explanation,
        levels=levels,
        market=snapshot,
        idempotent_key=idempotent_key,
        directional_conviction=conviction,
        market_quality=quality,
        config_hash=cfg_hash,
        source_mode=source_mode,
        execution_allowed=False,
        news_advisory=news_advisory,
        news_changed_decision=False,
        decision_context={
            "market_regime": regime_name,
            "regime_filter_enabled": config.regime.enabled,
            "proposal_before_regime": before_regime,
            "calibration_profile_id": config.calibration_profile_id,
            "calibration_hash": config.calibration_hash,
            "consensus": {
                "direction": desired_bias,
                "supporting_agents": supporting,
                "opposing_agents": opposing,
                "neutral_agents": neutral,
                "minimum_support": config.regime.minimum_supporting_agents,
                "agreement_ratio": (
                    len(supporting) / len(directional_agents) if directional_agents else 0.0
                ),
                "score_kind": (
                    "calibrated_historical_agreement"
                    if config.calibration_profile_id
                    else "heuristic_not_probability"
                ),
            },
            "abstention_reason": final_reasons[0] if final in {DecisionAction.HOLD, DecisionAction.BLOCKED} else None,
        },
    )
