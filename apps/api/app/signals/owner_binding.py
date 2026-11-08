"""
Verified owner binding for unattended Phase 4D cloud synchronization.

Fail-closed: sync must not invent a user UUID. Operator establishes binding via
SIGNAL_CLOUD_OWNER_USER_ID after authenticating in Supabase Auth (manual setup).
This module never creates Auth users and never trusts frontend-supplied owner ids.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from apps.api.app.auth.principal import AuthenticatedPrincipal


@dataclass(frozen=True)
class SyncOwnerBinding:
    owner_user_id: uuid.UUID | None
    source: str
    sync_owner_ready: bool
    block_reason: str | None

    def public_dict(self) -> dict[str, Any]:
        return {
            "sync_owner_ready": self.sync_owner_ready,
            "owner_bound": self.owner_user_id is not None,
            "owner_user_id_prefix": (
                str(self.owner_user_id)[:8] + "…" if self.owner_user_id else None
            ),
            "source": self.source,
            "block_reason": self.block_reason,
            "note": (
                "Set SIGNAL_CLOUD_OWNER_USER_ID to the verified Supabase Auth user UUID "
                "(JWT sub) in a later approved operator setup. Do not invent UUIDs."
            ),
        }


def resolve_sync_owner_binding() -> SyncOwnerBinding:
    raw = (os.getenv("SIGNAL_CLOUD_OWNER_USER_ID") or "").strip()
    if not raw:
        return SyncOwnerBinding(
            owner_user_id=None,
            source="env_missing",
            sync_owner_ready=False,
            block_reason="signal_cloud_owner_user_id_unset",
        )
    try:
        owner = uuid.UUID(raw)
    except ValueError:
        return SyncOwnerBinding(
            owner_user_id=None,
            source="env_invalid",
            sync_owner_ready=False,
            block_reason="signal_cloud_owner_user_id_invalid_uuid",
        )
    return SyncOwnerBinding(
        owner_user_id=owner,
        source="SIGNAL_CLOUD_OWNER_USER_ID",
        sync_owner_ready=True,
        block_reason=None,
    )


def require_sync_owner_user_id() -> uuid.UUID:
    binding = resolve_sync_owner_binding()
    if binding.owner_user_id is None or not binding.sync_owner_ready:
        raise RuntimeError(binding.block_reason or "sync_owner_not_bound")
    return binding.owner_user_id


def assert_principal_matches_bound_owner(principal: AuthenticatedPrincipal) -> uuid.UUID:
    """Interactive cloud history: JWT sub is the owner — never client-supplied."""
    try:
        uid = uuid.UUID(str(principal.user_id))
    except ValueError as exc:
        raise ValueError("principal_user_id_invalid_uuid") from exc
    return uid
