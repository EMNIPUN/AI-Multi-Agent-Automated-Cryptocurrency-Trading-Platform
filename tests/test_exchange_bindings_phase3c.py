"""Phase 3C Part 1 — exchange account binding ownership (offline)."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from agent.telemetry_ledger import TelemetryLedger, make_event
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeEnvironment,
    ExchangeProvider,
    OperatorEnrollmentSpec,
    assert_telemetry_scope_access,
    enroll_operator_binding,
    require_active_binding_for_principal,
)
from apps.api.app.factory import create_app
from apps.api.app.migration_audit import (
    audit_exchange_binding_migration,
    audit_initial_migration,
    audit_ownership_migration,
)
from apps.api.app.observability.types import ObservabilityEventType
from fastapi import HTTPException


USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _settings(**kwargs) -> ApiSettings:
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
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _principal(user_id: uuid.UUID, *, role: str = "authenticated") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=str(user_id), role=role)


def _enroll(
    store: InMemoryBindingStore,
    owner: uuid.UUID,
    *,
    env: ExchangeEnvironment = ExchangeEnvironment.TESTNET,
    activate: bool = True,
    cred: str = "env:BYBIT_TESTNET_OPERATOR",
) -> object:
    return enroll_operator_binding(
        store,
        OperatorEnrollmentSpec(
            owner_user_id=owner,
            environment=env,
            credential_ref=cred,
            display_label="Operator testnet",
            attestation="Operator attested local enrollment ticket T-3C-1",
            activate=activate,
        ),
    )


def test_operator_enrollment_requires_attestation() -> None:
    store = InMemoryBindingStore()
    try:
        enroll_operator_binding(
            store,
            OperatorEnrollmentSpec(
                owner_user_id=USER_A,
                environment=ExchangeEnvironment.TESTNET,
                credential_ref="env:BYBIT_TESTNET_OPERATOR",
                display_label="x",
                attestation="   ",
            ),
        )
        raise AssertionError("expected attestation failure")
    except ValueError as exc:
        assert "attestation" in str(exc)


def test_does_not_auto_assign_to_other_users() -> None:
    store = InMemoryBindingStore()
    binding = _enroll(store, USER_A)
    assert store.find_active(
        owner_user_id=USER_B,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
    ) is None
    assert binding.owner_user_id == USER_A


def test_credential_ref_cannot_bind_two_active_owners() -> None:
    store = InMemoryBindingStore()
    _enroll(store, USER_A, cred="env:BYBIT_TESTNET_OPERATOR")
    try:
        _enroll(store, USER_B, cred="env:BYBIT_TESTNET_OPERATOR")
        raise AssertionError("expected conflict")
    except ValueError as exc:
        assert "already_bound" in str(exc)


def test_refuse_raw_looking_credential_ref() -> None:
    store = InMemoryBindingStore()
    try:
        enroll_operator_binding(
            store,
            OperatorEnrollmentSpec(
                owner_user_id=USER_A,
                environment=ExchangeEnvironment.TESTNET,
                credential_ref="api_key=abc",
                display_label="bad",
                attestation="note",
            ),
        )
        raise AssertionError("expected invalid credential_ref")
    except ValueError as exc:
        assert "opaque" in str(exc)


def test_missing_binding_and_private_reads_off() -> None:
    store = InMemoryBindingStore()
    settings = _settings(private_data_reads_enabled=False)
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_A),
            store=store,
            settings=settings,
            environment=ExchangeEnvironment.TESTNET,
        )
        raise AssertionError("expected deny")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "ownership_schema_required"


def test_wrong_user_denied_even_with_private_reads() -> None:
    store = InMemoryBindingStore()
    binding = _enroll(store, USER_A)
    settings = _settings(private_data_reads_enabled=True)
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_B),
            store=store,
            settings=settings,
            requested_binding_id=binding.id,
        )
        raise AssertionError("expected cross-tenant deny")
    except HTTPException as exc:
        assert exc.detail == "cross_tenant_forbidden"


def test_wrong_environment_denied() -> None:
    store = InMemoryBindingStore()
    binding = _enroll(store, USER_A, env=ExchangeEnvironment.TESTNET)
    settings = _settings(private_data_reads_enabled=True)
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_A),
            store=store,
            settings=settings,
            requested_binding_id=binding.id,
            environment=ExchangeEnvironment.MAINNET,
        )
        raise AssertionError("expected env mismatch")
    except HTTPException as exc:
        assert exc.detail == "exchange_environment_mismatch"


def test_pending_binding_not_readable() -> None:
    store = InMemoryBindingStore()
    binding = _enroll(store, USER_A, activate=False)
    assert binding.status is BindingStatus.PENDING
    settings = _settings(private_data_reads_enabled=True)
    try:
        require_active_binding_for_principal(
            principal=_principal(USER_A),
            store=store,
            settings=settings,
            requested_binding_id=binding.id,
        )
        raise AssertionError("expected inactive")
    except HTTPException as exc:
        assert exc.detail == "exchange_binding_inactive"


def test_telemetry_scope_must_match_binding() -> None:
    store = InMemoryBindingStore()
    binding = _enroll(store, USER_A)
    settings = _settings(private_data_reads_enabled=True)
    ok = assert_telemetry_scope_access(
        principal=_principal(USER_A),
        store=store,
        settings=settings,
        telemetry_scope_id=binding.telemetry_scope_id,
        environment=ExchangeEnvironment.TESTNET,
    )
    assert ok.id == binding.id
    try:
        assert_telemetry_scope_access(
            principal=_principal(USER_A),
            store=store,
            settings=settings,
            telemetry_scope_id=str(uuid.uuid4()),
            environment=ExchangeEnvironment.TESTNET,
        )
        raise AssertionError("expected scope deny")
    except HTTPException as exc:
        assert exc.detail == "telemetry_scope_forbidden"


def test_wallet_jwt_still_denied_without_binding() -> None:
    clear_settings_cache()
    app = create_app(_settings(private_data_reads_enabled=True))
    app.state.token_verifier = StaticMappingVerifier(
        {"good": _principal(USER_A)}
    )
    client = TestClient(app)
    resp = client.get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "exchange_binding_missing"


def test_wallet_jwt_with_binding_uses_credential_resolver_client() -> None:
    clear_settings_cache()
    app = create_app(_settings(private_data_reads_enabled=True))
    store: InMemoryBindingStore = app.state.exchange_binding_store
    binding = _enroll(store, USER_A, cred="env:BYBIT_TESTNET_OPERATOR")

    class _Fake:
        def get_wallet_balance(self, **kwargs):
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [
                        {
                            "totalEquity": "9.5",
                            "totalWalletBalance": "9.5",
                            "totalAvailableBalance": "9.5",
                            "totalPerpUPL": "0",
                            "coin": [
                                {
                                    "coin": "USDT",
                                    "walletBalance": "9.5",
                                    "availableToWithdraw": "9.5",
                                    "equity": "9.5",
                                    "unrealisedPnl": "0",
                                }
                            ],
                        }
                    ]
                },
            }

    app.state.token_verifier = StaticMappingVerifier({"good": _principal(USER_A)})
    app.state.bybit_wallet_clients = {binding.credential_ref: _Fake()}
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 200
    assert resp.json()["total_equity"] == "9.5"
    assert any("Owner-bound" in n for n in resp.json()["notes"])


def test_service_role_token_rejected() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    app.state.token_verifier = StaticMappingVerifier(
        {"svc": AuthenticatedPrincipal(user_id=str(USER_A), role="service_role")}
    )
    # StaticMappingVerifier returns principal as stored — get_current_principal
    # rejects non authenticated. Wallet optional bearer uses same check.
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer svc"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "non_user_token"


def test_forged_jwt_rejected() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    # No verifier override → HS256 with secret; garbage token fails.
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert resp.status_code in {401, 503}


def test_cross_user_worker_telemetry_denied(tmp_path: Path) -> None:
    ledger_path = tmp_path / "obs.sqlite"
    ledger = TelemetryLedger(ledger_path)
    scope_a = str(uuid.uuid4())
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.AGENT_HEARTBEAT,
            event_id="hb-a",
            message="a",
            account_scope_label=scope_a,
        )
    )
    clear_settings_cache()
    app = create_app(
        _settings(
            private_data_reads_enabled=True,
            observability_ledger_path=str(ledger_path),
        )
    )
    store: InMemoryBindingStore = app.state.exchange_binding_store
    binding_b = _enroll(store, USER_B, cred="env:BYBIT_DEMO_OPERATOR", env=ExchangeEnvironment.DEMO)
    # USER_B binding scope differs from event scope_a
    assert binding_b.telemetry_scope_id != scope_a
    app.state.token_verifier = StaticMappingVerifier({"b": _principal(USER_B)})
    resp = TestClient(app).get(
        "/api/v1/observability/worker-snapshot",
        headers={"Authorization": "Bearer b"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_mode"] == "unavailable"
    assert body["events"] == []


def test_operator_local_wallet_still_works_without_jwt() -> None:
    clear_settings_cache()
    app = create_app(_settings())

    class _Fake:
        def get_wallet_balance(self, **kwargs):
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [
                        {
                            "totalEquity": "1",
                            "totalWalletBalance": "1",
                            "totalAvailableBalance": "1",
                            "totalPerpUPL": "0",
                            "coin": [
                                {
                                    "coin": "USDT",
                                    "walletBalance": "1",
                                    "availableToWithdraw": "1",
                                    "equity": "1",
                                    "unrealisedPnl": "0",
                                }
                            ],
                        }
                    ]
                },
            }

    app.state.bybit_wallet_client = _Fake()
    resp = TestClient(app).get("/api/v1/exchange/wallet")
    assert resp.status_code == 200
    assert resp.json()["total_equity"] == "1"


def test_migration_audits_include_0003() -> None:
    assert audit_initial_migration().ok, audit_initial_migration().issues
    assert audit_ownership_migration().ok, audit_ownership_migration().issues
    binding = audit_exchange_binding_migration()
    assert binding.ok, binding.issues
    assert any("0003" in f for f in binding.revision_files)
    review = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "api"
        / "sql"
        / "review"
        / "20261105_0003_exchange_account_bindings.sql"
    )
    assert review.is_file()
    text = review.read_text(encoding="utf-8")
    assert "DO NOT auto-apply" in text
    assert "credential_ref" in text


def test_next_proxy_source_denies_by_default() -> None:
    """Static guard: browser proxies use JWT-forwarding helper; break-glass is gated."""
    root = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
    proxy = (root / "lib" / "security" / "authenticated-proxy.ts").read_text(
        encoding="utf-8"
    )
    wallet = (root / "app" / "api" / "exchange" / "wallet" / "route.ts").read_text(
        encoding="utf-8"
    )
    snap = (root / "app" / "api" / "observability" / "snapshot" / "route.ts").read_text(
        encoding="utf-8"
    )
    assert "operatorLocalBrowserProxyEnabled" in proxy
    assert "Authorization" in proxy
    assert "Bearer" in proxy
    assert "proxyJsonToFastApi" in wallet
    assert "allowOperatorBreakGlass" in wallet
    assert "proxyJsonToFastApi" in snap
    assert "operatorLocalBrowserProxyEnabled" in snap
    assert "owner-bound" in snap or "Authorization Bearer" in snap
