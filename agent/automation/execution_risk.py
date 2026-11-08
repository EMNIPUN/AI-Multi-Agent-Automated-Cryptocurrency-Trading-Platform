"""
Phase 6A independent execution risk engine (hard limits).

Separate from Phase 4 paper SignalRiskState and from legacy AGENT_RISK_PCT sizing.
Fail closed. Conservative defaults. Spot-first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ExecutionRiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    VETO = "VETO"
    HALTED = "HALTED"


@dataclass(frozen=True)
class ExecutionRiskLimits:
    max_risk_fraction_per_trade: float = 0.005  # 0.5% equity
    max_daily_loss_fraction: float = 0.02  # 2%
    max_concurrent_positions: int = 1
    max_portfolio_exposure_fraction: float = 0.25
    max_position_notional: float = 500.0  # USDT
    min_available_balance: float = 50.0
    max_spread_bps: float = 15.0
    max_slippage_bps: float = 20.0
    max_data_age_ms: int = 120_000
    max_api_errors_per_hour: int = 10
    require_stop_loss: bool = True
    spot_only_default: bool = True


@dataclass
class ExecutionRiskState:
    day_key: str = ""
    realized_day_pnl: float = 0.0
    open_positions: int = 0
    open_notional: float = 0.0
    halted: bool = False
    halt_reason: str = ""
    api_errors_window: int = 0
    seen_client_order_ids: set[str] = field(default_factory=set)
    emergency_halt: bool = False
    protection_unverified: bool = False


@dataclass(frozen=True)
class ExecutionRiskAssessment:
    verdict: ExecutionRiskVerdict
    reason_codes: tuple[str, ...]
    explanation: str
    sized_qty: float | None = None
    max_notional: float | None = None


@dataclass(frozen=True)
class ExecutionCandidate:
    symbol: str
    category: str  # spot | linear
    side: str
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    equity: float
    available_balance: float
    spread_bps: float
    data_age_ms: int
    client_order_id: str
    intended_notional: float
    now_ms: int


def evaluate_execution_risk(
    candidate: ExecutionCandidate,
    state: ExecutionRiskState,
    limits: ExecutionRiskLimits | None = None,
) -> ExecutionRiskAssessment:
    limits = limits or ExecutionRiskLimits()
    reasons: list[str] = []

    if state.emergency_halt or state.halted:
        return ExecutionRiskAssessment(
            ExecutionRiskVerdict.HALTED,
            ("EXECUTION_HALTED",),
            state.halt_reason or "execution halted",
        )
    if state.protection_unverified:
        return ExecutionRiskAssessment(
            ExecutionRiskVerdict.HALTED,
            ("PROTECTION_UNVERIFIED",),
            "Protective stops not verified — new entries halted",
        )
    if limits.spot_only_default and candidate.category != "spot":
        reasons.append("SPOT_ONLY_DEFAULT")
    if candidate.available_balance < limits.min_available_balance:
        reasons.append("INSUFFICIENT_BALANCE")
    if candidate.data_age_ms > limits.max_data_age_ms:
        reasons.append("STALE_MARKET_DATA")
    if candidate.spread_bps > limits.max_spread_bps:
        reasons.append("SPREAD_TOO_WIDE")
    if candidate.client_order_id in state.seen_client_order_ids:
        reasons.append("DUPLICATE_CLIENT_ORDER_ID")
    if state.api_errors_window >= limits.max_api_errors_per_hour:
        reasons.append("EXCESSIVE_API_ERRORS")
    if state.open_positions >= limits.max_concurrent_positions:
        reasons.append("MAX_CONCURRENT_POSITIONS")
    if limits.require_stop_loss and (
        candidate.stop_loss is None or candidate.stop_loss <= 0
    ):
        reasons.append("STOP_LOSS_REQUIRED")

    risk_budget = candidate.equity * limits.max_risk_fraction_per_trade
    max_notional = min(
        limits.max_position_notional,
        candidate.equity * limits.max_portfolio_exposure_fraction - state.open_notional,
        candidate.available_balance * 0.95,
        candidate.intended_notional,
    )
    if max_notional <= 0:
        reasons.append("EXPOSURE_CAP")

    day_loss_frac = (
        abs(min(0.0, state.realized_day_pnl)) / candidate.equity
        if candidate.equity > 0
        else 1.0
    )
    if day_loss_frac >= limits.max_daily_loss_fraction:
        reasons.append("DAILY_LOSS_HALT")

    if candidate.stop_loss and candidate.entry_price > 0:
        stop_dist = abs(candidate.entry_price - candidate.stop_loss) / candidate.entry_price
        if stop_dist <= 0:
            reasons.append("INVALID_STOP_DISTANCE")
        else:
            # Cap notional so loss at stop ≈ risk_budget
            stop_capped = risk_budget / stop_dist
            max_notional = min(max_notional, stop_capped)

    if reasons:
        verdict = (
            ExecutionRiskVerdict.HALTED
            if "DAILY_LOSS_HALT" in reasons or "PROTECTION_UNVERIFIED" in reasons
            else ExecutionRiskVerdict.VETO
        )
        return ExecutionRiskAssessment(
            verdict,
            tuple(reasons),
            "Execution risk veto: " + ", ".join(reasons),
            sized_qty=None,
            max_notional=max_notional if max_notional > 0 else None,
        )

    qty = max_notional / candidate.entry_price if candidate.entry_price > 0 else 0.0
    return ExecutionRiskAssessment(
        ExecutionRiskVerdict.APPROVED,
        ("EXEC_RISK_OK",),
        "Execution risk approved (paper/test planning)",
        sized_qty=qty,
        max_notional=max_notional,
    )


def record_api_error(state: ExecutionRiskState) -> None:
    state.api_errors_window += 1


def trigger_emergency_halt(state: ExecutionRiskState, reason: str) -> None:
    state.emergency_halt = True
    state.halted = True
    state.halt_reason = reason
