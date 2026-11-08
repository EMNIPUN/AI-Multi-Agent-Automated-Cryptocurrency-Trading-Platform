"""Phase 3C Part 6C — binding persistence preflight (offline only)."""

from __future__ import annotations

import concurrent.futures
import uuid

from fastapi.testclient import TestClient

from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_lifecycle import (
    BindingLifecycleEvent,
    BindingLifecycleService,
    PersistenceRuntimeGates,
    assert_durable_persistence_allowed,
    assert_transition_allowed,
)
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeAccountBinding,
    ExchangeEnvironment,
    ExchangeProvider,
    PendingBindingRequestSpec,
    request_pending_binding,
    require_active_binding_for_principal,
    revoke_owned_binding,
)
from apps.api.app.exchange.credential_registry import (
    CredentialPermissionClass,
    CredentialRecord,
    CredentialVerificationState,
    public_credential_view,
)
from apps.api.app.exchange.credential_verification import (
    VerificationGates,
    VerificationOutcome,
)
from apps.api.app.factory import create_app
from apps.api.app.security.session_identity import ConnectionIdentityGuard
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
        exchange_binding_persistence_operator_approved=False,
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


def _app(**settings_kwargs):
    settings = _settings(**settings_kwargs)
    app = create_app(settings)
    store = InMemoryBindingStore()
    app.state.exchange_binding_fixture_store = store
    app.state.exchange_binding_store = store
    app.state.token_verifier = StaticMappingVerifier(
        {"token-a": _principal(USER_A), "token-b": _principal(USER_B)}
    )
    return app, store, settings


def test_missing_and_invalid_jwt() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    assert client.get("/api/v1/exchange/bindings").status_code == 401
    assert (
        client.get(
            "/api/v1/exchange/bindings",
            headers={"Authorization": "Bearer nope"},
        ).status_code
        == 401
    )


def test_cross_user_access_denied() -> None:
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


def test_persistence_flag_alone_stays_fixture() -> None:
    """Even if persistence env is true, operator approval gate keeps fixture store."""
    app, _, settings = _app(
        exchange_binding_persistence_enabled=True,
        exchange_binding_persistence_operator_approved=False,
    )
    assert settings.exchange_binding_persistence_enabled is True
    client = TestClient(app)
    created = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert created["persistence"] == "fixture"
    assert created["is_live_exchange_connection"] is False


def test_durable_persistence_gates_fail_closed() -> None:
    try:
        assert_durable_persistence_allowed(PersistenceRuntimeGates())
        raise AssertionError("expected deny")
    except ValueError as exc:
        assert str(exc) == "binding_persistence_disabled"

    try:
        assert_durable_persistence_allowed(
            PersistenceRuntimeGates(
                persistence_flag_enabled=True,
                operator_approved=True,
                auth_e2e_passed=True,
                least_privilege_role_applied=False,
            )
        )
        raise AssertionError("expected deny")
    except ValueError as exc:
        assert str(exc) == "least_privilege_db_role_required"


def test_revoked_cannot_become_active_implicitly() -> None:
    try:
        assert_transition_allowed(BindingStatus.REVOKED, BindingStatus.ACTIVE)
        raise AssertionError("expected deny")
    except ValueError as exc:
        assert str(exc) == "illegal_binding_status_transition"


def test_transaction_rollback_discards_activation() -> None:
    store = InMemoryBindingStore()
    pending = request_pending_binding(
        store,
        owner_user_id=USER_A,
        spec=PendingBindingRequestSpec(environment=ExchangeEnvironment.TESTNET),
    )
    svc = BindingLifecycleService(store=store)
    svc.begin()
    svc.transition(
        owner_user_id=USER_A,
        binding_id=pending.id,
        target=BindingStatus.ERROR,
        detail="simulate_error",
    )
    svc.rollback()
    assert store.get(pending.id).status is BindingStatus.PENDING
    assert any(
        e.event is BindingLifecycleEvent.ROLLBACK for e in svc.audit_log()
    )


def test_concurrent_binding_requests_idempotent() -> None:
    app, _, _ = _app()
    client = TestClient(app)

    def _create() -> str:
        res = client.post(
            "/api/v1/exchange/bindings",
            headers={"Authorization": "Bearer token-a"},
            json={"environment": "testnet"},
        )
        assert res.status_code == 201
        return res.json()["id"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: _create(), range(16)))
    assert len(set(ids)) == 1


def test_pending_never_authorizes_wallet_and_private_kill_switch() -> None:
    app, store, settings = _app()
    client = TestClient(app)
    pending = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert settings.private_data_reads_enabled is False
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_A),
            store=store,
            settings=settings,
            requested_binding_id=uuid.UUID(pending["id"]),
        )
        raise AssertionError("expected deny")
    except HTTPException as exc:
        assert exc.detail == "ownership_schema_required"


def test_activation_fail_closed_despite_verified_credential() -> None:
    store = InMemoryBindingStore()
    pending = request_pending_binding(
        store,
        owner_user_id=USER_A,
        spec=PendingBindingRequestSpec(
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="pending:bybit-testnet",
        ),
    )
    # Align binding ref with a verified credential public_ref for mismatch-free path.
    cred = CredentialRecord(
        id=uuid.uuid4(),
        owner_user_id=USER_A,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
        public_ref="pending:bybit-testnet",
        secret_storage_ref="vault:mock",
        permission_class=CredentialPermissionClass.READ_ONLY,
        verification_state=CredentialVerificationState.VERIFIED,
        operator_managed=False,
    )
    svc = BindingLifecycleService(store=store)
    verification = VerificationOutcome(ok=True, reason=None)
    try:
        svc.activate_fail_closed(
            owner_user_id=USER_A,
            binding_id=pending.id,
            credential=cred,
            verification=verification,
            verification_gates=VerificationGates(
                operator_approved=True,
                auth_e2e_passed=True,
                binding_persistence_enabled=True,
                allow_external_bybit_calls=True,
            ),
            persistence_gates=PersistenceRuntimeGates(
                persistence_flag_enabled=True,
                operator_approved=True,
                auth_e2e_passed=True,
                least_privilege_role_applied=True,
            ),
        )
        raise AssertionError("expected activation deny")
    except ValueError as exc:
        assert "activation_requires_separate_operator_workflow" in str(exc)
    assert store.get(pending.id).status is BindingStatus.PENDING


def test_credential_ownership_mismatch_and_secret_redaction() -> None:
    cred = CredentialRecord(
        id=uuid.uuid4(),
        owner_user_id=USER_A,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
        public_ref="cred:abc",
        secret_storage_ref="vault:secret-path",
        permission_class=CredentialPermissionClass.READ_ONLY,
        verification_state=CredentialVerificationState.VERIFIED,
        operator_managed=False,
    )
    view = public_credential_view(cred)
    assert "secret_storage_ref" not in view
    assert "vault:secret-path" not in str(view)

    store = InMemoryBindingStore()
    pending = request_pending_binding(
        store,
        owner_user_id=USER_A,
        spec=PendingBindingRequestSpec(environment=ExchangeEnvironment.TESTNET),
    )
    svc = BindingLifecycleService(store=store)
    try:
        svc.activate_fail_closed(
            owner_user_id=USER_B,
            binding_id=pending.id,
            credential=cred,
            verification=VerificationOutcome(ok=True, reason=None),
            verification_gates=VerificationGates(),
            persistence_gates=PersistenceRuntimeGates(),
        )
        raise AssertionError("expected deny")
    except ValueError:
        pass


def test_rotation_propagates_and_demotes_active() -> None:
    store = InMemoryBindingStore()
    now_binding = ExchangeAccountBinding(
        id=uuid.uuid4(),
        owner_user_id=USER_A,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
        status=BindingStatus.ACTIVE,
        display_label="Active fixture",
        credential_ref="cred:old",
        telemetry_scope_id=str(uuid.uuid4()),
        enrollment_attestation="fixture",
        enrolled_by_operator=False,
    )
    store.upsert(now_binding)
    svc = BindingLifecycleService(store=store)
    rotated = svc.rotate_binding_credential_ref(
        owner_user_id=USER_A,
        binding_id=now_binding.id,
        new_public_ref="cred:new",
    )
    assert rotated.status is BindingStatus.PENDING
    assert rotated.credential_ref == "cred:new"
    assert any(
        e.event is BindingLifecycleEvent.CREDENTIAL_ROTATED for e in svc.audit_log()
    )


def test_revocation_and_recovery_after_restart_fixture() -> None:
    """Fixture store is process memory — restart empties it (documented non-durable)."""
    store = InMemoryBindingStore()
    pending = request_pending_binding(
        store,
        owner_user_id=USER_A,
        spec=PendingBindingRequestSpec(environment=ExchangeEnvironment.TESTNET),
    )
    revoke_owned_binding(store, owner_user_id=USER_A, binding_id=pending.id)
    assert store.get(pending.id).status is BindingStatus.REVOKED
    # Simulate service restart
    store2 = InMemoryBindingStore()
    assert store2.get(pending.id) is None


def test_connection_pool_identity_isolation() -> None:
    guard = ConnectionIdentityGuard()
    conn_id = "pool-1"
    guard.checkout(conn_id)
    guard.attach_verified_user(connection_id=conn_id, user_id=USER_A)
    guard.assert_no_cross_tenant_leak(conn_id, expected_user_id=USER_A)
    guard.release(conn_id)
    guard.assert_no_cross_tenant_leak(conn_id, expected_user_id=None)
    # Re-checkout must not retain USER_A
    guard.checkout(conn_id)
    guard.assert_no_cross_tenant_leak(conn_id, expected_user_id=None)
    guard.attach_verified_user(connection_id=conn_id, user_id=USER_B)
    try:
        guard.assert_no_cross_tenant_leak(conn_id, expected_user_id=USER_A)
        raise AssertionError("expected mismatch")
    except ValueError as exc:
        assert str(exc) == "tenant_identity_mismatch"


def test_mainnet_lock_and_operator_env_unclaimable() -> None:
    app, _, _ = _app()
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/exchange/bindings",
            headers={"Authorization": "Bearer token-a"},
            json={"environment": "mainnet"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/exchange/bindings",
            headers={"Authorization": "Bearer token-a"},
            json={
                "environment": "testnet",
                "credential_ref": "env:BYBIT_TESTNET_OPERATOR",
            },
        ).status_code
        == 403
    )


def test_root_flags_remain_fail_closed() -> None:
    app, _, _ = _app()
    root = TestClient(app).get("/").json()
    assert root["trading_endpoints"] is False
    assert root["private_catalog_reads_enabled"] is False
    assert root["exchange_binding_persistence_enabled"] is False
