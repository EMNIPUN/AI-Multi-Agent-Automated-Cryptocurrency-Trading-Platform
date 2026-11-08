"""Phase 3C Part 2 — Postgres binding store, credential resolver, auth isolation."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from agent.telemetry_ledger import TelemetryLedger, make_event
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_store import (
    InMemoryBindingStore,
    SqlAlchemyBindingStore,
)
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeEnvironment,
    OperatorEnrollmentSpec,
    enroll_operator_binding,
)
from apps.api.app.exchange.credentials import resolve_credential_ref
from apps.api.app.factory import create_app
from apps.api.app.models import Base
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
        private_data_reads_enabled=True,
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


def _principal(user_id: uuid.UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=str(user_id), role="authenticated")


@pytest.fixture
def sqlite_binding_store(tmp_path: Path) -> Generator[SqlAlchemyBindingStore, None, None]:
    main = tmp_path / "main.sqlite"
    app_db = tmp_path / "app.sqlite"
    engine = create_engine(f"sqlite:///{main.as_posix()}", future=True)
    with engine.begin() as conn:
        conn.execute(text(f"ATTACH DATABASE '{app_db.as_posix()}' AS app"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    store = SqlAlchemyBindingStore.from_sessionmaker(factory)
    try:
        yield store
    finally:
        engine.dispose()


def test_sqlalchemy_store_persists_enrollment(sqlite_binding_store: SqlAlchemyBindingStore) -> None:
    binding = enroll_operator_binding(
        sqlite_binding_store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="A testnet",
            attestation="Part2 enrollment ticket",
            activate=True,
        ),
    )
    loaded = sqlite_binding_store.get(binding.id)
    assert loaded is not None
    assert loaded.owner_user_id == USER_A
    assert loaded.telemetry_scope_id == str(binding.id)
    assert loaded.status is BindingStatus.ACTIVE


def test_credential_resolver_environment_mismatch() -> None:
    try:
        resolve_credential_ref(
            "env:BYBIT_TESTNET_OPERATOR",
            expected_environment=ExchangeEnvironment.MAINNET,
            environ={
                "BYBIT_TESTNET_API_KEY": "k",
                "BYBIT_TESTNET_API_SECRET": "s",
            },
        )
        raise AssertionError("expected mismatch")
    except HTTPException as exc:
        assert exc.detail == "credential_environment_mismatch"


def test_credential_resolver_missing_material() -> None:
    try:
        resolve_credential_ref(
            "env:BYBIT_TESTNET_OPERATOR",
            expected_environment=ExchangeEnvironment.TESTNET,
            environ={},
        )
        raise AssertionError("expected unavailable")
    except HTTPException as exc:
        assert exc.detail == "credential_material_unavailable"


def test_revoked_binding_denied(sqlite_binding_store: SqlAlchemyBindingStore) -> None:
    from dataclasses import replace

    binding = enroll_operator_binding(
        sqlite_binding_store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="A",
            attestation="t",
            activate=True,
        ),
    )
    sqlite_binding_store.upsert(replace(binding, status=BindingStatus.REVOKED))

    clear_settings_cache()
    app = create_app(_settings())
    app.state.exchange_binding_store = sqlite_binding_store
    app.state.token_verifier = StaticMappingVerifier({"good": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "exchange_binding_inactive"


def test_wrong_owner_cannot_use_binding_id(sqlite_binding_store: SqlAlchemyBindingStore) -> None:
    binding = enroll_operator_binding(
        sqlite_binding_store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="A",
            attestation="t",
            activate=True,
        ),
    )
    clear_settings_cache()
    app = create_app(_settings())
    app.state.exchange_binding_store = sqlite_binding_store
    app.state.token_verifier = StaticMappingVerifier({"b": _principal(USER_B)})
    # Even if B somehow knows A's binding id, ownership check fails.
    from apps.api.app.exchange.bindings import require_active_binding_for_principal

    try:
        require_active_binding_for_principal(
            principal=_principal(USER_B),
            store=sqlite_binding_store,
            settings=_settings(),
            requested_binding_id=binding.id,
        )
        raise AssertionError("expected deny")
    except HTTPException as exc:
        assert exc.detail == "cross_tenant_forbidden"


def test_worker_snapshot_scopes_events(tmp_path: Path) -> None:
    ledger_path = tmp_path / "obs.sqlite"
    ledger = TelemetryLedger(ledger_path)
    store = InMemoryBindingStore()
    binding = enroll_operator_binding(
        store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="A",
            attestation="t",
            activate=True,
        ),
    )
    scope = binding.telemetry_scope_id
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.AGENT_HEARTBEAT,
            event_id="mine",
            message="mine",
            account_scope_label=scope,
        )
    )
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.AGENT_HEARTBEAT,
            event_id="other",
            message="other",
            account_scope_label=str(uuid.uuid4()),
        )
    )
    clear_settings_cache()
    app = create_app(_settings(observability_ledger_path=str(ledger_path)))
    app.state.exchange_binding_store = store
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/observability/worker-snapshot",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_mode"] == "live"
    assert len(body["events"]) == 1
    assert body["events"][0]["event_id"] == "mine"
    assert body["orders"] == []


def test_private_reads_flag_still_fail_closed_by_default() -> None:
    clear_settings_cache()
    app = create_app(_settings(private_data_reads_enabled=False))
    store: InMemoryBindingStore = app.state.exchange_binding_store
    enroll_operator_binding(
        store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="A",
            attestation="t",
            activate=True,
        ),
    )
    app.state.token_verifier = StaticMappingVerifier({"a": _principal(USER_A)})
    resp = TestClient(app).get(
        "/api/v1/exchange/wallet",
        headers={"Authorization": "Bearer a"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ownership_schema_required"


def test_next_proxy_forwards_authorization_header() -> None:
    root = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
    proxy = (root / "lib" / "security" / "authenticated-proxy.ts").read_text(encoding="utf-8")
    wallet = (root / "app" / "api" / "exchange" / "wallet" / "route.ts").read_text(
        encoding="utf-8"
    )
    snap = (root / "app" / "api" / "observability" / "snapshot" / "route.ts").read_text(
        encoding="utf-8"
    )
    assert "Authorization" in proxy
    assert "allowOperatorBreakGlass" in proxy
    assert "proxyJsonToFastApi" in wallet
    assert "bearerFromRequest" in snap
    assert "authentication_required" in proxy
