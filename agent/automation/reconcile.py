"""TESTNET order/position reconciliation — no blind resubmit on unknown ack."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from agent.automation.exec_store import AutomationExecStore
from agent.automation.execution_risk import ExecutionRiskState
from agent.automation.protective import apply_and_verify_protection
from agent.automation.testnet_adapter import BybitTestnetTradingAdapter


@dataclass(frozen=True)
class ReconcileResult:
    intent_id: str
    state: str
    detail: str
    position_size: float | None = None
    protection_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "state": self.state,
            "detail": self.detail,
            "position_size": self.position_size,
            "protection_state": self.protection_state,
            "live_orders": False,
        }


def reconcile_intent(
    *,
    store: AutomationExecStore,
    adapter: BybitTestnetTradingAdapter,
    intent_id: str,
    halt_new_entries: bool = False,
    risk_state: ExecutionRiskState | None = None,
) -> ReconcileResult:
    now_ms = int(time.time() * 1000)
    row = store.get(intent_id)
    if row is None:
        return ReconcileResult(intent_id, "MISSING", "intent_not_found")

    if halt_new_entries and row.state in {"NEW", "SUBMITTING", "SUBMISSION_PENDING"}:
        return ReconcileResult(intent_id, "HALTED", "new_entries_blocked_protective_only")

    # Timeout / unknown ack — never blind resubmit.
    if row.state in {"SUBMITTING", "UNKNOWN_ACK", "SUBMISSION_PENDING"} and not row.exchange_order_id:
        try:
            found = adapter.get_order(
                category=row.category,
                symbol=row.symbol,
                orderLinkId=row.client_order_id,
            )
        except Exception as exc:  # noqa: BLE001
            store.update_intent(intent_id, state="UNKNOWN_ACK", now_ms=now_ms)
            store.append_event(
                intent_id=intent_id,
                event_type="RECONCILE_QUERY_FAILED",
                detail={"error": type(exc).__name__},
                now_ms=now_ms,
            )
            return ReconcileResult(intent_id, "UNKNOWN_ACK", "timeout_no_blind_resubmit")
        status = str(found.get("orderStatus") or "Unknown")
        if status in {"Unknown", ""}:
            store.update_intent(intent_id, state="UNKNOWN_ACK", now_ms=now_ms)
            return ReconcileResult(intent_id, "UNKNOWN_ACK", "timeout_no_blind_resubmit")
        oid = found.get("orderId")
        if oid:
            store.update_intent(intent_id, exchange_order_id=str(oid), now_ms=now_ms)
        if status == "Filled":
            store.update_intent(intent_id, state="FILLED", now_ms=now_ms)
        elif status in {"Cancelled", "Rejected"}:
            store.update_intent(intent_id, state=status.upper(), now_ms=now_ms)
        else:
            store.update_intent(intent_id, state="ACKED", now_ms=now_ms)

    row = store.get(intent_id) or row
    pos = adapter.get_position(category=row.category, symbol=row.symbol)
    if abs(float(pos.size or 0.0)) > 0 and (row.stop_loss or row.take_profit):
        try:
            prot = apply_and_verify_protection(
                adapter,
                symbol=row.symbol,
                category=row.category,
                stop_loss=row.stop_loss,
                take_profit=row.take_profit,
                risk_state=risk_state or ExecutionRiskState(),
            )
            store.update_intent(
                intent_id,
                protection_state=prot.state.value,
                now_ms=now_ms,
            )
            return ReconcileResult(
                intent_id,
                row.state,
                "reconciled_with_protection",
                position_size=float(pos.size),
                protection_state=prot.state.value,
            )
        except Exception as exc:  # noqa: BLE001
            return ReconcileResult(
                intent_id,
                row.state,
                f"protection_verify_failed:{type(exc).__name__}",
                position_size=float(pos.size),
            )

    return ReconcileResult(
        intent_id,
        row.state,
        "reconciled",
        position_size=float(pos.size or 0.0),
        protection_state=row.protection_state,
    )


def emergency_halt_policy(*, allow_protective_exits: bool = True) -> dict[str, Any]:
    return {
        "block_new_entries": True,
        "allow_protective_exits": allow_protective_exits,
        "cancel_unfilled_entries": True,
        "flatten": False,
        "live_orders": False,
        "label": "TESTNET emergency halt — protective exits only",
    }
