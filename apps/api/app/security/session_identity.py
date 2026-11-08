"""Connection-pool tenant identity helpers (Option A / Part 6C).

PostgreSQL RLS for Supabase role `authenticated` uses auth.uid().
FastAPI today connects as BYPASSRLS `postgres`, so GUCs are not authoritative yet.

This module models safe per-request identity attach/reset for a future
`cryptonova_api_runtime` role. See also `db_identity.py` for transaction-local
`set_config` helpers (disabled by default via RUNTIME_DB_IDENTITY_ENABLED).

Trust boundary:
  JWT verification (FastAPI) → principal.user_id → attach_verified_user /
  attach_owner_identity. Never accept client-supplied owner IDs as GUC values.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from apps.api.app.security.db_identity import parse_owner_uuid


@dataclass
class PooledConnectionIdentity:
    """Simulated pool connection that must reset tenant GUCs between checkouts."""

    connection_id: str
    jwt_sub: str | None = None
    role: str | None = None
    dirty: bool = False


@dataclass
class ConnectionIdentityGuard:
    """
    Ensures pooled connections cannot leak prior-request tenant identity.

    Production mapping (after remote Option A approval):
      BEGIN;
      SELECT set_config('request.jwt.claim.sub', :sub, true);  -- SET LOCAL
      -- connection already uses cryptonova_api_runtime credentials (preferred)
      -- or SET LOCAL ROLE only if membership is granted and audited
      -- work --
      -- connection return: discard / RESET ALL / new checkout without prior GUC
    """

    _local: threading.local = field(default_factory=threading.local)
    _pool: dict[str, PooledConnectionIdentity] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def checkout(self, connection_id: str) -> PooledConnectionIdentity:
        with self._lock:
            conn = self._pool.get(connection_id)
            if conn is None:
                conn = PooledConnectionIdentity(connection_id=connection_id)
                self._pool[connection_id] = conn
            # Mandatory reset before reuse — prevents tenant leakage.
            conn.jwt_sub = None
            conn.role = None
            conn.dirty = False
            self._local.connection_id = connection_id
            return conn

    def attach_verified_user(
        self,
        *,
        connection_id: str,
        user_id: uuid.UUID,
        role: str = "cryptonova_api_runtime",
    ) -> None:
        owner = parse_owner_uuid(user_id)
        with self._lock:
            conn = self._pool.get(connection_id)
            if conn is None:
                raise ValueError("connection_not_checked_out")
            # Never trust client-supplied identity without JWT verification upstream.
            conn.jwt_sub = str(owner)
            conn.role = role
            conn.dirty = True

    def current_sub(self, connection_id: str) -> str | None:
        with self._lock:
            conn = self._pool.get(connection_id)
            return conn.jwt_sub if conn else None

    def release(self, connection_id: str) -> None:
        with self._lock:
            conn = self._pool.get(connection_id)
            if conn is None:
                return
            conn.jwt_sub = None
            conn.role = None
            conn.dirty = False

    def assert_no_cross_tenant_leak(
        self, connection_id: str, *, expected_user_id: uuid.UUID | None
    ) -> None:
        sub = self.current_sub(connection_id)
        if expected_user_id is None:
            if sub is not None:
                raise ValueError("tenant_identity_leak_after_release")
            return
        if sub != str(expected_user_id):
            raise ValueError("tenant_identity_mismatch")
