"""Phase 3C Part 6B — credential registry, ownership, verification mocks."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeEnvironment,
    ExchangeProvider,
    require_active_binding_for_principal,
)
from apps.api.app.exchange.credential_registry import (
    CredentialPermissionClass,
    CredentialRecord,
    CredentialVerificationState,
    InMemoryCredentialRegistry,
    assert_credential_owned_by,
    assert_user_cannot_claim_operator_ref,
    public_credential_view,
    redact_secret_material,
    revoke_credential_record,
    rotate_credential_record,
)
from apps.api.app.exchange.credential_verification import (
    VerificationGates,
    activation_allowed_after_verification,
    verify_testnet_credential_readonly,
)
from apps.api.app.factory import create_app
from fastapi import HTTPException


USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _settings(**kwargs) -> ApiSettings:
    clear_settings_cache()
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        private_data_reads_enabled=False,
        observability_fixture_mode=True,
        observability_live_stream_enabled=False,
        observability_ledger_path=None,
        exchange_wallet_reads_enabled=True,
        exchange_binding_api_enabled=True,
        exchange_binding_persistence_enabled=False,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _principal(user_id: uuid.UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=str(user_id), role="authenticated")


def _app():
    settings = _settings()
    app = create_app(settings)
    store = InMemoryBindingStore()
    app.state.exchange_binding_fixture_store = store
    app.state.exchange_binding_store = store
    app.state.token_verifier = StaticMappingVerifier(
        {"token-a": _principal(USER_A), "token-b": _principal(USER_B)}
    )
    return app, store, settings


def _user_cred(
    registry: InMemoryCredentialRegistry,
    owner: uuid.UUID,
    *,
    env: ExchangeEnvironment = ExchangeEnvironment.TESTNET,
) -> CredentialRecord:
    rec = CredentialRecord(
        id=uuid.uuid4(),
        owner_user_id=owner,
        provider=ExchangeProvider.BYBIT,
        environment=env,
        public_ref=f"cred:{uuid.uuid4().hex[:12]}",
        secret_storage_ref="vault:mock/path",
        permission_class=CredentialPermissionClass.READ_ONLY,
        verification_state=CredentialVerificationState.UNVERIFIED,
        operator_managed=False,
    )
    return registry.upsert(rec)


def test_user_cannot_claim_operator_env_ref_via_pending_api() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    res = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={
            "environment": "testnet",
            "credential_ref": "env:BYBIT_TESTNET_OPERATOR",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "operator_credential_not_user_claimable"


def test_assert_user_cannot_claim_operator_ref_helper() -> None:
    try:
        assert_user_cannot_claim_operator_ref("env:BYBIT_MAINNET_OPERATOR")
        raise AssertionError("expected deny")
    except ValueError as exc:
        assert str(exc) == "operator_credential_not_user_claimable"


def test_cross_user_binding_isolation_still_holds() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    created = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert (
        client.get(
            f"/api/v1/exchange/bindings/{created['id']}",
            headers={"Authorization": "Bearer token-b"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/exchange/bindings/{created['id']}/revoke",
            headers={"Authorization": "Bearer token-b"},
        ).status_code
        == 404
    )


def test_duplicate_pending_idempotent_under_repeat() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    ids = []
    for _ in range(5):
        res = client.post(
            "/api/v1/exchange/bindings",
            headers={"Authorization": "Bearer token-a"},
            json={"environment": "testnet"},
        )
        assert res.status_code == 201
        ids.append(res.json()["id"])
    assert len(set(ids)) == 1


def test_pending_revoked_never_authorize_private_reads() -> None:
    app, store, settings = _app()
    client = TestClient(app)
    pending = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert pending["persistence"] == "fixture"
    assert pending["is_live_exchange_connection"] is False
    settings_on = _settings(private_data_reads_enabled=True)
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_A),
            store=store,
            settings=settings_on,
            requested_binding_id=uuid.UUID(pending["id"]),
        )
        raise AssertionError("expected inactive")
    except HTTPException as exc:
        assert exc.detail == "exchange_binding_inactive"

    client.post(
        f"/api/v1/exchange/bindings/{pending['id']}/revoke",
        headers={"Authorization": "Bearer token-a"},
    )
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_A),
            store=store,
            settings=settings_on,
            requested_binding_id=uuid.UUID(pending["id"]),
        )
        raise AssertionError("expected inactive")
    except HTTPException as exc:
        assert exc.detail == "exchange_binding_inactive"


def test_mainnet_still_locked() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    res = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "mainnet"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "mainnet_binding_locked"


def test_secret_redaction_and_public_view_omits_storage_ref() -> None:
    registry = InMemoryCredentialRegistry()
    rec = _user_cred(registry, USER_A)
    view = public_credential_view(rec)
    assert "secret_storage_ref" not in view
    assert view["secret_storage_ref_present"] is True
    assert "api_secret" not in str(view).lower()
    assert redact_secret_material("api_secret=abc123") == "[redacted]"
    assert redact_secret_material("pending:bybit-testnet") == "pending:bybit-testnet"


def test_credential_ownership_mismatch() -> None:
    registry = InMemoryCredentialRegistry()
    rec = _user_cred(registry, USER_A)
    try:
        assert_credential_owned_by(rec, owner_user_id=USER_B)
        raise AssertionError("expected mismatch")
    except ValueError as exc:
        assert str(exc) == "credential_ownership_mismatch"


def test_duplicate_enrollment_operator_ref_still_blocked_across_owners() -> None:
    """Operator enrollment path already blocks dual-owner active env refs."""
    from apps.api.app.exchange.bindings import OperatorEnrollmentSpec, enroll_operator_binding

    store = InMemoryBindingStore()
    enroll_operator_binding(
        store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="A",
            attestation="operator ticket A",
            activate=True,
        ),
    )
    try:
        enroll_operator_binding(
            store,
            OperatorEnrollmentSpec(
                owner_user_id=USER_B,
                environment=ExchangeEnvironment.TESTNET,
                credential_ref="env:BYBIT_TESTNET_OPERATOR",
                display_label="B",
                attestation="operator ticket B",
                activate=True,
            ),
        )
        raise AssertionError("expected already bound")
    except ValueError as exc:
        assert str(exc) == "credential_ref_already_bound"


def test_rotation_design_requires_owner_and_opaque_ref() -> None:
    registry = InMemoryCredentialRegistry()
    rec = _user_cred(registry, USER_A)
    try:
        rotate_credential_record(
            registry,
            credential_id=rec.id,
            new_secret_storage_ref="api_secret=leaked",
            actor_owner_user_id=USER_A,
        )
        raise AssertionError("expected opaque deny")
    except ValueError as exc:
        assert str(exc) == "secret_storage_ref_must_be_opaque"

    try:
        rotate_credential_record(
            registry,
            credential_id=rec.id,
            new_secret_storage_ref="vault:new/path",
            actor_owner_user_id=USER_B,
        )
        raise AssertionError("expected ownership deny")
    except ValueError as exc:
        assert str(exc) == "credential_ownership_mismatch"

    successor = rotate_credential_record(
        registry,
        credential_id=rec.id,
        new_secret_storage_ref="vault:new/path",
        actor_owner_user_id=USER_A,
    )
    assert successor.verification_state is CredentialVerificationState.UNVERIFIED
    assert registry.get(rec.id).verification_state is CredentialVerificationState.ROTATED


def test_verification_fail_closed_without_gates() -> None:
    registry = InMemoryCredentialRegistry()
    rec = _user_cred(registry, USER_A)
    gates = VerificationGates()  # all false — Part 6B default posture
    outcome = verify_testnet_credential_readonly(
        registry,
        credential_id=rec.id,
        actor_owner_user_id=USER_A,
        gates=gates,
    )
    assert outcome.ok is False
    assert outcome.reason == "operator_approval_required"

    gates2 = VerificationGates(operator_approved=True, auth_e2e_passed=True)
    outcome2 = verify_testnet_credential_readonly(
        registry,
        credential_id=rec.id,
        actor_owner_user_id=USER_A,
        gates=gates2,
    )
    assert outcome2.ok is False
    assert outcome2.reason == "binding_persistence_disabled"

    mainnet = CredentialRecord(
        id=uuid.uuid4(),
        owner_user_id=USER_A,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.MAINNET,
        public_ref="cred:mainnet",
        secret_storage_ref="vault:x",
        permission_class=CredentialPermissionClass.READ_ONLY,
        verification_state=CredentialVerificationState.UNVERIFIED,
        operator_managed=False,
    )
    registry.upsert(mainnet)
    outcome3 = verify_testnet_credential_readonly(
        registry,
        credential_id=mainnet.id,
        actor_owner_user_id=USER_A,
        gates=VerificationGates(
            operator_approved=True,
            auth_e2e_passed=True,
            binding_persistence_enabled=True,
            allow_external_bybit_calls=True,
        ),
    )
    assert outcome3.ok is False
    assert outcome3.reason == "mainnet_verification_forbidden"


def test_activation_never_implied_by_verification_alone() -> None:
    registry = InMemoryCredentialRegistry()
    rec = _user_cred(registry, USER_A)
    # Force a mock "verified" outcome path with all gates except we still deny activation.
    gates = VerificationGates(
        operator_approved=True,
        auth_e2e_passed=True,
        binding_persistence_enabled=True,
        allow_external_bybit_calls=True,
    )
    outcome = verify_testnet_credential_readonly(
        registry,
        credential_id=rec.id,
        actor_owner_user_id=USER_A,
        gates=gates,
        mock_key_valid=True,
    )
    assert outcome.ok is True
    allowed, reason = activation_allowed_after_verification(
        verification=outcome, gates=gates
    )
    assert allowed is False
    assert reason == "activation_requires_separate_operator_workflow"


def test_revoke_credential_and_no_private_reads_trading_flags() -> None:
    registry = InMemoryCredentialRegistry()
    rec = _user_cred(registry, USER_A)
    revoked = revoke_credential_record(
        registry, credential_id=rec.id, actor_owner_user_id=USER_A
    )
    assert revoked.verification_state is CredentialVerificationState.REVOKED
    settings = _settings()
    assert settings.private_data_reads_enabled is False
    assert settings.exchange_binding_persistence_enabled is False
    # Trading flag lives outside ApiSettings — ensure AGENT_ALLOW_LIVE default posture
    # via factory root contract.
    app, _, _ = _app()
    root = TestClient(app).get("/").json()
    assert root["trading_endpoints"] is False
    assert root["private_catalog_reads_enabled"] is False
    assert root["exchange_binding_persistence_enabled"] is False


def test_fixture_bindings_marked_nonpersistent() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    listed = client.get(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
    ).json()
    assert listed["binding_persistence_enabled"] is False
    created = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert created["persistence"] == "fixture"
    assert created["status"] == BindingStatus.PENDING.value
