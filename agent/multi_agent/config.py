"""Configurable weights and paper-risk knobs (signals only)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


# Advanced multi-agent: trend/momentum/volume/structure + offline calibration.
STRATEGY_VERSION = "6.0.0"


@dataclass(frozen=True)
class SignalAgentWeights:
    """Weights apply to directional agents (trend, momentum, volume, structure)."""

    trend: float = 0.40
    momentum: float = 0.30
    volume: float = 0.15
    structure: float = 0.15

    def normalized(self) -> SignalAgentWeights:
        total = self.trend + self.momentum + self.volume + self.structure
        if total <= 0:
            return SignalAgentWeights(0.40, 0.30, 0.15, 0.15)
        return SignalAgentWeights(
            trend=self.trend / total,
            momentum=self.momentum / total,
            volume=self.volume / total,
            structure=self.structure / total,
        )


@dataclass(frozen=True)
class PaperRiskConfig:
    """Hypothetical capital only — never reads live exchange balances."""

    paper_balance: float = 10_000.0
    max_risk_fraction_per_trade: float = 0.01  # 1% of paper balance
    min_stop_distance_pct: float = 0.004  # 0.4%
    max_stop_distance_pct: float = 0.03  # 3%
    min_risk_reward: float = 1.5
    take_profit_rr: float = 2.0
    daily_loss_halt_fraction: float = 0.03  # 3% of paper balance
    cooldown_ms: int = 15 * 60_000
    max_atr_pct: float = 0.06  # volatility filter (approx ATR/price)
    atr_lookback: int = 14
    agent_timeout_ms: int = 250


@dataclass(frozen=True)
class RegimeConfig:
    """Conservative confirmation gates, not fitted accuracy estimates."""

    enabled: bool = True
    lookback: int = 20
    range_efficiency: float = 0.15
    trend_efficiency: float = 0.35
    minimum_supporting_agents: int = 2

    def __post_init__(self) -> None:
        if self.lookback < 2:
            raise ValueError("Regime lookback must be at least 2")
        if not 0 <= self.range_efficiency < self.trend_efficiency <= 1:
            raise ValueError("Regime efficiency thresholds must be ordered within 0..1")
        if self.minimum_supporting_agents not in {1, 2, 3}:
            raise ValueError("Regime consensus requires between 1 and 3 supporting agents")


@dataclass(frozen=True)
class SignalPipelineConfig:
    weights: SignalAgentWeights = SignalAgentWeights()
    risk: PaperRiskConfig = PaperRiskConfig()
    strategy_version: str = STRATEGY_VERSION
    min_confirmed_bars: int = 210  # EMA200 + buffer
    buy_threshold: float = 0.35
    sell_threshold: float = -0.35
    # Market quality is a gate, not a directional additive term.
    min_market_quality: float = 1.0
    regime: RegimeConfig = RegimeConfig()
    # Optional offline calibration profile id/hash (see calibration.py).
    calibration_profile_id: str | None = None
    calibration_hash: str | None = None


def config_hash(config: SignalPipelineConfig) -> str:
    payload = {
        "strategy_version": config.strategy_version,
        "weights": asdict(config.weights.normalized()),
        "buy_threshold": config.buy_threshold,
        "sell_threshold": config.sell_threshold,
        "min_market_quality": config.min_market_quality,
        "min_confirmed_bars": config.min_confirmed_bars,
        "risk": asdict(config.risk),
        "regime": asdict(config.regime),
        "calibration_profile_id": config.calibration_profile_id,
        "calibration_hash": config.calibration_hash,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
