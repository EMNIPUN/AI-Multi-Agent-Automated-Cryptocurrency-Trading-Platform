"""Server-controlled Bybit credential registry (Part 6B).

Design + offline fixtures only. No live secret intake, no cloud persistence,
no real Bybit verification in this phase.

Client-supplied credential_ref strings are never proof of ownership.
Environment-backed operator refs (env:BYBIT_*) stay operator-managed until
explicitly enrolled and assigned.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from apps.api.app.exchange.bindings import ExchangeEnvironment, ExchangeProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CredentialPermissionClass(str, Enum):
    """Declared intended permissions — never trust client claims alone."""

    READ_ONLY = "read_only"
    TRADE = "trade"  # must never be accepted for onboarding in Part 6B+ gates
    WITHDRAW = "withdraw"  # forbidden for CryptoNova wallet binding path


class CredentialVerificationState(str, Enum):
    UNVERIFIED = "unverified"
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"
    FAILED = "failed"
    REVOKED = "revoked"
    ROTATED = "rotated"


@dataclass(frozen=True, slots=True)
class CredentialRecord:
    """Owned credential metadata — secrets live only behind secret_storage_ref."""

    id: uuid.UUID
    owner_user_id: uuid.UUID | None
    provider: ExchangeProvider
    environment: ExchangeEnvironment
    # Opaque public alias (e.g. cred:… or pending:…). Never a raw API key.
    public_ref: str
    # Pointer into vault/KMS/env map — never logged, never returned to browser.
    secret_storage_ref: str
    permission_class: CredentialPermissionClass
    verification_state: CredentialVerificationState
    operator_managed: bool
    created_at: datetime = field(default_factory=_utc_now)
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    last_verified_at: datetime | None = None
    # Exchange account identity fingerprint after verification (non-secret).
    exchange_account_fingerprint: str | None = None

    @property
    def is_assignable_to_user_binding(self) -> bool:
        return (
            self.verification_state is CredentialVerificationState.VERIFIED
            and self.permission_class is CredentialPermissionClass.READ_ONLY
            and self.revoked_at is None
        )


class CredentialRegistry(Protocol):
    def get(self, credential_id: uuid.UUID) -> CredentialRecord | None: ...

    def get_by_public_ref(self, public_ref: str) -> CredentialRecord | None: ...

    def list_for_owner(self, owner_user_id: uuid.UUID) -> list[CredentialRecord]: ...

    def upsert(self, record: CredentialRecord) -> CredentialRecord: ...


class InMemoryCredentialRegistry:
    """Offline / test registry — ephemeral process memory only."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, CredentialRecord] = {}

    def upsert(self, record: CredentialRecord) -> CredentialRecord:
        self._rows[record.id] = record
        return record

    def get(self, credential_id: uuid.UUID) -> CredentialRecord | None:
        return self._rows.get(credential_id)

    def get_by_public_ref(self, public_ref: str) -> CredentialRecord | None:
        ref = (public_ref or "").strip()
        for row in self._rows.values():
            if row.public_ref == ref:
                return row
        return None

    def list_for_owner(self, owner_user_id: uuid.UUID) -> list[CredentialRecord]:
        return [r for r in self._rows.values() if r.owner_user_id == owner_user_id]


# Built-in operator env credentials — not user-claimable.
OPERATOR_ENV_PUBLIC_REFS: frozenset[str] = frozenset(
    {
        "env:BYBIT_OPERATOR",
        "env:BYBIT_TESTNET_OPERATOR",
        "env:BYBIT_MAINNET_OPERATOR",
        "env:BYBIT_DEMO_OPERATOR",
    }
)


def is_operator_managed_public_ref(public_ref: str) -> bool:
    return (public_ref or "").strip() in OPERATOR_ENV_PUBLIC_REFS


def assert_user_cannot_claim_operator_ref(public_ref: str) -> None:
    if is_operator_managed_public_ref(public_ref):
        raise ValueError("operator_credential_not_user_claimable")


def assert_credential_owned_by(
    record: CredentialRecord, *, owner_user_id: uuid.UUID
) -> None:
    if record.owner_user_id is None:
        raise ValueError("credential_unassigned")
    if record.owner_user_id != owner_user_id:
        raise ValueError("credential_ownership_mismatch")


def redact_secret_material(text: str) -> str:
    """Best-effort redaction for audit/log strings — never a substitute for not logging."""
    lowered = text.lower()
    banned = ("api_secret", "apisecret", "api-key", "apikey", "secret=", "password")
    if any(token in lowered for token in banned):
        return "[redacted]"
    if len(text) > 64 and text.isalnum():
        return f"{text[:4]}…[redacted]"
    return text


def public_credential_view(record: CredentialRecord) -> dict[str, object]:
    """Safe serialization — omits secret_storage_ref and any secret material."""
    return {
        "id": str(record.id),
        "owner_user_id": str(record.owner_user_id) if record.owner_user_id else None,
        "provider": record.provider.value,
        "environment": record.environment.value,
        "public_ref": record.public_ref,
        "permission_class": record.permission_class.value,
        "verification_state": record.verification_state.value,
        "operator_managed": record.operator_managed,
        "created_at": record.created_at.isoformat(),
        "rotated_at": record.rotated_at.isoformat() if record.rotated_at else None,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        "last_verified_at": (
            record.last_verified_at.isoformat() if record.last_verified_at else None
        ),
        "exchange_account_fingerprint": record.exchange_account_fingerprint,
        # Explicit: secret pointer never leaves the server boundary in this view.
        "secret_storage_ref_present": bool(record.secret_storage_ref),
    }


def rotate_credential_record(
    registry: CredentialRegistry,
    *,
    credential_id: uuid.UUID,
    new_secret_storage_ref: str,
    actor_owner_user_id: uuid.UUID | None,
    operator_attestation: str | None = None,
) -> CredentialRecord:
    """
    Design helper: mark prior record rotated and insert successor metadata.

    Does not touch vault material. Requires owner match or operator attestation.
    """
    current = registry.get(credential_id)
    if current is None:
        raise ValueError("credential_not_found")
    if current.revoked_at is not None:
        raise ValueError("credential_already_revoked")
    if current.operator_managed:
        if not (operator_attestation or "").strip():
            raise ValueError("operator_attestation_required")
    else:
        if actor_owner_user_id is None or current.owner_user_id != actor_owner_user_id:
            raise ValueError("credential_ownership_mismatch")
    if not (new_secret_storage_ref or "").strip():
        raise ValueError("secret_storage_ref_required")
    if "secret" in new_secret_storage_ref.lower() and "=" in new_secret_storage_ref:
        raise ValueError("secret_storage_ref_must_be_opaque")

    now = _utc_now()
    retired = CredentialRecord(
        id=current.id,
        owner_user_id=current.owner_user_id,
        provider=current.provider,
        environment=current.environment,
        public_ref=current.public_ref,
        secret_storage_ref=current.secret_storage_ref,
        permission_class=current.permission_class,
        verification_state=CredentialVerificationState.ROTATED,
        operator_managed=current.operator_managed,
        created_at=current.created_at,
        rotated_at=now,
        revoked_at=current.revoked_at,
        last_verified_at=current.last_verified_at,
        exchange_account_fingerprint=current.exchange_account_fingerprint,
    )
    registry.upsert(retired)

    successor = CredentialRecord(
        id=uuid.uuid4(),
        owner_user_id=current.owner_user_id,
        provider=current.provider,
        environment=current.environment,
        public_ref=f"cred:{uuid.uuid4().hex[:16]}",
        secret_storage_ref=new_secret_storage_ref.strip()[:256],
        permission_class=CredentialPermissionClass.READ_ONLY,
        verification_state=CredentialVerificationState.UNVERIFIED,
        operator_managed=current.operator_managed,
        created_at=now,
        rotated_at=None,
        revoked_at=None,
        last_verified_at=None,
        exchange_account_fingerprint=None,
    )
    return registry.upsert(successor)


def revoke_credential_record(
    registry: CredentialRegistry,
    *,
    credential_id: uuid.UUID,
    actor_owner_user_id: uuid.UUID | None,
    operator_attestation: str | None = None,
) -> CredentialRecord:
    current = registry.get(credential_id)
    if current is None:
        raise ValueError("credential_not_found")
    if current.operator_managed:
        if not (operator_attestation or "").strip():
            raise ValueError("operator_attestation_required")
    else:
        if actor_owner_user_id is None or current.owner_user_id != actor_owner_user_id:
            raise ValueError("credential_ownership_mismatch")
    now = _utc_now()
    revoked = CredentialRecord(
        id=current.id,
        owner_user_id=current.owner_user_id,
        provider=current.provider,
        environment=current.environment,
        public_ref=current.public_ref,
        secret_storage_ref=current.secret_storage_ref,
        permission_class=current.permission_class,
        verification_state=CredentialVerificationState.REVOKED,
        operator_managed=current.operator_managed,
        created_at=current.created_at,
        rotated_at=current.rotated_at,
        revoked_at=now,
        last_verified_at=current.last_verified_at,
        exchange_account_fingerprint=current.exchange_account_fingerprint,
    )
    return registry.upsert(revoked)
