"""Structured LLM decision-support contracts (Prompt 69D). Advisory only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "69D.1.0"
PROMPT_TEMPLATE_VERSION = "69D.prompt.1"
ADVISORY_LABEL = "LLM Advisory Only — Trading Decisions Unchanged"

ALLOWED_ACTIONS = frozenset({"BUY", "SELL", "HOLD", "ABSTAIN"})
TECHNICAL_BIAS = frozenset({"BULLISH", "BEARISH", "NEUTRAL", "INSUFFICIENT_DATA", "UNKNOWN"})
NEWS_BIAS = frozenset({"POSITIVE", "NEGATIVE", "MIXED", "NEUTRAL", "UNKNOWN"})
UNCERTAINTY = frozenset({"LOW", "MEDIUM", "HIGH", "UNKNOWN"})

FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "execution_allowed",
        "position_size",
        "position_notional",
        "place_order",
        "order",
        "orders",
        "api_key",
        "openai_api_key",
        "bypass_risk",
        "risk_override",
    }
)


@dataclass(frozen=True)
class LlmEvaluation:
    evaluation_id: str
    status: str
    symbol: str
    interval: str
    signal_decision_id: str
    coordinator_action: str
    risk_verdict: str
    position_notional: float | None
    suggested_action: str | None
    agreement: str
    conflict_detected: bool
    reason: str
    risk_warnings: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]
    uncertainty: str
    abstain: bool
    model: str
    provider: str
    prompt_template_version: str
    context_hash: str
    validation_result: str
    token_usage: dict[str, int]
    estimated_cost_usd: float
    persisted: bool
    storage_error: str | None
    provider_called: bool
    idempotency_key: str
    idempotent_replay: bool
    warnings: tuple[str, ...]
    requested_at_ms: int
    completed_at_ms: int
    technical_bias: str = "UNKNOWN"
    news_bias: str = "UNKNOWN"
    error_code: str | None = None
    llm_changed_decision: bool = False
    execution_allowed: bool = False
    places_orders: bool = False
    label: str = ADVISORY_LABEL
    schema_version: str = SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_id": self.evaluation_id,
            "status": self.status,
            "label": self.label,
            "symbol": self.symbol,
            "interval": self.interval,
            "signal_decision_id": self.signal_decision_id,
            "coordinator_action": self.coordinator_action,
            "risk_verdict": self.risk_verdict,
            "position_notional": self.position_notional,
            "suggested_action": self.suggested_action,
            "technical_bias": self.technical_bias,
            "news_bias": self.news_bias,
            "agreement": self.agreement,
            "conflict_detected": self.conflict_detected,
            "reason": self.reason,
            "risk_warnings": list(self.risk_warnings),
            "evidence_event_ids": list(self.evidence_event_ids),
            "uncertainty": self.uncertainty,
            "abstain": self.abstain,
            "model": self.model,
            "provider": self.provider,
            "prompt_template_version": self.prompt_template_version,
            "context_hash": self.context_hash,
            "validation_result": self.validation_result,
            "token_usage": dict(self.token_usage),
            "estimated_cost_usd": self.estimated_cost_usd,
            "persisted": self.persisted,
            "storage_error": self.storage_error,
            "provider_called": self.provider_called,
            "idempotency_key": self.idempotency_key,
            "idempotent_replay": self.idempotent_replay,
            "warnings": list(self.warnings),
            "requested_at_ms": self.requested_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "error_code": self.error_code,
            "llm_changed_decision": False,
            "execution_allowed": False,
            "places_orders": False,
            "not_a_trading_signal": True,
            "profitability_not_claimed": True,
        }
