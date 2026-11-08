"""
Read-only order lifecycle observer (Phase 3B Part 2).

Projects authoritative IntentStore state into the separate TelemetryLedger.
Never writes the intent/execution databases. Never places or cancels orders.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError

from agent.intent_store import IntentStore, IntentStoreError
from agent.order_intent import OrderIntent, OrderIntentState
from agent.telemetry_ledger import TelemetryLedger, make_event
from apps.api.app.observability.types import (
    ExecutionMode,
    ObservabilityEventType,
    OrderLifecycleItem,
    PipelineStep,
)

_STATE_EVENTS: dict[OrderIntentState, ObservabilityEventType] = {
    OrderIntentState.CREATED: ObservabilityEventType.ORDER_INTENT_CREATED,
    OrderIntentState.ACCEPTED: ObservabilityEventType.ORDER_ACCEPTED,
    OrderIntentState.PARTIALLY_FILLED: ObservabilityEventType.ORDER_PARTIALLY_FILLED,
    OrderIntentState.FILLED: ObservabilityEventType.ORDER_FILLED,
    OrderIntentState.CANCELED: ObservabilityEventType.ORDER_CANCELED,
    OrderIntentState.RECONCILIATION_REQUIRED: ObservabilityEventType.ORDER_RECONCILIATION_REQUIRED,
    OrderIntentState.UNKNOWN: ObservabilityEventType.ORDER_RECONCILIATION_REQUIRED,
}

_PIPELINE: dict[ObservabilityEventType, PipelineStep] = {
    ObservabilityEventType.ORDER_INTENT_CREATED: PipelineStep.INTENT,
    ObservabilityEventType.ORDER_ACCEPTED: PipelineStep.INTENT,
    ObservabilityEventType.ORDER_PARTIALLY_FILLED: PipelineStep.RECONCILIATION,
    ObservabilityEventType.ORDER_FILLED: PipelineStep.RECONCILIATION,
    ObservabilityEventType.ORDER_CANCELED: PipelineStep.RECONCILIATION,
    ObservabilityEventType.ORDER_RECONCILIATION_REQUIRED: PipelineStep.RECONCILIATION,
}


@dataclass(frozen=True)
class ObservationResult:
    emitted: int
    intents_seen: int
    orders: list[OrderLifecycleItem]
    error: str | None = None


def event_id_for_intent(intent: OrderIntent) -> str | None:
    """Stable idempotent id for the current evidenced lifecycle stage."""
    state = intent.state
    if state is OrderIntentState.CREATED:
        return f"order.intent_created:{intent.intent_id}"
    if state is OrderIntentState.ACCEPTED:
        return f"order.accepted:{intent.intent_id}"
    if state is OrderIntentState.PARTIALLY_FILLED:
        filled = intent.filled_qty or "0"
        return f"order.partially_filled:{intent.intent_id}:{filled}"
    if state is OrderIntentState.FILLED:
        return f"order.filled:{intent.intent_id}"
    if state is OrderIntentState.CANCELED:
        return f"order.canceled:{intent.intent_id}"
    if state is OrderIntentState.RECONCILIATION_REQUIRED:
        return f"order.reconciliation_required:{intent.intent_id}"
    if state is OrderIntentState.UNKNOWN:
        return f"order.reconciliation_required:{intent.intent_id}:unknown"
    # SUBMISSION_PENDING / REJECTED: no order.* event in the Part 2 contract.
    return None


def lifecycle_item(intent: OrderIntent) -> OrderLifecycleItem:
    updated = _parse_iso(intent.updated_at) or _parse_iso(intent.created_at)
    return OrderLifecycleItem(
        client_order_id=intent.client_order_id,
        state=intent.state.value,
        side=intent.side,
        qty=intent.qty,
        filled_qty=intent.filled_qty or "0",
        correlation_id=intent.correlation_id or None,
        updated_at=updated,
        sample=False,
    )


class OrderLifecycleObserver:
    """Poll IntentStore → TelemetryLedger without mutating authority."""

    def __init__(
        self,
        *,
        intent_store: IntentStore | None = None,
        intent_db_path: str | Path | None = None,
        env_scope: str,
        account_fp: str,
        execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
        limit: int = 200,
        busy_retries: int = 3,
        busy_sleep_s: float = 0.05,
        list_fn: Callable[[], list[OrderIntent]] | None = None,
    ) -> None:
        self.env_scope = env_scope
        self.account_fp = account_fp
        self.execution_mode = execution_mode
        self.limit = limit
        self.busy_retries = busy_retries
        self.busy_sleep_s = busy_sleep_s
        self._list_fn = list_fn
        self._store = intent_store
        self._intent_db_path = intent_db_path

    def _store_instance(self) -> IntentStore:
        if self._store is not None:
            return self._store
        return IntentStore(db_path=self._intent_db_path)

    def _load_intents(self) -> list[OrderIntent]:
        last_exc: Exception | None = None
        for attempt in range(self.busy_retries):
            try:
                if self._list_fn is not None:
                    return self._list_fn()
                return self._store_instance().list_recent_for_observation(
                    self.env_scope,
                    self.account_fp,
                    limit=self.limit,
                )
            except (SQLAlchemyError, IntentStoreError, OSError) as exc:
                last_exc = exc
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    time.sleep(self.busy_sleep_s * (attempt + 1))
                    continue
                raise
        if last_exc:
            raise last_exc
        return []

    def poll(self, ledger: TelemetryLedger) -> ObservationResult:
        """
        Emit missing lifecycle events for current authoritative intents.
        Telemetry write failures are isolated; the intent store is never written.
        """
        try:
            intents = self._load_intents()
        except Exception as exc:  # noqa: BLE001 — observation must not stop the agent
            return ObservationResult(
                emitted=0,
                intents_seen=0,
                orders=[],
                error=f"{type(exc).__name__}",
            )

        emitted = 0
        orders = [lifecycle_item(intent) for intent in intents]
        for intent in intents:
            event_type = _STATE_EVENTS.get(intent.state)
            event_id = event_id_for_intent(intent)
            if event_type is None or event_id is None:
                continue
            occurred = _parse_iso(_authoritative_ts(intent)) or datetime.now(timezone.utc)
            try:
                event = make_event(
                    event_type=event_type,
                    event_id=event_id,
                    message=_message(intent),
                    symbol=intent.symbol,
                    correlation_id=intent.correlation_id or None,
                    env_scope=self.env_scope,
                    execution_mode=self.execution_mode,
                    pipeline_step=_PIPELINE.get(event_type),
                    payload=_safe_payload(intent),
                )
                event = event.model_copy(update={"occurred_at": occurred})
                if ledger.safe_record(event):
                    emitted += 1
            except Exception:
                continue
        return ObservationResult(
            emitted=emitted,
            intents_seen=len(intents),
            orders=orders,
        )


def _authoritative_ts(intent: OrderIntent) -> str:
    return intent.updated_at or intent.created_at


def _message(intent: OrderIntent) -> str:
    if intent.state is OrderIntentState.ACCEPTED:
        return "Exchange accepted the order (not a fill)"
    if intent.state is OrderIntentState.PARTIALLY_FILLED:
        return f"Partial fill evidenced; filled={intent.filled_qty or '0'}"
    if intent.state is OrderIntentState.FILLED:
        return "Fill evidenced to completion"
    if intent.state is OrderIntentState.CANCELED:
        return "Order canceled; earlier fills are preserved if present"
    if intent.state is OrderIntentState.UNKNOWN:
        return "Order state UNKNOWN — not verified as filled or rejected"
    if intent.state is OrderIntentState.RECONCILIATION_REQUIRED:
        return "Reconciliation required before treating exposure as settled"
    if intent.state is OrderIntentState.CREATED:
        return "Order intent created locally"
    return intent.state.value


def _safe_payload(intent: OrderIntent) -> dict:
    remaining = intent.remaining_qty
    if not remaining and intent.qty and intent.filled_qty:
        remaining = "not_verified"
    return {
        "intent_id": intent.intent_id,
        "client_order_id": intent.client_order_id,
        "symbol": intent.symbol,
        "category": intent.category,
        "side": intent.side,
        "qty": intent.qty,
        "filled_qty": intent.filled_qty or "0",
        "remaining_qty": remaining or "",
        "state": intent.state.value,
        "dry_run": intent.dry_run,
        "reduce_only": intent.reduce_only,
        "evidence_status": intent.evidence_status or "",
        "reconciliation_required": intent.state
        in {
            OrderIntentState.RECONCILIATION_REQUIRED,
            OrderIntentState.UNKNOWN,
            OrderIntentState.ACCEPTED,
            OrderIntentState.PARTIALLY_FILLED,
        },
        # Never include account_fp or exchange secrets.
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
