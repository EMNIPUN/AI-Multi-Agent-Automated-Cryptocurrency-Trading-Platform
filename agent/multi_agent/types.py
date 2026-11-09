"""Typed contracts for Phase 4A signals-only multi-agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from agent.market_data import Candle


class MarketCategoryKind(str, Enum):
    SPOT = "spot"
    LINEAR = "linear"


class TrendBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MomentumBias(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class DecisionAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    BLOCKED = "BLOCKED"


class RiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    VETO = "VETO"
    HALTED = "HALTED"


@dataclass(frozen=True)
class MarketSnapshot:
    """Immutable public-market snapshot for one decision cycle."""

    symbol: str
    category: MarketCategoryKind
    interval: str
    candles: tuple[Candle, ...]  # confirmed only, oldest→newest
    closes: tuple[float, ...]
    volumes: tuple[float, ...]
    newest_close_ms: int
    as_of_ms: int
    data_fresh: bool
    data_path: str
    reason_codes: tuple[str, ...] = ()
    valid: bool = True

    @property
    def last_price(self) -> float:
        return self.closes[-1] if self.closes else 0.0


@dataclass(frozen=True)
class AgentContribution:
    agent_id: str
    agent_version: str
    bias: str
    confidence: float  # 0..1 qualitative weight — NOT calibrated win probability
    reason_codes: tuple[str, ...]
    explanation: str
    indicators: dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False
    error: str | None = None


@dataclass(frozen=True)
class RiskAssessment:
    verdict: RiskVerdict
    reason_codes: tuple[str, ...]
    explanation: str
    paper_balance: float
    risk_fraction: float
    position_notional: float | None
    stop_distance_pct: float | None
    reward_distance_pct: float | None
    risk_reward: float | None
    cooldown_remaining_ms: int = 0
    indicators: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HypotheticalLevels:
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    note: str = "Hypothetical paper levels only — not an order"


@dataclass(frozen=True)
class CoordinatorDecision:
    action: DecisionAction
    symbol: str
    category: str
    interval: str
    timestamp_ms: int
    strategy_version: str
    correlation_id: str
    decision_id: str
    signal_strength: float  # 0..1 qualitative score — NOT win probability
    signal_strength_note: str
    contributions: tuple[AgentContribution, ...]
    risk: RiskAssessment
    reason_codes: tuple[str, ...]
    explanation: str
    levels: HypotheticalLevels
    market: MarketSnapshot
    idempotent_key: str
    directional_conviction: float = 0.0  # [-1, 1] symmetric
    market_quality: float = 0.0  # [0, 1] gate only — not directional
    config_hash: str = ""
    source_mode: str = "SIMULATED"
    execution_allowed: Literal[False] = False
    news_advisory: dict[str, Any] | None = None
    news_changed_decision: bool = False
    decision_context: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "symbol": self.symbol,
            "category": self.category,
            "interval": self.interval,
            "timestamp_ms": self.timestamp_ms,
            "strategy_version": self.strategy_version,
            "correlation_id": self.correlation_id,
            "decision_id": self.decision_id,
            "signal_strength": self.signal_strength,
            "signal_strength_note": self.signal_strength_note,
            "directional_conviction": self.directional_conviction,
            "market_quality": self.market_quality,
            "config_hash": self.config_hash,
            "source_mode": self.source_mode,
            "decision_context": self.decision_context,
            "reason_codes": list(self.reason_codes),
            "explanation": self.explanation,
            "execution_allowed": False,
            "not_an_order": True,
            "contributions": [
                {
                    "agent_id": c.agent_id,
                    "agent_version": c.agent_version,
                    "bias": c.bias,
                    "confidence": c.confidence,
                    "reason_codes": list(c.reason_codes),
                    "explanation": c.explanation,
                    "indicators": c.indicators,
                    "timed_out": c.timed_out,
                    "error": c.error,
                }
                for c in self.contributions
            ],
            "risk": {
                "verdict": self.risk.verdict.value,
                "reason_codes": list(self.risk.reason_codes),
                "explanation": self.risk.explanation,
                "paper_balance": self.risk.paper_balance,
                "risk_fraction": self.risk.risk_fraction,
                "position_notional": self.risk.position_notional,
                "stop_distance_pct": self.risk.stop_distance_pct,
                "reward_distance_pct": self.risk.reward_distance_pct,
                "risk_reward": self.risk.risk_reward,
                "cooldown_remaining_ms": self.risk.cooldown_remaining_ms,
                "indicators": self.risk.indicators,
            },
            "levels": {
                "entry": self.levels.entry,
                "stop_loss": self.levels.stop_loss,
                "take_profit": self.levels.take_profit,
                "note": self.levels.note,
            },
            "market": {
                "symbol": self.market.symbol,
                "category": self.market.category.value,
                "interval": self.market.interval,
                "bar_count": len(self.market.candles),
                "newest_close_ms": self.market.newest_close_ms,
                "as_of_ms": self.market.as_of_ms,
                "data_fresh": self.market.data_fresh,
                "data_path": self.market.data_path,
                "last_price": self.market.last_price,
                "valid": self.market.valid,
                "reason_codes": list(self.market.reason_codes),
            },
            "idempotent_key": self.idempotent_key,
            "news_changed_decision": False,
            "news_advisory": self.news_advisory
            or {
                "enabled": False,
                "consumed": False,
                "news_changed_decision": False,
                "label": "News Advisory Only — Trading Decisions Unchanged",
                "storage_availability": "not_consulted",
                "freshness": "not_applicable",
                "llm_recommendation": None,
            },
            "news_influence_label": "News Advisory Only — Trading Decisions Unchanged",
        }
