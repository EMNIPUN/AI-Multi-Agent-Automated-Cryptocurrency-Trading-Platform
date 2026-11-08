"""Bybit Testnet credential verification design (Part 6B).

Deterministic mocks only. No real Bybit HTTP. External calls require future
explicit operator approval + AUTH E2E + security gates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from apps.api.app.exchange.bindings import ExchangeEnvironment
from apps.api.app.exchange.credential_registry import (
    CredentialPermissionClass,
    CredentialRecord,
    CredentialRegistry,
    CredentialVerificationState,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VerificationDenyReason(str, Enum):
    OPERATOR_APPROVAL_REQUIRED = "operator_approval_required"
    MAINNET_FORBIDDEN = "mainnet_verification_forbidden"
    TRADE_PERMISSIONS_FORBIDDEN = "trade_permissions_forbidden"
    AUTH_E2E_REQUIRED = "auth_e2e_required"
    PRIVATE_READS_GATE = "private_reads_still_disabled_for_activation"
    PERSISTENCE_DISABLED = "binding_persistence_disabled"
    CREDENTIAL_NOT_FOUND = "credential_not_found"
    OWNERSHIP_MISMATCH = "credential_ownership_mismatch"
    ALREADY_REVOKED = "credential_already_revoked"
    EXTERNAL_CALLS_DISABLED = "external_bybit_calls_disabled"
    MOCK_KEY_INVALID = "mock_key_invalid"


@dataclass(frozen=True, slots=True)
class VerificationGates:
    """Fail-closed gates for any future live verification."""

    operator_approved: bool = False
    auth_e2e_passed: bool = False
    binding_persistence_enabled: bool = False
    private_data_reads_enabled: bool = False
    allow_external_bybit_calls: bool = False


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    ok: bool
    reason: str | None
    exchange_account_fingerprint: str | None = None
    audited_at: datetime | None = None
    # Never includes secrets.
    audit_event: str | None = None


def verify_testnet_credential_readonly(
    registry: CredentialRegistry,
    *,
    credential_id: uuid.UUID,
    actor_owner_user_id: uuid.UUID,
    gates: VerificationGates,
    mock_key_valid: bool = True,
) -> VerificationOutcome:
    """
    Future Testnet signed read-only verification workflow (mocked).

    Steps when gates open (not in Part 6B):
    1. Operator approval
    2. Testnet-only
    3. Read-only permission class
    4. Signed Bybit read (wallet/account info) — not implemented here
    5. Bind fingerprint to owner
    6. Record outcome without secrets
    7. Separately approved PENDING→ACTIVE (not performed here)
    """
    record = registry.get(credential_id)
    if record is None:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.CREDENTIAL_NOT_FOUND.value
        )
    if record.revoked_at is not None:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.ALREADY_REVOKED.value
        )
    if record.owner_user_id != actor_owner_user_id:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.OWNERSHIP_MISMATCH.value
        )
    if record.environment is ExchangeEnvironment.MAINNET:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.MAINNET_FORBIDDEN.value
        )
    if record.permission_class is not CredentialPermissionClass.READ_ONLY:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.TRADE_PERMISSIONS_FORBIDDEN.value
        )
    if not gates.operator_approved:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.OPERATOR_APPROVAL_REQUIRED.value
        )
    if not gates.auth_e2e_passed:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.AUTH_E2E_REQUIRED.value
        )
    if not gates.binding_persistence_enabled:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.PERSISTENCE_DISABLED.value
        )
    # Activation of private reads is a separate Gate F — verification may still
    # record identity, but Part 6B keeps this fail-closed for the full path.
    if gates.private_data_reads_enabled:
        # Still require explicit external-call flag; never auto-enable.
        pass
    if not gates.allow_external_bybit_calls:
        return VerificationOutcome(
            ok=False, reason=VerificationDenyReason.EXTERNAL_CALLS_DISABLED.value
        )
    if not mock_key_valid:
        now = _utc_now()
        failed = CredentialRecord(
            id=record.id,
            owner_user_id=record.owner_user_id,
            provider=record.provider,
            environment=record.environment,
            public_ref=record.public_ref,
            secret_storage_ref=record.secret_storage_ref,
            permission_class=record.permission_class,
            verification_state=CredentialVerificationState.FAILED,
            operator_managed=record.operator_managed,
            created_at=record.created_at,
            rotated_at=record.rotated_at,
            revoked_at=record.revoked_at,
            last_verified_at=None,
            exchange_account_fingerprint=None,
        )
        registry.upsert(failed)
        return VerificationOutcome(
            ok=False,
            reason=VerificationDenyReason.MOCK_KEY_INVALID.value,
            audited_at=now,
            audit_event="bybit_testnet_verification_failed",
        )

    # Live path would call Bybit here — intentionally unreachable without gates.
    now = _utc_now()
    fingerprint = f"bybit-testnet:{uuid.uuid4().hex[:12]}"
    verified = CredentialRecord(
        id=record.id,
        owner_user_id=record.owner_user_id,
        provider=record.provider,
        environment=record.environment,
        public_ref=record.public_ref,
        secret_storage_ref=record.secret_storage_ref,
        permission_class=record.permission_class,
        verification_state=CredentialVerificationState.VERIFIED,
        operator_managed=record.operator_managed,
        created_at=record.created_at,
        rotated_at=record.rotated_at,
        revoked_at=record.revoked_at,
        last_verified_at=now,
        exchange_account_fingerprint=fingerprint,
    )
    registry.upsert(verified)
    return VerificationOutcome(
        ok=True,
        reason=None,
        exchange_account_fingerprint=fingerprint,
        audited_at=now,
        audit_event="bybit_testnet_verification_ok",
    )


def activation_allowed_after_verification(
    *,
    verification: VerificationOutcome,
    gates: VerificationGates,
) -> tuple[bool, str | None]:
    """PENDING→ACTIVE is a separate approved step — never implied by verify alone."""
    if not verification.ok:
        return False, verification.reason or "verification_failed"
    if not gates.operator_approved:
        return False, VerificationDenyReason.OPERATOR_APPROVAL_REQUIRED.value
    if not gates.auth_e2e_passed:
        return False, VerificationDenyReason.AUTH_E2E_REQUIRED.value
    if not gates.binding_persistence_enabled:
        return False, VerificationDenyReason.PERSISTENCE_DISABLED.value
    # Even after verify, Part 6B does not perform ACTIVE transition.
    return False, "activation_requires_separate_operator_workflow"
