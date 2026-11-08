"""Phase 3C Part 6A — secure binding management API (offline / in-memory)."""

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
    OperatorEnrollmentSpec,
    enroll_operator_binding,
    require_active_binding_for_principal,
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


def _app_with_users():
    settings = _settings()
    app = create_app(settings)
    store = InMemoryBindingStore()
    app.state.exchange_binding_fixture_store = store
    app.state.exchange_binding_store = store
    app.state.token_verifier = StaticMappingVerifier(
        {
            "token-a": _principal(USER_A),
            "token-b": _principal(USER_B),
            "token-bad": AuthenticatedPrincipal(
                user_id="not-a-uuid", role="authenticated"
            ),
        }
    )
    return app, store, settings


def test_missing_jwt_rejected() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    assert client.get("/api/v1/exchange/bindings").status_code == 401
    assert (
        client.post(
            "/api/v1/exchange/bindings",
            json={"environment": "testnet"},
        ).status_code
        == 401
    )


def test_invalid_jwt_rejected() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    res = client.get(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer unknown-token"},
    )
    assert res.status_code == 401


def test_user_a_cannot_read_user_b_bindings() -> None:
    app, store, _ = _app_with_users()
    client = TestClient(app)
    create = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet", "display_label": "A pending"},
    )
    assert create.status_code == 201
    binding_id = create.json()["id"]

    # B lists only own (empty)
    listed = client.get(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-b"},
    )
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    # B cannot inspect A's binding (404 — no cross-tenant leak)
    inspect = client.get(
        f"/api/v1/exchange/bindings/{binding_id}",
        headers={"Authorization": "Bearer token-b"},
    )
    assert inspect.status_code == 404
    assert inspect.json()["detail"] == "exchange_binding_not_found"
    assert store.get(uuid.UUID(binding_id)) is not None


def test_user_a_cannot_revoke_user_b_binding() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    created = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-b"},
        json={"environment": "testnet"},
    )
    binding_id = created.json()["id"]
    revoke = client.post(
        f"/api/v1/exchange/bindings/{binding_id}/revoke",
        headers={"Authorization": "Bearer token-a"},
    )
    assert revoke.status_code == 404


def test_client_cannot_spoof_owner_user_id() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    res = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={
            "environment": "testnet",
            "owner_user_id": str(USER_B),
            "display_label": "spoof",
        },
    )
    # extra=forbid → 422
    assert res.status_code == 422


def test_credential_ref_validated() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    bad = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={
            "environment": "testnet",
            "credential_ref": "env:BYBIT_INJECT_${HOME}",
        },
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] in {
        "credential_ref_invalid",
        "credential_ref_not_allowlisted",
    }

    secretish = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={
            "environment": "testnet",
            "credential_ref": "raw-api-secret=abc",
        },
    )
    assert secretish.status_code == 400


def test_pending_and_revoked_cannot_read_private_wallet() -> None:
    app, store, settings = _app_with_users()
    client = TestClient(app)
    settings_on = _settings(private_data_reads_enabled=True)
    # Force kill-switch still off in app settings used by require_* — use store helpers.
    pending = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    ).json()
    assert pending["status"] == "pending"
    assert pending["is_live_exchange_connection"] is False

    principal = _principal(USER_A)
    # Kill switch still false on app → ownership_schema_required
    try:
        require_active_binding_for_principal(
            principal=principal,
            store=store,
            settings=settings,
            environment=ExchangeEnvironment.TESTNET,
            requested_binding_id=uuid.UUID(pending["id"]),
        )
        raise AssertionError("expected deny")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "ownership_schema_required"

    # Even with reads enabled, pending is inactive
    try:
        require_active_binding_for_principal(
            principal=principal,
            store=store,
            settings=settings_on,
            environment=ExchangeEnvironment.TESTNET,
            requested_binding_id=uuid.UUID(pending["id"]),
        )
        raise AssertionError("expected inactive")
    except HTTPException as exc:
        assert exc.detail == "exchange_binding_inactive"

    revoked = client.post(
        f"/api/v1/exchange/bindings/{pending['id']}/revoke",
        headers={"Authorization": "Bearer token-a"},
    ).json()
    assert revoked["status"] == "revoked"
    try:
        require_active_binding_for_principal(
            principal=principal,
            store=store,
            settings=settings_on,
            requested_binding_id=uuid.UUID(pending["id"]),
        )
        raise AssertionError("expected inactive")
    except HTTPException as exc:
        assert exc.detail == "exchange_binding_inactive"


def test_no_api_credentials_in_binding_response() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    res = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet"},
    )
    body = res.json()
    blob = str(body).lower()
    assert "api_key" not in blob
    assert "api_secret" not in blob
    assert "secret" not in blob or "credential_ref" in blob
    assert "credential_ref_alias" in body
    assert "credential_ref" not in body or "credential_ref_alias" in body
    # Raw field name credential_ref must not appear as a response key
    assert "credential_ref" not in body
    assert body["credential_ref_alias"].startswith("pending:")


def test_private_reads_and_live_trading_remain_disabled_flags() -> None:
    app, _, settings = _app_with_users()
    assert settings.private_data_reads_enabled is False
    assert settings.exchange_binding_persistence_enabled is False
    client = TestClient(app)
    listed = client.get(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
    ).json()
    assert listed["private_data_reads_enabled"] is False
    assert listed["binding_persistence_enabled"] is False
    assert listed["mainnet_activation_locked"] is True
    assert listed["auth_e2e_verified"] is False


def test_mainnet_locked_and_duplicate_pending_idempotent() -> None:
    app, _, _ = _app_with_users()
    client = TestClient(app)
    mainnet = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "mainnet"},
    )
    assert mainnet.status_code == 403
    assert mainnet.json()["detail"] == "mainnet_binding_locked"

    first = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet", "display_label": "First"},
    )
    second = client.post(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
        json={"environment": "testnet", "display_label": "Second"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_active_fixture_still_not_live_connection_flag() -> None:
    """Operator-enrolled ACTIVE in fixture store is not advertised as live."""
    app, store, _ = _app_with_users()
    enroll_operator_binding(
        store,
        OperatorEnrollmentSpec(
            owner_user_id=USER_A,
            environment=ExchangeEnvironment.TESTNET,
            credential_ref="env:BYBIT_TESTNET_OPERATOR",
            display_label="Fixture active",
            attestation="Part6A offline fixture only",
            activate=True,
        ),
    )
    client = TestClient(app)
    listed = client.get(
        "/api/v1/exchange/bindings",
        headers={"Authorization": "Bearer token-a"},
    ).json()
    assert len(listed["items"]) == 1
    item = listed["items"][0]
    assert item["status"] == BindingStatus.ACTIVE.value
    assert item["is_live_exchange_connection"] is False
    assert item["persistence"] == "fixture"
