"""Backtest inputs, events, and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class BacktestStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED_DATA = "rejected_data"


@dataclass(frozen=True)
class DatasetIdentity:
    symbol: str
    interval: str
    market_type: str
    candle_count: int
    first_start_ms: int
    last_start_ms: int
    content_hash: str
    provenance: str
    source_kind: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionRecord:
    candle_start_ms: int
    now_ms: int
    action: str
    risk_verdict: str
    decision_id: str
    signal_strength: float
    reason_codes: tuple[str, ...]
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    position_notional: float | None
    contribution_biases: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionRecord:
    candle_start_ms: int
    kind: str  # submit | fill | reject | process
    ok: bool
    reason: str
    order_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptionalMetricView:
    value: str | None
    status: str
    reason: str | None = None


@dataclass
class DecisionCounters:
    evaluations: int = 0
    buy: int = 0
    sell: int = 0
    hold: int = 0
    blocked: int = 0
    submitted: int = 0
    filled: int = 0
    rejected: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "total_agent_evaluations": self.evaluations,
            "buy_signals": self.buy,
            "sell_signals": self.sell,
            "hold_signals": self.hold,
            "blocked_signals": self.blocked,
            "submitted_simulated_orders": self.submitted,
            "filled_orders": self.filled,
            "rejected_orders": self.rejected,
        }


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    status: BacktestStatus
    performance_label: str
    effective_config: dict[str, Any]
    dataset: DatasetIdentity
    session_id: str | None
    journal_path: str | None
    eligible_candles: int
    warm_up_candles: int
    counters: dict[str, int]
    decisions: tuple[DecisionRecord, ...]
    executions: tuple[ExecutionRecord, ...]
    analytics: dict[str, Any] | None
    open_positions: int
    final_available_balance: str | None
    final_reserved_capital: str | None
    final_marked_equity: str | None
    data_quality_warnings: tuple[str, ...]
    result_hash: str
    created_ms: int  # wall-clock metadata — excluded from result_hash
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "performance_label": self.performance_label,
            "effective_config": self.effective_config,
            "dataset": {
                "symbol": self.dataset.symbol,
                "interval": self.dataset.interval,
                "market_type": self.dataset.market_type,
                "candle_count": self.dataset.candle_count,
                "first_start_ms": self.dataset.first_start_ms,
                "last_start_ms": self.dataset.last_start_ms,
                "content_hash": self.dataset.content_hash,
                "provenance": self.dataset.provenance,
                "source_kind": self.dataset.source_kind,
                "warnings": list(self.dataset.warnings),
            },
            "session_id": self.session_id,
            "journal_path": self.journal_path,
            "eligible_candles": self.eligible_candles,
            "warm_up_candles": self.warm_up_candles,
            "counters": self.counters,
            "decisions": [
                {
                    "candle_start_ms": d.candle_start_ms,
                    "now_ms": d.now_ms,
                    "action": d.action,
                    "risk_verdict": d.risk_verdict,
                    "decision_id": d.decision_id,
                    "signal_strength": d.signal_strength,
                    "reason_codes": list(d.reason_codes),
                    "entry": d.entry,
                    "stop_loss": d.stop_loss,
                    "take_profit": d.take_profit,
                    "position_notional": d.position_notional,
                    "contribution_biases": list(d.contribution_biases),
                }
                for d in self.decisions
            ],
            "executions": [
                {
                    "candle_start_ms": e.candle_start_ms,
                    "kind": e.kind,
                    "ok": e.ok,
                    "reason": e.reason,
                    "order_id": e.order_id,
                    "detail": e.detail,
                }
                for e in self.executions
            ],
            "analytics": self.analytics,
            "open_positions": self.open_positions,
            "final_available_balance": self.final_available_balance,
            "final_reserved_capital": self.final_reserved_capital,
            "final_marked_equity": self.final_marked_equity,
            "data_quality_warnings": list(self.data_quality_warnings),
            "result_hash": self.result_hash,
            "created_ms": self.created_ms,
            "error": self.error,
            "extras": self.extras,
            "currency_note": "Monetary values are virtual USDT in isolated paper simulation.",
        }


def optional_metric_dict(m: Any) -> dict[str, Any] | None:
    if m is None:
        return None
    value = getattr(m, "value", None)
    return {
        "value": None if value is None else str(value),
        "status": getattr(getattr(m, "status", None), "value", str(getattr(m, "status", ""))),
        "reason": getattr(m, "reason", None),
    }


def qstr(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
