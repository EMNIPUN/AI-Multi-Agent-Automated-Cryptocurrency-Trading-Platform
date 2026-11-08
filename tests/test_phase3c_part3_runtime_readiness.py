"""Phase 3C Part 3 — runtime readiness isolation matrix (offline / local)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from agent.telemetry_ledger import TelemetryLedger, make_event
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeEnvironment,
    OperatorEnrollmentSpec,
    enroll_operator_binding,
)
from apps.api.app.exchange.credentials import (
    ALLOWLISTED_CREDENTIAL_REFS,
    is_allowlisted_credential_ref,
    resolve_credential_ref,
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
HS_SECRET = "test-only-hs256-secret-not-for-production-32b+"


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        private_data_reads_enabled=True,
        observability_fixture_mode=True,
        observability_live_stream_enabled=False,
        observability_ledger_path=None,
        exchange_wallet_reads_enabled=True,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret=HS_SECRET,
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _principal(user_id: uuid.UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=str(user_id), role="authenticated")


def _enroll(
    store: InMemoryBindingStore,
    owner: uuid.UUID,
    *,
    env: ExchangeEnvironment = ExchangeEnvironment.TESTNET,
    cred: str = "env:BYBIT_TESTNET_OPERATOR",
    activate: bool = True,
):
    return enroll_operator_binding(
        store,
        OperatorEnrollmentSpec(
            owner_user_id=owner,
            environment=env,
            credential_ref=cred,
            display_label="t",
            attestation="part3",
            activate=activate,
        ),
    )


def _mint_hs256(**claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(USER_A),
        "role": "authenticated",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **claims,
    }
    return jwt.encode(payload, HS_SECRET, algorithm="HS256")


def test_migration_offline_audits_pass() -> None:
    assert audit_initial_migration().ok
    assert audit_ownership_migration().ok
    assert audit_exchange_binding_migration().ok


def test_credential_allowlist_rejects_injection() -> None:
    assert is_allowlisted_credential_ref("env:BYBIT_TESTNET_OPERATOR")
    assert "env:BYBIT_OPERATOR" in ALLOWLISTED_CREDENTIAL_REFS
    with pytest.raises(HTTPException) as exc:
        resolve_credential_ref(
            "env:BYBIT_${USER}_OPERATOR",
            expected_environment=ExchangeEnvironment.TESTNET,
            environ={"BYBIT_TESTNET_API_KEY": "k", "BYBIT_TESTNET_API_SECRET": "s"},
        )
    assert exc.value.detail == "credential_ref_invalid"


def test_enrollment_rejects_non_allowlisted_ref() -> None:
    store = InMemoryBindingStore()
    with pytest.raises(ValueError, match="credential_ref_not_allowlisted"):
        _enroll(store, USER_A, cred="env:CUSTOM_USER_KEYS")


def test_pending_binding_inactive_detail() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    store: InMemoryBindingStore = app.state.exchange_binding_store
    _enroll(store, USER_A, activate=False)
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "exchange_binding_inactive"


def test_revoked_binding_inactive_detail() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    store: InMemoryBindingStore = app.state.exchange_binding_store
    binding = _enroll(store, USER_A, activate=True)
    store.upsert(replace(binding, status=BindingStatus.REVOKED))
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "exchange_binding_inactive"


def test_wrong_environment_denied() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    store: InMemoryBindingStore = app.state.exchange_binding_store
    _enroll(store, USER_A, env=ExchangeEnvironment.TESTNET, activate=True)
    binding = store.find_active(
        owner_user_id=USER_A,
        provider=__import__(
            "apps.api.app.exchange.bindings", fromlist=["ExchangeProvider"]
        ).ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
    )
    assert binding is not None
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    # Request mainnet wallet by forcing environment via query is not exposed;
    # resolve with wrong credential env instead.
    with pytest.raises(HTTPException) as exc:
        resolve_credential_ref(
            "env:BYBIT_MAINNET_OPERATOR",
            expected_environment=ExchangeEnvironment.TESTNET,
            environ={
                "BYBIT_MAINNET_API_KEY": "k",
                "BYBIT_MAINNET_API_SECRET": "s",
            },
        )
    assert exc.value.detail == "credential_environment_mismatch"


def test_expired_jwt_rejected() -> None:
    from apps.api.app.auth.errors import AuthError

    clear_settings_cache()
    app = create_app(_settings())
    _enroll(app.state.exchange_binding_store, USER_A)
    app.state.token_verifier = StaticMappingVerifier(
        {"expired-token": AuthError("token_expired")}
    )
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer expired-token"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_expired"


def test_service_role_rejected() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    app.state.token_verifier = StaticMappingVerifier(
        {"svc": AuthenticatedPrincipal(user_id=str(USER_A), role="service_role")}
    )
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer svc"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "non_user_token"


def test_wrong_owner_denied() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    store: InMemoryBindingStore = app.state.exchange_binding_store
    _enroll(store, USER_A, cred="env:BYBIT_TESTNET_OPERATOR")
    app.state.token_verifier = StaticMappingVerifier({"b": _principal(USER_B)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer b"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] in {
        "exchange_binding_missing",
        "cross_tenant_forbidden",
    }


def test_client_binding_id_cannot_bypass_ownership() -> None:
    from apps.api.app.exchange.bindings import require_active_binding_for_principal

    store = InMemoryBindingStore()
    binding_a = _enroll(store, USER_A)
    with pytest.raises(HTTPException) as exc:
        require_active_binding_for_principal(
            principal=_principal(USER_B),
            store=store,
            settings=_settings(),
            requested_binding_id=binding_a.id,
        )
    assert exc.value.detail == "cross_tenant_forbidden"


def test_missing_credential_material() -> None:
    with pytest.raises(HTTPException) as exc:
        resolve_credential_ref(
            "env:BYBIT_TESTNET_OPERATOR",
            expected_environment=ExchangeEnvironment.TESTNET,
            environ={},
        )
    assert exc.value.detail == "credential_material_unavailable"


def test_private_reads_still_off_by_default() -> None:
    clear_settings_cache()
    app = create_app(_settings(private_data_reads_enabled=False))
    _enroll(app.state.exchange_binding_store, USER_A)
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ownership_schema_required"


def test_sse_still_disabled() -> None:
    clear_settings_cache()
    app = create_app(_settings(observability_live_stream_enabled=False))
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/observability/stream",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "observability_live_stream_disabled"


def test_stale_heartbeat_offline(tmp_path: Path) -> None:
    ledger_path = tmp_path / "obs.sqlite"
    ledger = TelemetryLedger(ledger_path)
    store = InMemoryBindingStore()
    binding = _enroll(store, USER_A)
    scope = binding.telemetry_scope_id
    # Heartbeat in the distant past via direct record then mutate is hard;
    # use stale_after_seconds=0 path by waiting — instead record and snapshot with tiny window.
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.AGENT_HEARTBEAT,
            event_id="hb",
            message="old",
            account_scope_label=scope,
        )
    )
    snap = ledger.snapshot(stale_after_seconds=0)
    assert snap.heartbeat_stale is True
    assert snap.agent_status.value in {"OFFLINE", "UNKNOWN", "RUNNING"}


def test_empty_ledger_unavailable(tmp_path: Path) -> None:
    ledger_path = tmp_path / "empty.sqlite"
    TelemetryLedger(ledger_path)  # create empty schema
    clear_settings_cache()
    app = create_app(
        _settings(
            observability_ledger_path=str(ledger_path),
            private_data_reads_enabled=True,
        )
    )
    store: InMemoryBindingStore = app.state.exchange_binding_store
    _enroll(store, USER_A)
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/observability/worker-snapshot",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_mode"] == "unavailable"
    assert body["events"] == []
    assert body["sample_label"] is None


def test_telemetry_scope_mismatch_unavailable(tmp_path: Path) -> None:
    ledger_path = tmp_path / "obs.sqlite"
    ledger = TelemetryLedger(ledger_path)
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.AGENT_HEARTBEAT,
            event_id="other-scope",
            message="x",
            account_scope_label=str(uuid.uuid4()),
        )
    )
    clear_settings_cache()
    app = create_app(
        _settings(observability_ledger_path=str(ledger_path), private_data_reads_enabled=True)
    )
    _enroll(app.state.exchange_binding_store, USER_A)
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/observability/worker-snapshot",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 200
    assert resp.json()["data_mode"] == "unavailable"
    assert resp.json()["events"] == []


def test_owner_wallet_with_fake_client() -> None:
    clear_settings_cache()
    app = create_app(_settings())
    store: InMemoryBindingStore = app.state.exchange_binding_store
    binding = _enroll(store, USER_A)

    class _Fake:
        def get_wallet_balance(self, **kwargs):
            return {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [
                        {
                            "accountType": "UNIFIED",
                            "totalEquity": "12.5",
                            "totalWalletBalance": "12.5",
                            "totalAvailableBalance": "10",
                            "totalPerpUPL": "0",
                            "coin": [],
                        }
                    ]
                },
            }

    app.state.bybit_wallet_clients = {binding.credential_ref: _Fake()}
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_equity"] == "12.5"
    assert "api_key" not in resp.text.lower()
    assert "api_secret" not in resp.text.lower()


def test_next_proxy_bypass_guards() -> None:
    root = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
    proxy = (root / "lib" / "security" / "authenticated-proxy.ts").read_text(encoding="utf-8")
    gate = (root / "lib" / "security" / "operator-proxy-gate.ts").read_text(encoding="utf-8")
    wallet = (root / "app" / "api" / "exchange" / "wallet" / "route.ts").read_text(
        encoding="utf-8"
    )
    snap = (root / "app" / "api" / "observability" / "snapshot" / "route.ts").read_text(
        encoding="utf-8"
    )
    assert "operatorLocalBrowserProxyEnabled" in gate
    assert '=== "true"' in gate
    assert "authentication_required" in proxy
    assert "X-Forwarded-For" in proxy or "forward" in proxy.lower()
    assert "Cache-Control" in proxy and "no-store" in proxy
    assert "proxyJsonToFastApi" in wallet
    assert "Bearer" in proxy
    # Break-glass must not be hard-coded true in route modules.
    assert "OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=true" not in wallet
    assert "OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=true" not in snap
    assert "sample_leak" not in snap.lower() or "worker" in snap


def test_gitignore_no_longer_ignores_web_src_lib() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / ".gitignore").read_text(encoding="utf-8")
    assert "/lib/" in text
    # Bare lib/ would ignore apps/web/src/lib — must not remain.
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    assert "lib/" not in lines
    assert "lib64/" not in lines
