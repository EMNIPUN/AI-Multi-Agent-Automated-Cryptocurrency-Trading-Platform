"""Order intent model and lifecycle state machine (Phase 1B / 1E)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class OrderIntentState(str, Enum):
    CREATED = "CREATED"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    ACCEPTED = "ACCEPTED"  # exchange ack — NOT proof of fill
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


# Valid directed transitions (including restart recovery).
_ALLOWED: dict[OrderIntentState, frozenset[OrderIntentState]] = {
    OrderIntentState.CREATED: frozenset(
        {
            OrderIntentState.SUBMISSION_PENDING,
            OrderIntentState.CANCELED,  # dry-run skip / abandoned
            OrderIntentState.REJECTED,  # local pre-submit reject
        }
    ),
    OrderIntentState.SUBMISSION_PENDING: frozenset(
        {
            OrderIntentState.ACCEPTED,
            OrderIntentState.REJECTED,
            OrderIntentState.UNKNOWN,
            OrderIntentState.RECONCILIATION_REQUIRED,  # crash mid-flight
        }
    ),
    OrderIntentState.UNKNOWN: frozenset(
        {
            OrderIntentState.RECONCILIATION_REQUIRED,
            OrderIntentState.ACCEPTED,
            OrderIntentState.PARTIALLY_FILLED,
            OrderIntentState.FILLED,
            OrderIntentState.REJECTED,
            OrderIntentState.CANCELED,
        }
    ),
    OrderIntentState.RECONCILIATION_REQUIRED: frozenset(
        {
            OrderIntentState.ACCEPTED,
            OrderIntentState.PARTIALLY_FILLED,
            OrderIntentState.FILLED,
            OrderIntentState.REJECTED,
            OrderIntentState.CANCELED,
            OrderIntentState.UNKNOWN,  # lookup still inconclusive
        }
    ),
    OrderIntentState.ACCEPTED: frozenset(
        {
            OrderIntentState.PARTIALLY_FILLED,
            OrderIntentState.FILLED,
            OrderIntentState.CANCELED,
            OrderIntentState.REJECTED,
            OrderIntentState.UNKNOWN,  # evidence conflict / lookup failure
            OrderIntentState.RECONCILIATION_REQUIRED,
        }
    ),
    OrderIntentState.PARTIALLY_FILLED: frozenset(
        {
            OrderIntentState.FILLED,
            OrderIntentState.CANCELED,  # partial then cancel — keep filled_qty
            OrderIntentState.UNKNOWN,
            OrderIntentState.RECONCILIATION_REQUIRED,
        }
    ),
    OrderIntentState.FILLED: frozenset(),
    OrderIntentState.REJECTED: frozenset(),
    OrderIntentState.CANCELED: frozenset(),
}


UNRESOLVED_STATES = frozenset(
    {
        OrderIntentState.SUBMISSION_PENDING,
        OrderIntentState.UNKNOWN,
        OrderIntentState.RECONCILIATION_REQUIRED,
    }
)

# Live intents that still need evidence-based reconcile (read-only).
NEEDS_RECONCILE_STATES = frozenset(
    {
        *UNRESOLVED_STATES,
        OrderIntentState.ACCEPTED,
        OrderIntentState.PARTIALLY_FILLED,
    }
)

# Block new exposure while these exist (Phase 1B unresolved + open partials).
BLOCKING_EXPOSURE_STATES = frozenset(
    {
        *UNRESOLVED_STATES,
        OrderIntentState.PARTIALLY_FILLED,
    }
)

TERMINAL_STATES = frozenset(
    {
        OrderIntentState.FILLED,
        OrderIntentState.REJECTED,
        OrderIntentState.CANCELED,
    }
)


def can_transition(current: OrderIntentState, new: OrderIntentState) -> bool:
    if current is new:
        return True
    return new in _ALLOWED.get(current, frozenset())


def assert_transition(current: OrderIntentState, new: OrderIntentState) -> None:
    if not can_transition(current, new):
        raise ValueError(f"invalid order intent transition {current.value} -> {new.value}")


def merge_reconcile_state(
    current: OrderIntentState, proposed: OrderIntentState
) -> OrderIntentState:
    """
    Apply exchange evidence without regressing terminal states or fill progress.

    Duplicate / out-of-order updates must not move FILLED → ACCEPTED, etc.
    """
    if current is proposed:
        return current
    if current in TERMINAL_STATES:
        return current
    if can_transition(current, proposed):
        # Do not regress fill progress ACCEPTED←PARTIALLY_FILLED (same-state only).
        progress = {
            OrderIntentState.ACCEPTED: 1,
            OrderIntentState.PARTIALLY_FILLED: 2,
            OrderIntentState.FILLED: 3,
            OrderIntentState.CANCELED: 3,
            OrderIntentState.REJECTED: 3,
        }
        if current in progress and proposed in progress:
            if progress[proposed] < progress[current]:
                return current
        return proposed
    return current


@dataclass
class OrderIntent:
    intent_id: str
    client_order_id: str
    env_scope: str
    account_fp: str
    symbol: str
    category: str
    side: str
    qty: str
    reduce_only: bool
    order_type: str
    time_in_force: str
    take_profit: str | None
    stop_loss: str | None
    correlation_id: str
    risk_auth_ref: str
    state: OrderIntentState
    created_at: str
    expires_at: str
    dry_run: bool
    exchange_order_id: str = ""
    last_error: str = ""
    filled_qty: str = ""
    remaining_qty: str = ""
    avg_exec_price: str = ""
    cum_fee: str = ""
    evidence_status: str = ""
    submission_attempted: bool = False
    updated_at: str = ""

    @property
    def is_unresolved(self) -> bool:
        return self.state in UNRESOLVED_STATES

    @property
    def needs_reconcile(self) -> bool:
        return self.state in NEEDS_RECONCILE_STATES

    @property
    def increases_exposure(self) -> bool:
        return not self.reduce_only


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_expiry_iso(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
