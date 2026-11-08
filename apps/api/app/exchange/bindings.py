"""Exchange account ownership bindings (Phase 3C).

Internal binding IDs are the only ownership authority for authenticated
wallet / telemetry reads. account_fp and client-supplied account IDs are never
proof of ownership. Credentials stay server-side behind credential_ref.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Protocol

from fastapi import HTTPException

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings

# Serializes pending-create idempotency checks (owner/provider/env).
_PENDING_CREATE_LOCK = threading.RLock()


class ExchangeProvider(str, Enum):
    BYBIT = "bybit"


class ExchangeEnvironment(str, Enum):
    TESTNET = "testnet"
    MAINNET = "mainnet"
    DEMO = "demo"


class BindingStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"
    ERROR = "error"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ExchangeAccountBinding:
    """Verified user ↔ exchange-account binding (no raw secrets)."""

    id: uuid.UUID
    owner_user_id: uuid.UUID
    provider: ExchangeProvider
    environment: ExchangeEnvironment
    status: BindingStatus
    display_label: str
    credential_ref: str
    telemetry_scope_id: str
    enrollment_attestation: str
    organization_id: uuid.UUID | None = None
    enrolled_by_operator: bool = True
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @property
    def is_readable(self) -> bool:
        return self.status is BindingStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class OperatorEnrollmentSpec:
    """Operator-only enrollment — never auto-assign to arbitrary users."""

    owner_user_id: uuid.UUID
    environment: ExchangeEnvironment
    credential_ref: str
    display_label: str
    attestation: str
    provider: ExchangeProvider = ExchangeProvider.BYBIT
    organization_id: uuid.UUID | None = None
    activate: bool = False


class BindingStore(Protocol):
    def get(self, binding_id: uuid.UUID) -> ExchangeAccountBinding | None: ...

    def list_for_owner(self, owner_user_id: uuid.UUID) -> list[ExchangeAccountBinding]: ...

    def find_active(
        self,
        *,
        owner_user_id: uuid.UUID,
        provider: ExchangeProvider,
        environment: ExchangeEnvironment,
    ) -> ExchangeAccountBinding | None: ...

    def find_active_by_credential_ref(
        self, *, provider: ExchangeProvider, credential_ref: str
    ) -> ExchangeAccountBinding | None: ...

    def find_by_telemetry_scope(self, telemetry_scope_id: str) -> ExchangeAccountBinding | None: ...

    def upsert(self, binding: ExchangeAccountBinding) -> ExchangeAccountBinding: ...


def enroll_operator_binding(
    store: BindingStore, spec: OperatorEnrollmentSpec
) -> ExchangeAccountBinding:
    """
    Create a binding only with explicit operator attestation.

    Does not assign the operator account to every authenticated user.
    Does not accept client-supplied binding IDs as ownership proof.
    """
    if not str(spec.attestation).strip():
        raise ValueError("enrollment_attestation_required")
    if not str(spec.credential_ref).strip():
        raise ValueError("credential_ref_required")
    if not str(spec.display_label).strip():
        raise ValueError("display_label_required")
    if " " in spec.credential_ref or len(spec.credential_ref) < 3:
        raise ValueError("credential_ref_invalid")
    lowered = spec.credential_ref.lower()
    if any(token in lowered for token in ("secret", "apikey=", "api_key=")):
        raise ValueError("credential_ref_must_be_opaque")
    if any(ch in spec.credential_ref for ch in ("$", "{", "}", "`", ";", "|", "\\")):
        raise ValueError("credential_ref_invalid")
    # Enrollment only accepts server allowlisted refs (no open-ended env injection).
    from apps.api.app.exchange.credentials import is_allowlisted_credential_ref

    if not is_allowlisted_credential_ref(spec.credential_ref):
        raise ValueError("credential_ref_not_allowlisted")

    existing = store.find_active_by_credential_ref(
        provider=spec.provider, credential_ref=spec.credential_ref
    )
    if existing and existing.owner_user_id != spec.owner_user_id:
        raise ValueError("credential_ref_already_bound")

    same = store.find_active(
        owner_user_id=spec.owner_user_id,
        provider=spec.provider,
        environment=spec.environment,
    )
    if same and same.credential_ref != spec.credential_ref:
        raise ValueError("owner_already_has_active_binding_for_environment")

    now = _utc_now()
    binding_id = uuid.uuid4()
    binding = ExchangeAccountBinding(
        id=binding_id,
        owner_user_id=spec.owner_user_id,
        provider=spec.provider,
        environment=spec.environment,
        status=BindingStatus.ACTIVE if spec.activate else BindingStatus.PENDING,
        display_label=spec.display_label.strip()[:128],
        credential_ref=spec.credential_ref.strip()[:128],
        telemetry_scope_id=str(binding_id),
        enrollment_attestation=spec.attestation.strip()[:500],
        organization_id=spec.organization_id,
        enrolled_by_operator=True,
        created_at=now,
        updated_at=now,
    )
    return store.upsert(binding)


def require_active_binding_for_principal(
    *,
    principal: AuthenticatedPrincipal,
    store: BindingStore,
    settings: ApiSettings,
    provider: ExchangeProvider = ExchangeProvider.BYBIT,
    environment: ExchangeEnvironment | None = None,
    requested_binding_id: uuid.UUID | None = None,
) -> ExchangeAccountBinding:
    """
    Fail-closed authorization for authenticated exchange / telemetry reads.

    Client-provided binding IDs are only accepted after ownership is verified
    against the repository. PRIVATE_DATA_READS_ENABLED remains the kill switch.
    """
    if not principal.is_authenticated_user:
        raise HTTPException(status_code=403, detail="forbidden")
    if not settings.private_data_reads_enabled:
        raise HTTPException(status_code=403, detail="ownership_schema_required")

    try:
        owner = uuid.UUID(str(principal.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="invalid_owner_identity") from exc

    if requested_binding_id is not None:
        binding = store.get(requested_binding_id)
        if binding is None:
            raise HTTPException(status_code=403, detail="exchange_binding_not_found")
        if binding.owner_user_id != owner:
            raise HTTPException(status_code=403, detail="cross_tenant_forbidden")
        if not binding.is_readable:
            raise HTTPException(status_code=403, detail="exchange_binding_inactive")
        if environment is not None and binding.environment is not environment:
            raise HTTPException(status_code=403, detail="exchange_environment_mismatch")
        if binding.provider is not provider:
            raise HTTPException(status_code=403, detail="exchange_provider_mismatch")
        return binding

    if environment is not None:
        binding = store.find_active(
            owner_user_id=owner, provider=provider, environment=environment
        )
        if binding is None:
            raise HTTPException(status_code=403, detail="exchange_binding_missing")
        return binding

    owned = [
        b
        for b in store.list_for_owner(owner)
        if b.provider is provider and b.is_readable
    ]
    if len(owned) == 0:
        # Distinguish missing vs non-active (pending/revoked) so UI never shows zero wallet.
        any_owned = [
            b for b in store.list_for_owner(owner) if b.provider is provider
        ]
        if any_owned:
            raise HTTPException(status_code=403, detail="exchange_binding_inactive")
        raise HTTPException(status_code=403, detail="exchange_binding_missing")
    if len(owned) > 1:
        raise HTTPException(status_code=403, detail="exchange_binding_ambiguous")
    return owned[0]


def assert_telemetry_scope_access(
    *,
    principal: AuthenticatedPrincipal,
    store: BindingStore,
    settings: ApiSettings,
    telemetry_scope_id: str,
    environment: ExchangeEnvironment,
) -> ExchangeAccountBinding:
    """Authorize reading a worker ledger scoped to a binding telemetry id."""
    binding = require_active_binding_for_principal(
        principal=principal,
        store=store,
        settings=settings,
        environment=environment,
    )
    if binding.telemetry_scope_id != telemetry_scope_id:
        raise HTTPException(status_code=403, detail="telemetry_scope_forbidden")
    if binding.environment is not environment:
        raise HTTPException(status_code=403, detail="exchange_environment_mismatch")
    return binding


EnvironmentName = Literal["testnet", "mainnet", "demo"]

# Opaque placeholders for user-requested pending bindings — never resolve to API keys.
PENDING_CREDENTIAL_REFS: frozenset[str] = frozenset(
    {
        "pending:bybit-testnet",
        "pending:bybit-mainnet",
        "pending:bybit-demo",
    }
)


@dataclass(frozen=True, slots=True)
class PendingBindingRequestSpec:
    """User self-serve pending request — owner always from verified JWT principal."""

    environment: ExchangeEnvironment
    display_label: str = "Bybit account"
    # Optional opaque ref; must be pending:* or allowlisted. Never a raw secret.
    credential_ref: str | None = None
    provider: ExchangeProvider = ExchangeProvider.BYBIT


def pending_credential_ref_for(environment: ExchangeEnvironment) -> str:
    return f"pending:bybit-{environment.value}"


def credential_ref_alias(credential_ref: str) -> str:
    """Safe display alias — never a secret materialization."""
    ref = (credential_ref or "").strip()
    if not ref:
        return "unassigned"
    if ref.startswith("pending:"):
        return ref
    if ref.startswith("env:"):
        return ref
    # Unknown shapes: show truncated opaque token only.
    if len(ref) <= 12:
        return ref
    return f"{ref[:6]}…{ref[-4:]}"


def request_pending_binding(
    store: BindingStore,
    *,
    owner_user_id: uuid.UUID,
    spec: PendingBindingRequestSpec,
    allow_mainnet: bool = False,
) -> ExchangeAccountBinding:
    """
    Create a PENDING binding owned by the verified user.

    Never activates. Never accepts owner_user_id from the client (caller must
    pass principal.sub). Mainnet locked unless allow_mainnet (future approval).
    """
    if spec.provider is not ExchangeProvider.BYBIT:
        raise ValueError("provider_unsupported")
    if spec.environment is ExchangeEnvironment.MAINNET and not allow_mainnet:
        raise ValueError("mainnet_binding_locked")

    label = (spec.display_label or "Bybit account").strip()[:128] or "Bybit account"
    ref = (spec.credential_ref or pending_credential_ref_for(spec.environment)).strip()
    if not ref or " " in ref or len(ref) < 3:
        raise ValueError("credential_ref_invalid")
    lowered = ref.lower()
    if any(token in lowered for token in ("secret", "apikey=", "api_key=", "api-secret")):
        raise ValueError("credential_ref_must_be_opaque")
    if any(ch in ref for ch in ("$", "{", "}", "`", ";", "|", "\\")):
        raise ValueError("credential_ref_invalid")

    from apps.api.app.exchange.credential_registry import (
        assert_user_cannot_claim_operator_ref,
    )
    from apps.api.app.exchange.credentials import is_allowlisted_credential_ref

    # Part 6B: user self-serve may only attach pending:* placeholders.
    # Operator env:BYBIT_* refs remain operator-managed (enroll_operator_binding).
    assert_user_cannot_claim_operator_ref(ref)
    if ref not in PENDING_CREDENTIAL_REFS:
        # Do not accept arbitrary / allowlisted env refs via user pending API.
        if is_allowlisted_credential_ref(ref):
            raise ValueError("operator_credential_not_user_claimable")
        raise ValueError("credential_ref_not_allowlisted")

    # Idempotent under concurrency: serialize create-or-return for owner/env.
    with _PENDING_CREATE_LOCK:
        for existing in store.list_for_owner(owner_user_id):
            if (
                existing.provider is spec.provider
                and existing.environment is spec.environment
                and existing.status is not BindingStatus.REVOKED
            ):
                if existing.status is BindingStatus.ACTIVE:
                    raise ValueError("owner_already_has_active_binding_for_environment")
                return existing

        now = _utc_now()
        binding_id = uuid.uuid4()
        binding = ExchangeAccountBinding(
            id=binding_id,
            owner_user_id=owner_user_id,
            provider=spec.provider,
            environment=spec.environment,
            status=BindingStatus.PENDING,
            display_label=label,
            credential_ref=ref[:128],
            telemetry_scope_id=str(binding_id),
            enrollment_attestation="user_pending_request_part6a",
            organization_id=None,
            enrolled_by_operator=False,
            created_at=now,
            updated_at=now,
        )
        return store.upsert(binding)


def get_owned_binding(
    store: BindingStore,
    *,
    owner_user_id: uuid.UUID,
    binding_id: uuid.UUID,
) -> ExchangeAccountBinding:
    binding = store.get(binding_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="exchange_binding_not_found")
    if binding.owner_user_id != owner_user_id:
        # Do not leak existence across tenants.
        raise HTTPException(status_code=404, detail="exchange_binding_not_found")
    return binding


def revoke_owned_binding(
    store: BindingStore,
    *,
    owner_user_id: uuid.UUID,
    binding_id: uuid.UUID,
) -> ExchangeAccountBinding:
    binding = get_owned_binding(
        store, owner_user_id=owner_user_id, binding_id=binding_id
    )
    if binding.status is BindingStatus.REVOKED:
        return binding
    now = _utc_now()
    revoked = ExchangeAccountBinding(
        id=binding.id,
        owner_user_id=binding.owner_user_id,
        provider=binding.provider,
        environment=binding.environment,
        status=BindingStatus.REVOKED,
        display_label=binding.display_label,
        credential_ref=binding.credential_ref,
        telemetry_scope_id=binding.telemetry_scope_id,
        enrollment_attestation=binding.enrollment_attestation,
        organization_id=binding.organization_id,
        enrolled_by_operator=binding.enrolled_by_operator,
        created_at=binding.created_at,
        updated_at=now,
    )
    return store.upsert(revoked)
