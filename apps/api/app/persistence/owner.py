"""Owner binding for tenant-scoped Supabase SoT rows."""

from __future__ import annotations

import os
import uuid

from apps.api.app.persistence.sqlite_guard import supabase_sot_enabled
from apps.api.app.signals.owner_binding import require_sync_owner_user_id

# Deterministic local-only owner when SoT is disabled (offline SQLAlchemy SQLite tests).
_LOCAL_DEV_OWNER = uuid.UUID("00000000-0000-0000-0000-000000000001")


def resolve_sot_owner_user_id(*, required: bool | None = None) -> uuid.UUID:
    """
    Return the tenant owner UUID for agent-side writes.

    Order: SIGNAL_CLOUD_OWNER_USER_ID → CRYPTONOVA_TEST_OWNER_USER_ID →
    (if SoT disabled) fixed local UUID.
    """
    must = supabase_sot_enabled() if required is None else bool(required)
    try:
        return require_sync_owner_user_id()
    except RuntimeError:
        pass
    raw = (os.getenv("CRYPTONOVA_TEST_OWNER_USER_ID") or "").strip()
    if raw:
        try:
            return uuid.UUID(raw)
        except ValueError as exc:
            raise RuntimeError("cryptonova_test_owner_user_id_invalid_uuid") from exc
    if must:
        raise RuntimeError(
            "signal_cloud_owner_user_id_unset — set SIGNAL_CLOUD_OWNER_USER_ID "
            "or CRYPTONOVA_TEST_OWNER_USER_ID for Supabase SoT"
        )
    return _LOCAL_DEV_OWNER


def require_sot_owner_user_id() -> uuid.UUID:
    return resolve_sot_owner_user_id(required=True)
