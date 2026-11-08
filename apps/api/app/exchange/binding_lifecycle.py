"""Durable binding lifecycle design (Part 6C).

Offline / fail-closed helpers for transactional state transitions.
Does not perform cloud writes. Persistence remains gated.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeAccountBinding,
    ExchangeEnvironment,
    ExchangeProvider,
    BindingStore,
    get_owned_binding,
)
from apps.api.app.exchange.credential_registry import (
    CredentialRecord,
    CredentialVerificationState,
    assert_credential_owned_by,
)
from apps.api.app.exchange.credential_verification import (
    VerificationGates,
    VerificationOutcome,
    activation_allowed_after_verification,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BindingLifecycleEvent(str, Enum):
    PENDING_CREATED = "binding_pending_created"
    ACTIVATION_DENIED = "binding_activation_denied"
    ACTIVATED = "binding_activated"
    REVOKED = "binding_revoked"
    MARKED_ERROR = "binding_marked_error"
    CREDENTIAL_ROTATED = "binding_credential_rotated"
    ROLLBACK = "binding_txn_rollback"


@dataclass(frozen=True, slots=True)
class BindingAuditEvent:
    event: BindingLifecycleEvent
    binding_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    detail: str
    at: datetime = field(default_factory=_utc_now)
    # Never include secrets or raw credential material.


@dataclass(frozen=True, slots=True)
class PersistenceRuntimeGates:
    """Extra gates beyond EXCHANGE_BINDING_PERSISTENCE_ENABLED."""

    persistence_flag_enabled: bool = False
    operator_approved: bool = False
    auth_e2e_passed: bool = False
    least_privilege_role_applied: bool = False


def assert_durable_persistence_allowed(gates: PersistenceRuntimeGates) -> None:
    """Fail-closed: flipping one env flag alone must not enable cloud writes."""
    if not gates.persistence_flag_enabled:
        raise ValueError("binding_persistence_disabled")
    if not gates.operator_approved:
        raise ValueError("binding_persistence_operator_approval_required")
    if not gates.auth_e2e_passed:
        raise ValueError("auth_e2e_required_for_persistence")
    if not gates.least_privilege_role_applied:
        raise ValueError("least_privilege_db_role_required")


# Legal transitions for durable bindings (revoked/error are terminal for activation).
_ALLOWED_TRANSITIONS: dict[BindingStatus, frozenset[BindingStatus]] = {
    BindingStatus.PENDING: frozenset(
        {BindingStatus.ACTIVE, BindingStatus.REVOKED, BindingStatus.ERROR}
    ),
    BindingStatus.ACTIVE: frozenset({BindingStatus.REVOKED, BindingStatus.ERROR}),
    BindingStatus.ERROR: frozenset({BindingStatus.REVOKED, BindingStatus.PENDING}),
    BindingStatus.REVOKED: frozenset(),  # terminal — never implicit reactivate
}


def assert_transition_allowed(
    current: BindingStatus, target: BindingStatus
) -> None:
    if target is current:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError("illegal_binding_status_transition")
    if current is BindingStatus.REVOKED and target is BindingStatus.ACTIVE:
        raise ValueError("revoked_binding_cannot_reactivate")


@dataclass
class BindingLifecycleService:
    """
    Transactional lifecycle over a BindingStore.

    For Part 6C tests this wraps InMemoryBindingStore with an explicit
    commit/rollback buffer. Production would map to a DB transaction.
    """

    store: BindingStore
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _audit: list[BindingAuditEvent] = field(default_factory=list)
    _pending_upserts: dict[uuid.UUID, ExchangeAccountBinding] = field(
        default_factory=dict
    )
    _in_txn: bool = False

    def begin(self) -> None:
        with self._lock:
            if self._in_txn:
                raise ValueError("transaction_already_open")
            self._in_txn = True
            self._pending_upserts.clear()

    def commit(self) -> None:
        with self._lock:
            if not self._in_txn:
                raise ValueError("no_transaction")
            for binding in self._pending_upserts.values():
                self.store.upsert(binding)
            self._pending_upserts.clear()
            self._in_txn = False

    def rollback(self) -> None:
        with self._lock:
            self._pending_upserts.clear()
            self._in_txn = False
            self._audit.append(
                BindingAuditEvent(
                    event=BindingLifecycleEvent.ROLLBACK,
                    binding_id=None,
                    owner_user_id=None,
                    detail="transaction_rolled_back",
                )
            )

    def _stage(self, binding: ExchangeAccountBinding) -> ExchangeAccountBinding:
        if self._in_txn:
            self._pending_upserts[binding.id] = binding
            return binding
        return self.store.upsert(binding)

    def _read(self, binding_id: uuid.UUID) -> ExchangeAccountBinding | None:
        if self._in_txn and binding_id in self._pending_upserts:
            return self._pending_upserts[binding_id]
        return self.store.get(binding_id)

    def audit_log(self) -> list[BindingAuditEvent]:
        return list(self._audit)

    def transition(
        self,
        *,
        owner_user_id: uuid.UUID,
        binding_id: uuid.UUID,
        target: BindingStatus,
        detail: str,
    ) -> ExchangeAccountBinding:
        with self._lock:
            binding = get_owned_binding(
                _LifecycleStoreView(self),
                owner_user_id=owner_user_id,
                binding_id=binding_id,
            )
            assert_transition_allowed(binding.status, target)
            now = _utc_now()
            updated = ExchangeAccountBinding(
                id=binding.id,
                owner_user_id=binding.owner_user_id,
                provider=binding.provider,
                environment=binding.environment,
                status=target,
                display_label=binding.display_label,
                credential_ref=binding.credential_ref,
                telemetry_scope_id=binding.telemetry_scope_id,
                enrollment_attestation=binding.enrollment_attestation,
                organization_id=binding.organization_id,
                enrolled_by_operator=binding.enrolled_by_operator,
                created_at=binding.created_at,
                updated_at=now,
            )
            staged = self._stage(updated)
            event = {
                BindingStatus.ACTIVE: BindingLifecycleEvent.ACTIVATED,
                BindingStatus.REVOKED: BindingLifecycleEvent.REVOKED,
                BindingStatus.ERROR: BindingLifecycleEvent.MARKED_ERROR,
                BindingStatus.PENDING: BindingLifecycleEvent.PENDING_CREATED,
            }.get(target, BindingLifecycleEvent.MARKED_ERROR)
            self._audit.append(
                BindingAuditEvent(
                    event=event,
                    binding_id=binding.id,
                    owner_user_id=owner_user_id,
                    detail=detail[:200],
                )
            )
            return staged

    def activate_fail_closed(
        self,
        *,
        owner_user_id: uuid.UUID,
        binding_id: uuid.UUID,
        credential: CredentialRecord,
        verification: VerificationOutcome,
        verification_gates: VerificationGates,
        persistence_gates: PersistenceRuntimeGates,
    ) -> ExchangeAccountBinding:
        """
        Explicit activation path — never auto-enables private reads.

        Separates: enrolled → verified → durable → activated → private reads.
        """
        with self._lock:
            try:
                assert_durable_persistence_allowed(persistence_gates)
            except ValueError as exc:
                self._audit.append(
                    BindingAuditEvent(
                        event=BindingLifecycleEvent.ACTIVATION_DENIED,
                        binding_id=binding_id,
                        owner_user_id=owner_user_id,
                        detail=str(exc),
                    )
                )
                raise

            allowed, reason = activation_allowed_after_verification(
                verification=verification, gates=verification_gates
            )
            if not allowed:
                self._audit.append(
                    BindingAuditEvent(
                        event=BindingLifecycleEvent.ACTIVATION_DENIED,
                        binding_id=binding_id,
                        owner_user_id=owner_user_id,
                        detail=reason or "activation_denied",
                    )
                )
                raise ValueError(reason or "activation_denied")

            assert_credential_owned_by(credential, owner_user_id=owner_user_id)
            if credential.verification_state is not CredentialVerificationState.VERIFIED:
                raise ValueError("credential_not_verified")
            if credential.environment is ExchangeEnvironment.MAINNET:
                raise ValueError("mainnet_binding_locked")

            binding = get_owned_binding(
                _LifecycleStoreView(self),
                owner_user_id=owner_user_id,
                binding_id=binding_id,
            )
            if binding.provider is not ExchangeProvider.BYBIT:
                raise ValueError("provider_unsupported")
            # Credential public_ref must match binding opaque ref after assignment.
            if binding.credential_ref != credential.public_ref:
                raise ValueError("credential_binding_ref_mismatch")

            return self.transition(
                owner_user_id=owner_user_id,
                binding_id=binding_id,
                target=BindingStatus.ACTIVE,
                detail="explicit_activation",
            )

    def rotate_binding_credential_ref(
        self,
        *,
        owner_user_id: uuid.UUID,
        binding_id: uuid.UUID,
        new_public_ref: str,
    ) -> ExchangeAccountBinding:
        """Propagate credential rotation to binding metadata (no secrets)."""
        with self._lock:
            binding = get_owned_binding(
                _LifecycleStoreView(self),
                owner_user_id=owner_user_id,
                binding_id=binding_id,
            )
            if binding.status is BindingStatus.REVOKED:
                raise ValueError("cannot_rotate_revoked_binding")
            if new_public_ref.startswith("env:"):
                raise ValueError("operator_credential_not_user_claimable")
            now = _utc_now()
            updated = ExchangeAccountBinding(
                id=binding.id,
                owner_user_id=binding.owner_user_id,
                provider=binding.provider,
                environment=binding.environment,
                # Rotation forces re-verification — drop to PENDING if was ACTIVE.
                status=(
                    BindingStatus.PENDING
                    if binding.status is BindingStatus.ACTIVE
                    else binding.status
                ),
                display_label=binding.display_label,
                credential_ref=new_public_ref.strip()[:128],
                telemetry_scope_id=binding.telemetry_scope_id,
                enrollment_attestation=binding.enrollment_attestation,
                organization_id=binding.organization_id,
                enrolled_by_operator=binding.enrolled_by_operator,
                created_at=binding.created_at,
                updated_at=now,
            )
            staged = self._stage(updated)
            self._audit.append(
                BindingAuditEvent(
                    event=BindingLifecycleEvent.CREDENTIAL_ROTATED,
                    binding_id=binding.id,
                    owner_user_id=owner_user_id,
                    detail="credential_ref_rotated_reverify_required",
                )
            )
            return staged


class _LifecycleStoreView:
    """Adapter so get_owned_binding can see staged txn rows."""

    def __init__(self, svc: BindingLifecycleService) -> None:
        self._svc = svc

    def get(self, binding_id: uuid.UUID) -> ExchangeAccountBinding | None:
        return self._svc._read(binding_id)

    def list_for_owner(self, owner_user_id: uuid.UUID) -> list[ExchangeAccountBinding]:
        return self._svc.store.list_for_owner(owner_user_id)

    def find_active(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._svc.store.find_active(**kwargs)

    def find_active_by_credential_ref(self, **kwargs):  # type: ignore[no-untyped-def]
        return self._svc.store.find_active_by_credential_ref(**kwargs)

    def find_by_telemetry_scope(self, telemetry_scope_id: str):
        return self._svc.store.find_by_telemetry_scope(telemetry_scope_id)

    def upsert(self, binding: ExchangeAccountBinding) -> ExchangeAccountBinding:
        return self._svc._stage(binding)
