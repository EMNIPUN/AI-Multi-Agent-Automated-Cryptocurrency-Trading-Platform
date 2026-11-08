"""
Phase 6A protective order lifecycle (SL/TP).

Ack ≠ protection. Require exchange-confirmed stop after fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agent.automation.execution_risk import ExecutionRiskState, trigger_emergency_halt
from agent.automation.testnet_adapter import (
    BybitTestnetTradingAdapter,
    PositionView,
    ProtectiveOrderSpec,
)


class ProtectionState(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    MISSING = "MISSING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass
class ProtectionRecord:
    symbol: str
    category: str
    stop_loss: str | None
    take_profit: str | None
    state: ProtectionState = ProtectionState.PENDING
    detail: str = ""


def verify_position_protection(pos: PositionView, *, require_sl: bool = True) -> bool:
    if abs(pos.size) <= 0:
        return True
    if require_sl and not pos.stop_loss:
        return False
    return True


def apply_and_verify_protection(
    adapter: BybitTestnetTradingAdapter,
    *,
    symbol: str,
    category: str,
    stop_loss: str | None,
    take_profit: str | None,
    risk_state: ExecutionRiskState,
) -> ProtectionRecord:
    rec = ProtectionRecord(
        symbol=symbol,
        category=category,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    if not stop_loss:
        rec.state = ProtectionState.MISSING
        rec.detail = "stop_loss_required"
        risk_state.protection_unverified = True
        trigger_emergency_halt(risk_state, "missing_stop_loss_after_fill")
        return rec

    try:
        adapter.set_trading_stop(
            ProtectiveOrderSpec(
                symbol=symbol,
                category=category,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        )
        rec.state = ProtectionState.SUBMITTED
    except Exception as exc:  # noqa: BLE001
        rec.state = ProtectionState.REJECTED
        rec.detail = type(exc).__name__
        risk_state.protection_unverified = True
        trigger_emergency_halt(risk_state, f"stop_rejected:{type(exc).__name__}")
        return rec

    pos = adapter.get_position(category=category, symbol=symbol)
    if verify_position_protection(pos, require_sl=True):
        rec.state = ProtectionState.VERIFIED
        rec.detail = "exchange_stop_present"
        risk_state.protection_unverified = False
    else:
        rec.state = ProtectionState.RECOVERY_REQUIRED
        rec.detail = "stop_not_visible_on_position"
        risk_state.protection_unverified = True
        trigger_emergency_halt(risk_state, "stop_not_verified_on_position")
    return rec


def emergency_risk_procedure(reason: str) -> dict[str, str]:
    """Documented procedure returned to operators — does not invent cancels."""
    return {
        "halt_new_entries": "true",
        "assume_nothing_cancelled": "true",
        "require_exchange_confirmation": "true",
        "reconcile_open_orders_and_positions": "true",
        "manual_operator_review": "required",
        "reason": reason,
        "note": (
            "Never assume an order was cancelled, filled, or closed without "
            "exchange confirmation. Prefer reduce-only flatten only after "
            "reconcile proves size and after operator approval of live Testnet."
        ),
    }
