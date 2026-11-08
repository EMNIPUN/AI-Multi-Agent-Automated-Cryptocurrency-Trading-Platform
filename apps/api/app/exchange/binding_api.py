"""Authenticated exchange binding management (Part 6A).

Mutations default to an in-memory fixture store. Postgres persistence requires
EXCHANGE_BINDING_PERSISTENCE_ENABLED=true and separate operator approval.
Never returns API secrets. Never activates PENDING without a future verified workflow.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.deps import get_current_principal
from apps.api.app.exchange.access import get_binding_store
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeAccountBinding,
    ExchangeEnvironment,
    ExchangeProvider,
    PendingBindingRequestSpec,
    credential_ref_alias,
    get_owned_binding,
    request_pending_binding,
    revoke_owned_binding,
)

router = APIRouter(prefix="/api/v1/exchange/bindings", tags=["exchange-bindings"])


class ExchangeBindingPublic(BaseModel):
    """Public binding DTO — no secrets, no raw keys."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    environment: str
    status: str
    display_label: str
    credential_ref_alias: str
    last_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    persistence: str = Field(description="fixture | persisted")
    is_live_exchange_connection: bool = False
    activation_blocked_reason: str | None = None
    # Part 6D — simulated Testnet verification (never implies ACTIVE/LIVE).
    verification_status: str = "unverified"
    verification_simulated: bool = True
    verification_message: str | None = None
    exchange_account_fingerprint: str | None = None


class ExchangeBindingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExchangeBindingPublic]
    private_data_reads_enabled: bool
    binding_persistence_enabled: bool
    auth_e2e_verified: bool = False
    mainnet_activation_locked: bool = True


class CreatePendingBindingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str = "testnet"
    display_label: str = "Bybit account"
    # Optional opaque ref only — ignored owner_user_id if clients send it (extra=forbid).
    credential_ref: str | None = None

    @field_validator("environment")
    @classmethod
    def _env(cls, value: str) -> str:
        text = (value or "").strip().lower()
        if text not in {"testnet", "mainnet", "demo"}:
            raise ValueError("invalid_environment")
        return text

    @field_validator("display_label")
    @classmethod
    def _label(cls, value: str) -> str:
        text = (value or "").strip()[:128]
        return text or "Bybit account"

    @field_validator("credential_ref")
    @classmethod
    def _ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 128:
            raise ValueError("credential_ref_invalid")
        return text


def _owner_uuid(principal: AuthenticatedPrincipal) -> uuid.UUID:
    try:
        return uuid.UUID(str(principal.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="invalid_owner_identity") from exc


def get_binding_management_store(
    request: Request, settings: ApiSettings
) -> tuple[object, str]:
    """
    Returns (store, persistence_label).

    When persistence is disabled (Part 6A default), always use the process
    in-memory fixture store — never SqlAlchemy / cloud writes.
    """
    # Part 6C fail-closed: require BOTH persistence flag and explicit operator
    # approval before any SqlAlchemy / cloud-backed store is used.
    persistence_ready = (
        settings.exchange_binding_persistence_enabled
        and settings.exchange_binding_persistence_operator_approved
    )
    if not persistence_ready:
        store = getattr(request.app.state, "exchange_binding_fixture_store", None)
        if store is None:
            store = InMemoryBindingStore()
            request.app.state.exchange_binding_fixture_store = store
        # Keep wallet ownership tests / dual-path aligned when apps only use fixture.
        request.app.state.exchange_binding_store = store
        return store, "fixture"

    store = get_binding_store(request, settings)
    return store, "persisted"


def _sim_state(request: Request | None, binding_id: uuid.UUID) -> dict:
    if request is None:
        return {}
    sims = getattr(request.app.state, "binding_verification_sims", None) or {}
    row = sims.get(str(binding_id))
    return row if isinstance(row, dict) else {}


def _to_public(
    binding: ExchangeAccountBinding,
    *,
    persistence: str,
    request: Request | None = None,
) -> ExchangeBindingPublic:
    live = (
        binding.status is BindingStatus.ACTIVE
        and persistence == "persisted"
        and not binding.credential_ref.startswith("pending:")
    )
    blocked: str | None = None
    if binding.status is BindingStatus.PENDING:
        blocked = "pending_requires_verified_activation_workflow"
    elif binding.status is BindingStatus.REVOKED:
        blocked = "revoked"
    elif binding.status is BindingStatus.ERROR:
        blocked = "error"
    elif not live:
        blocked = "fixture_or_unverified_not_live_connection"

    sim = _sim_state(request, binding.id)
    last_verified = sim.get("last_verified_at")
    if isinstance(last_verified, str):
        try:
            last_verified = datetime.fromisoformat(last_verified)
        except ValueError:
            last_verified = None
    elif not isinstance(last_verified, datetime):
        last_verified = None

    return ExchangeBindingPublic(
        id=str(binding.id),
        provider=binding.provider.value,
        environment=binding.environment.value,
        status=binding.status.value,
        display_label=binding.display_label,
        credential_ref_alias=credential_ref_alias(binding.credential_ref),
        last_verified_at=last_verified,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
        persistence=persistence,
        is_live_exchange_connection=live,
        activation_blocked_reason=blocked,
        verification_status=str(sim.get("verification_status") or "unverified"),
        verification_simulated=bool(sim.get("simulated", True)),
        verification_message=(
            str(sim["safe_message"]) if sim.get("safe_message") else None
        ),
        exchange_account_fingerprint=(
            str(sim["fingerprint"]) if sim.get("fingerprint") else None
        ),
    )


def _require_api_enabled(settings: ApiSettings) -> None:
    if not settings.exchange_binding_api_enabled:
        raise HTTPException(status_code=403, detail="exchange_binding_api_disabled")


@router.get("/", response_model=ExchangeBindingListResponse)
@router.get("", response_model=ExchangeBindingListResponse, include_in_schema=False)
def list_my_bindings(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> ExchangeBindingListResponse:
    _require_api_enabled(settings)
    store, persistence = get_binding_management_store(request, settings)
    owner = _owner_uuid(principal)
    items = [
        _to_public(b, persistence=persistence, request=request)
        for b in sorted(
            store.list_for_owner(owner),
            key=lambda b: b.created_at,
            reverse=True,
        )
    ]
    return ExchangeBindingListResponse(
        items=items,
        private_data_reads_enabled=settings.private_data_reads_enabled,
        binding_persistence_enabled=settings.exchange_binding_persistence_enabled,
        auth_e2e_verified=False,
        mainnet_activation_locked=True,
    )


@router.get("/{binding_id}", response_model=ExchangeBindingPublic)
def get_my_binding(
    binding_id: uuid.UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> ExchangeBindingPublic:
    _require_api_enabled(settings)
    store, persistence = get_binding_management_store(request, settings)
    owner = _owner_uuid(principal)
    binding = get_owned_binding(store, owner_user_id=owner, binding_id=binding_id)
    return _to_public(binding, persistence=persistence, request=request)


@router.post("/", response_model=ExchangeBindingPublic, status_code=201)
@router.post("", response_model=ExchangeBindingPublic, status_code=201, include_in_schema=False)
def create_pending_binding(
    body: CreatePendingBindingBody,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> ExchangeBindingPublic:
    _require_api_enabled(settings)
    store, persistence = get_binding_management_store(request, settings)
    owner = _owner_uuid(principal)
    # owner_user_id is never taken from the body (extra=forbid + principal only).
    try:
        env = ExchangeEnvironment(body.environment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_environment") from exc

    try:
        binding = request_pending_binding(
            store,
            owner_user_id=owner,
            spec=PendingBindingRequestSpec(
                environment=env,
                display_label=body.display_label,
                credential_ref=body.credential_ref,
                provider=ExchangeProvider.BYBIT,
            ),
            allow_mainnet=False,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "mainnet_binding_locked":
            raise HTTPException(status_code=403, detail=code) from exc
        if code in {
            "owner_already_has_active_binding_for_environment",
            "credential_ref_already_bound",
        }:
            raise HTTPException(status_code=409, detail=code) from exc
        if code == "operator_credential_not_user_claimable":
            raise HTTPException(status_code=403, detail=code) from exc
        if code in {
            "credential_ref_invalid",
            "credential_ref_must_be_opaque",
            "credential_ref_not_allowlisted",
            "provider_unsupported",
        }:
            raise HTTPException(status_code=400, detail=code) from exc
        raise HTTPException(status_code=400, detail="binding_request_rejected") from exc

    return _to_public(binding, persistence=persistence, request=request)


@router.post("/{binding_id}/revoke", response_model=ExchangeBindingPublic)
def revoke_my_binding(
    binding_id: uuid.UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> ExchangeBindingPublic:
    _require_api_enabled(settings)
    store, persistence = get_binding_management_store(request, settings)
    owner = _owner_uuid(principal)
    binding = revoke_owned_binding(
        store, owner_user_id=owner, binding_id=binding_id
    )
    return _to_public(binding, persistence=persistence, request=request)


class SimulateVerifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding: ExchangeBindingPublic
    verification: dict[str, object]


@router.post("/{binding_id}/simulate-verify", response_model=SimulateVerifyResponse)
def simulate_verify_binding(
    binding_id: uuid.UUID,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    settings: ApiSettings = Depends(get_api_settings),
) -> SimulateVerifyResponse:
    """
    Run Part 6D Testnet verification simulator against an owned binding.

    Always uses an injected fake client (no network). Never activates the binding
    or enables private reads. Status remains pending/fixture unless already set.
    """
    _require_api_enabled(settings)
    store, persistence = get_binding_management_store(request, settings)
    owner = _owner_uuid(principal)
    binding = get_owned_binding(store, owner_user_id=owner, binding_id=binding_id)
    if binding.status is BindingStatus.REVOKED:
        raise HTTPException(status_code=400, detail="cannot_verify_revoked_binding")
    if binding.environment is not ExchangeEnvironment.TESTNET:
        raise HTTPException(status_code=403, detail="mainnet_verification_forbidden")

    from apps.api.app.exchange.bybit_testnet_adapter import (
        BybitTestnetVerificationAdapter,
        FakeBybitTestnetClient,
    )
    from apps.api.app.exchange.credential_registry import (
        CredentialPermissionClass,
        CredentialRecord,
        CredentialVerificationState,
        InMemoryCredentialRegistry,
    )

    # Fixture credential row owned by the caller — never operator env refs.
    registry = getattr(request.app.state, "credential_registry", None)
    if registry is None:
        registry = InMemoryCredentialRegistry()
        request.app.state.credential_registry = registry

    public_ref = binding.credential_ref
    existing = registry.get_by_public_ref(public_ref)
    if existing is None:
        cred = CredentialRecord(
            id=uuid.uuid4(),
            owner_user_id=owner,
            provider=ExchangeProvider.BYBIT,
            environment=ExchangeEnvironment.TESTNET,
            public_ref=public_ref,
            secret_storage_ref="simulator:fixture",
            permission_class=CredentialPermissionClass.READ_ONLY,
            verification_state=CredentialVerificationState.UNVERIFIED,
            operator_managed=False,
        )
        registry.upsert(cred)
        cred_id = cred.id
    else:
        if existing.owner_user_id != owner:
            raise HTTPException(status_code=404, detail="exchange_binding_not_found")
        cred_id = existing.id

    client = getattr(request.app.state, "bybit_testnet_verify_client", None)
    if client is None:
        client = FakeBybitTestnetClient()
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=client, simulated=True
    )
    result = adapter.verify_readonly(
        credential_id=cred_id,
        actor_owner_user_id=owner,
        update_registry=True,
    )

    sims = getattr(request.app.state, "binding_verification_sims", None)
    if sims is None:
        sims = {}
        request.app.state.binding_verification_sims = sims
    sims[str(binding.id)] = {
        "verification_status": "simulated_verified" if result.ok else "simulated_failed",
        "simulated": True,
        "safe_message": result.safe_message,
        "fingerprint": result.exchange_account_fingerprint,
        "last_verified_at": result.audited_at.isoformat() if result.audited_at else None,
        "reason": result.reason,
    }

    # Binding status unchanged — never flip to ACTIVE from simulator.
    public = _to_public(binding, persistence=persistence, request=request)
    return SimulateVerifyResponse(
        binding=public,
        verification=result.to_public_dict(),
    )
