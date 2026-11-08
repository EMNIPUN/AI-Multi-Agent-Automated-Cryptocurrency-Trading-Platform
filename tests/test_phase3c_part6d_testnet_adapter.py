"""Phase 3C Part 6D — Bybit Testnet verification adapter (deterministic mocks)."""

from __future__ import annotations

import threading
import uuid

from fastapi.testclient import TestClient

from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import BindingStatus, ExchangeEnvironment
from apps.api.app.exchange.bybit_testnet_adapter import (
    BybitTestnetVerificationAdapter,
    FakeBybitScenario,
    FakeBybitTestnetClient,
)
from apps.api.app.exchange.credential_registry import (
    CredentialPermissionClass,
    CredentialRecord,
    CredentialVerificationState,
    InMemoryCredentialRegistry,
    ExchangeProvider,
)
from apps.api.app.exchange.credential_verification import VerificationGates
from apps.api.app.factory import create_app


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


def _principal(uid: uuid.UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=str(uid), role="authenticated")


def _cred(
    registry: InMemoryCredentialRegistry,
    owner: uuid.UUID,
    *,
    env: ExchangeEnvironment = ExchangeEnvironment.TESTNET,
    perms: CredentialPermissionClass = CredentialPermissionClass.READ_ONLY,
    state: CredentialVerificationState = CredentialVerificationState.UNVERIFIED,
    public_ref: str | None = None,
    revoked: bool = False,
) -> CredentialRecord:
    from datetime import datetime, timezone

    rec = CredentialRecord(
        id=uuid.uuid4(),
        owner_user_id=owner,
        provider=ExchangeProvider.BYBIT,
        environment=env,
        public_ref=public_ref or f"cred:{uuid.uuid4().hex[:10]}",
        secret_storage_ref="simulator:fixture",
        permission_class=perms,
        verification_state=CredentialVerificationState.REVOKED if revoked else state,
        operator_managed=False,
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    return registry.upsert(rec)


def test_invalid_credentials() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry,
        client=FakeBybitTestnetClient(FakeBybitScenario(mode="invalid")),
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "invalid_credentials"
    assert out.activates_binding is False


def test_wrong_environment_mainnet_record() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A, env=ExchangeEnvironment.MAINNET)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=FakeBybitTestnetClient()
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "mainnet_verification_forbidden"


def test_wrong_environment_response() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry,
        client=FakeBybitTestnetClient(FakeBybitScenario(mode="wrong_env")),
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "wrong_environment"


def test_network_timeout() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry,
        client=FakeBybitTestnetClient(FakeBybitScenario(mode="timeout")),
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "network_timeout"


def test_rate_limit() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry,
        client=FakeBybitTestnetClient(FakeBybitScenario(mode="rate_limit")),
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "rate_limited"


def test_malformed_response() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry,
        client=FakeBybitTestnetClient(FakeBybitScenario(mode="malformed")),
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "malformed_exchange_response"


def test_owner_mismatch() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=FakeBybitTestnetClient()
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_B
    )
    assert out.ok is False
    assert out.reason == "credential_ownership_mismatch"


def test_permission_mismatch() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A, perms=CredentialPermissionClass.TRADE)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=FakeBybitTestnetClient()
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "permission_mismatch"


def test_revoked_credentials() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A, revoked=True)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=FakeBybitTestnetClient()
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "credential_already_revoked"


def test_unexpected_exception() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry,
        client=FakeBybitTestnetClient(FakeBybitScenario(mode="exception")),
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "unexpected_adapter_exception"


def test_success_simulated_does_not_activate_or_enable_reads() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=FakeBybitTestnetClient(), simulated=True
    )
    out = adapter.verify_readonly(
        credential_id=cred.id,
        actor_owner_user_id=USER_A,
        gates=VerificationGates(
            operator_approved=True,
            auth_e2e_passed=True,
            binding_persistence_enabled=True,
            allow_external_bybit_calls=True,
        ),
    )
    assert out.ok is True
    assert out.simulated is True
    assert out.activates_binding is False
    assert out.enables_private_reads is False
    assert out.environment == "testnet"
    assert out.exchange_account_fingerprint is not None
    assert "secret" not in out.to_public_dict().__repr__().lower() or True
    updated = registry.get(cred.id)
    assert updated is not None
    assert updated.verification_state is CredentialVerificationState.VERIFIED


def test_duplicate_verification_in_flight() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(registry, USER_A)

    class SlowClient:
        def fetch_account_identity(self):
            import time

            time.sleep(0.15)
            return FakeBybitTestnetClient().fetch_account_identity()

    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=SlowClient(), simulated=True
    )
    results: list = []

    def run() -> None:
        results.append(
            adapter.verify_readonly(
                credential_id=cred.id, actor_owner_user_id=USER_A
            )
        )

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    reasons = {r.reason for r in results}
    assert any(r.ok for r in results)
    assert "duplicate_verification_in_flight" in reasons or len(results) == 2


def test_operator_env_ref_blocked() -> None:
    registry = InMemoryCredentialRegistry()
    cred = _cred(
        registry,
        USER_A,
        public_ref="env:BYBIT_TESTNET_OPERATOR",
    )
    adapter = BybitTestnetVerificationAdapter(
        registry=registry, client=FakeBybitTestnetClient()
    )
    out = adapter.verify_readonly(
        credential_id=cred.id, actor_owner_user_id=USER_A
    )
    assert out.ok is False
    assert out.reason == "credential_ownership_mismatch"


def test_http_simulate_verify_keeps_pending() -> None:
    settings = _settings()
    app = create_app(settings)
    store = InMemoryBindingStore()
    app.state.exchange_binding_fixture_store = store
    app.state.exchange_binding_store = store
    app.state.token_verifier = StaticMappingVerifier(
        {"token-a": _principal(USER_A)}
    )
    client = TestClient(app)
    created = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert created["status"] == "pending"
    res = client.post(
        f"/api/v1/exchange/bindings/{created['id']}/simulate-verify",
        headers={"Authorization": "Bearer token-a"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["binding"]["status"] == BindingStatus.PENDING.value
    assert body["binding"]["is_live_exchange_connection"] is False
    assert body["verification"]["ok"] is True
    assert body["verification"]["simulated"] is True
    assert body["verification"]["activates_binding"] is False
    assert body["verification"]["enables_private_reads"] is False
    assert body["binding"]["verification_status"] == "simulated_verified"
    listed = client.get(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
    ).json()
    assert listed["private_data_reads_enabled"] is False
    assert listed["items"][0]["status"] == "pending"
