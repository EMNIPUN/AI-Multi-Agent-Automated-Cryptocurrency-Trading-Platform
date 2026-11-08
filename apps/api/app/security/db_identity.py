"""
Transaction-local PostgreSQL owner identity for least-privilege runtime roles.

DISABLED BY DEFAULT. Does not change active DATABASE_URL or remote grants.

Trust boundary:
  Only FastAPI may call attach_owner_identity after JWT verification.
  The GUC value is not independently trusted if the DB role can SET it
  arbitrarily — pair with NOBYPASSRLS runtime credentials (Option A remote gate).
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_GUC_SUB = "request.jwt.claim.sub"
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def runtime_db_identity_enabled() -> bool:
    return os.getenv("RUNTIME_DB_IDENTITY_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def parse_owner_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    text_v = str(value or "").strip()
    if not text_v or not _UUID_RE.match(text_v):
        raise ValueError("owner_identity_invalid_uuid")
    return uuid.UUID(text_v)


@dataclass(frozen=True)
class AttachedOwnerIdentity:
    owner_user_id: uuid.UUID
    guc_name: str = _GUC_SUB
    is_local: bool = True


def attach_owner_identity(
    session: Session,
    *,
    owner_user_id: uuid.UUID,
    apply_guc: bool | None = None,
) -> AttachedOwnerIdentity:
    """
    SET LOCAL request.jwt.claim.sub for the current transaction only.

    Fail closed on malformed UUID. Uses bound parameters (no string concat of SQL idents
    beyond the fixed GUC name allowlist).

    apply_guc defaults to RUNTIME_DB_IDENTITY_ENABLED. Callers that already gated
    on settings may pass apply_guc=True explicitly.
    """
    owner = parse_owner_uuid(owner_user_id)
    do_guc = runtime_db_identity_enabled() if apply_guc is None else bool(apply_guc)
    if not do_guc:
        # Offline / default path: record intent without touching Postgres GUCs.
        return AttachedOwnerIdentity(owner_user_id=owner)

    # Fixed GUC name — never interpolate user input into the setting key.
    session.execute(
        text("SELECT set_config(:guc, :sub, true)"),
        {"guc": _GUC_SUB, "sub": str(owner)},
    )
    return AttachedOwnerIdentity(owner_user_id=owner)


def clear_owner_identity(session: Session, *, apply_guc: bool | None = None) -> None:
    """Best-effort clear; transaction end also drops SET LOCAL values."""
    do_guc = runtime_db_identity_enabled() if apply_guc is None else bool(apply_guc)
    if not do_guc:
        return
    session.execute(
        text("SELECT set_config(:guc, '', true)"),
        {"guc": _GUC_SUB},
    )


def require_attached_owner(identity: AttachedOwnerIdentity | None) -> uuid.UUID:
    if identity is None:
        raise ValueError("owner_identity_missing")
    return parse_owner_uuid(identity.owner_user_id)


@contextmanager
def owner_scoped_session(
    session: Session,
    *,
    owner_user_id: uuid.UUID,
) -> Generator[AttachedOwnerIdentity, None, None]:
    """
    Attach verified owner for the duration of a repository unit of work.

    Callers must commit/rollback the SQLAlchemy session themselves.
    Identity is cleared in finally when GUC mode is enabled.
    """
    attached = attach_owner_identity(session, owner_user_id=owner_user_id)
    try:
        yield attached
    finally:
        try:
            clear_owner_identity(session)
        except Exception:  # noqa: BLE001 — never mask original errors
            pass


def assert_write_owner_matches(
    *,
    principal_owner: uuid.UUID,
    row_owner: uuid.UUID,
) -> None:
    if principal_owner != row_owner:
        raise PermissionError("owner_mismatch")


class IdentityLeakTracker:
    """Offline / mock helper for concurrent request identity isolation tests."""

    def __init__(self) -> None:
        self._active: dict[str, str] = {}

    def begin(self, request_id: str, owner: uuid.UUID) -> None:
        if request_id in self._active:
            raise RuntimeError("request_identity_already_active")
        self._active[request_id] = str(owner)

    def end(self, request_id: str) -> None:
        self._active.pop(request_id, None)

    def active_owners(self) -> list[str]:
        return sorted(self._active.values())

    def assert_isolated(self, request_id: str, owner: uuid.UUID) -> None:
        current = self._active.get(request_id)
        if current != str(owner):
            raise ValueError("identity_isolation_violation")
