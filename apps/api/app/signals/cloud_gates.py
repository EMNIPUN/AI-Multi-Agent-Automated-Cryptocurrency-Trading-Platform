"""Kill switches for Phase 4D Supabase signal persistence (default OFF)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class SignalCloudGates:
    """
    Dual gate — both must be true before any Supabase signal/history write.

    Independent from exchange binding persistence gates.
    """

    writes_enabled: bool
    operator_approved: bool
    sync_enabled: bool

    @property
    def cloud_writes_allowed(self) -> bool:
        return self.writes_enabled and self.operator_approved

    @property
    def sync_allowed(self) -> bool:
        return self.cloud_writes_allowed and self.sync_enabled


def get_signal_cloud_gates() -> SignalCloudGates:
    return SignalCloudGates(
        writes_enabled=_flag("SIGNAL_SUPABASE_WRITES_ENABLED"),
        operator_approved=_flag("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED"),
        sync_enabled=_flag("SIGNAL_CLOUD_SYNC_ENABLED"),
    )


def gates_public_dict() -> dict[str, object]:
    g = get_signal_cloud_gates()
    return {
        "signal_supabase_writes_enabled": g.writes_enabled,
        "signal_supabase_writes_operator_approved": g.operator_approved,
        "signal_cloud_sync_enabled": g.sync_enabled,
        "cloud_writes_allowed": g.cloud_writes_allowed,
        "sync_allowed": g.sync_allowed,
        "binding_persistence_unchanged": True,
        "note": (
            "Operator-authorized SoT cutover: SUPABASE_SOT_ENABLED targets Postgres "
            "(alembic 20261108_0006 + SIGNAL_CLOUD_OWNER_USER_ID). "
            "Mirror/API cloud writes still require SIGNAL_SUPABASE_WRITES_* dual gates."
        ),
    }
