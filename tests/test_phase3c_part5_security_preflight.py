"""Phase 3C Part 5 — offline security regression (no live DB writes)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from apps.api.app.auth.errors import AuthError
from apps.api.app.auth.jwt_verifier import (
    StaticMappingVerifier,
    SupabaseHS256Verifier,
    principal_from_payload,
)
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.binding_store import InMemoryBindingStore
from apps.api.app.exchange.bindings import (
    BindingStatus,
    ExchangeAccountBinding,
    ExchangeEnvironment,
    ExchangeProvider,
    enroll_operator_binding,
    require_active_binding_for_principal,
)
from apps.api.app.exchange.credentials import is_allowlisted_credential_ref
from apps.api.app.factory import create_app
from apps.api.app.migration_audit import (
    audit_exchange_binding_migration,
    audit_ownership_migration,
)
from apps.api.app.ownership import assert_owner_matches, assert_same_user
from scripts.verify_dev_database_target import (
    DEFAULT_APPROVED_DEV_PROJECT_REFS,
    DevTargetError,
    verify_dev_database_target,
)

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "https://wmirifmgaftassgrfbyl.supabase.co/auth/v1"
AUDIENCE = "authenticated"
SECRET = "phase5-test-only-hs256-secret-not-real-32chars"


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        supabase_url="https://wmirifmgaftassgrfbyl.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret=SECRET,
        supabase_jwt_audience=AUDIENCE,
        supabase_jwt_issuer=ISSUER,
        private_data_reads_enabled=False,
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _hs256(**claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "authenticated",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "nbf": now - timedelta(seconds=5),
        "exp": now + timedelta(minutes=5),
    }
    payload.update(claims)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_approved_dev_ref_allowlist_contains_operator_project() -> None:
    assert "wmirifmgaftassgrfbyl" in DEFAULT_APPROVED_DEV_PROJECT_REFS


def test_dev_identity_guard_rejects_production_classification() -> None:
    with pytest.raises(DevTargetError):
        verify_dev_database_target(
            {
                "CRYPTONOVA_DB_TARGET": "production",
                "CRYPTONOVA_DEV_PROJECT_REF": "wmirifmgaftassgrfbyl",
                "CRYPTONOVA_USE_DATABASE_URL_AS_DEV": "true",
                "DATABASE_URL": (
                    "postgresql://postgres.wmirifmgaftassgrfbyl:x@"
                    "aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
                    "?sslmode=require"
                ),
            }
        )


def test_ownership_and_binding_migration_audits_pass() -> None:
    ownership = audit_ownership_migration()
    assert ownership.ok, ownership.issues
    binding = audit_exchange_binding_migration()
    assert binding.ok, binding.issues


def test_rls_policies_use_auth_uid_and_authenticated_role() -> None:
    m0002 = (
        ROOT
        / "apps/api/alembic/versions/20261104_0002_ownership_rls.py"
    ).read_text(encoding="utf-8")
    m0003 = (
        ROOT
        / "apps/api/alembic/versions/20261105_0003_exchange_account_bindings.py"
    ).read_text(encoding="utf-8")
    for src in (m0002, m0003):
        assert "ENABLE ROW LEVEL SECURITY" in src
        assert "TO authenticated" in src
        assert "auth.uid()" in src
        assert "FORCE ROW LEVEL SECURITY" not in src
        assert "GRANT USAGE ON SCHEMA app" not in src
    assert "status = 'active'" in m0003


def test_models_store_credential_ref_not_raw_secrets() -> None:
    models = (ROOT / "apps/api/app/models.py").read_text(encoding="utf-8")
    assert "credential_ref" in models
    assert re.search(r"class ExchangeAccountBindingRow", models)
    block = models.split("class ExchangeAccountBindingRow", 1)[1].split("\n\n\n", 1)[0]
    forbidden = ("bybit_api_secret", "api_secret", "raw_secret", "private_key", "api_key")
    for token in forbidden:
        assert token not in block.lower()


def test_jwt_rejects_service_role_and_anon() -> None:
    for role in ("service_role", "anon"):
        with pytest.raises(AuthError) as exc:
            principal_from_payload(
                {
                    "sub": str(uuid.uuid4()),
                    "role": role,
                    "aud": AUDIENCE,
                    "iss": ISSUER,
                }
            )
        assert exc.value.code == "non_user_token"


def test_jwt_rejects_wrong_issuer_and_expired() -> None:
    verifier = SupabaseHS256Verifier(
        secret=SECRET, issuer=ISSUER, audience=AUDIENCE
    )
    wrong_iss = _hs256(iss="https://other-project.supabase.co/auth/v1")
    with pytest.raises(AuthError) as exc:
        verifier.verify_access_token(wrong_iss)
    assert exc.value.code == "invalid_issuer"

    expired = _hs256(exp=datetime.now(timezone.utc) - timedelta(minutes=10))
    with pytest.raises(AuthError) as exc2:
        verifier.verify_access_token(expired)
    assert exc2.value.code == "token_expired"

    bad_sig = _hs256()
    tampered = bad_sig[:-4] + ("AAAA" if not bad_sig.endswith("AAAA") else "BBBB")
    with pytest.raises(AuthError):
        verifier.verify_access_token(tampered)


def test_jwt_rejects_missing_sub() -> None:
    with pytest.raises(AuthError) as exc:
        principal_from_payload({"role": "authenticated", "aud": AUDIENCE})
    assert "missing_claim_sub" in exc.value.code


def test_fastapi_missing_authorization_and_service_role() -> None:
    clear_settings_cache()
    # StaticMappingVerifier avoids global settings-cache coupling in deps verifier factory.
    app = create_app(_settings())
    app.state.token_verifier = StaticMappingVerifier(
        {"svc": AuthError("non_user_token")}
    )
    client = TestClient(app)
    assert client.get("/api/v1/me").status_code == 401
    resp = client.get("/api/v1/me", headers={"Authorization": "Bearer svc"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "non_user_token"


def test_application_ownership_isolation_helpers() -> None:
    a = AuthenticatedPrincipal(user_id=str(uuid.uuid4()), role="authenticated")
    b = str(uuid.uuid4())
    with pytest.raises(Exception) as exc:
        assert_same_user(a, b)
    assert getattr(exc.value, "status_code", None) == 403
    with pytest.raises(Exception) as exc2:
        assert_owner_matches(a, None)
    assert getattr(exc2.value, "status_code", None) == 403


def test_binding_cross_user_pending_revoked_forged_and_scope() -> None:
    store = InMemoryBindingStore()
    owner_a = uuid.uuid4()
    owner_b = uuid.uuid4()
    binding_a = ExchangeAccountBinding(
        id=uuid.uuid4(),
        owner_user_id=owner_a,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
        status=BindingStatus.ACTIVE,
        display_label="A",
        credential_ref="env:BYBIT_TESTNET_OPERATOR",
        telemetry_scope_id=str(uuid.uuid4()),
        enrollment_attestation="phase5-test",
    )
    binding_b = ExchangeAccountBinding(
        id=uuid.uuid4(),
        owner_user_id=owner_b,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.TESTNET,
        status=BindingStatus.ACTIVE,
        display_label="B",
        credential_ref="env:BYBIT_OPERATOR",
        telemetry_scope_id=str(uuid.uuid4()),
        enrollment_attestation="phase5-test",
    )
    pending = ExchangeAccountBinding(
        id=uuid.uuid4(),
        owner_user_id=owner_a,
        provider=ExchangeProvider.BYBIT,
        environment=ExchangeEnvironment.DEMO,
        status=BindingStatus.PENDING,
        display_label="pending",
        credential_ref="env:BYBIT_DEMO_OPERATOR",
        telemetry_scope_id=str(uuid.uuid4()),
        enrollment_attestation="phase5-test",
    )
    store.upsert(binding_a)
    store.upsert(binding_b)
    store.upsert(pending)
    settings = _settings(private_data_reads_enabled=True)
    principal_a = AuthenticatedPrincipal(user_id=str(owner_a), role="authenticated")

    ok = require_active_binding_for_principal(
        principal=principal_a, store=store, settings=settings, environment=ExchangeEnvironment.TESTNET
    )
    assert ok.id == binding_a.id

    with pytest.raises(Exception) as cross:
        require_active_binding_for_principal(
            principal=principal_a,
            store=store,
            settings=settings,
            requested_binding_id=binding_b.id,
        )
    assert getattr(cross.value, "detail", None) == "cross_tenant_forbidden"

    with pytest.raises(Exception) as forged:
        require_active_binding_for_principal(
            principal=principal_a,
            store=store,
            settings=settings,
            requested_binding_id=uuid.uuid4(),
        )
    assert getattr(forged.value, "detail", None) == "exchange_binding_not_found"

    with pytest.raises(Exception) as inactive:
        require_active_binding_for_principal(
            principal=principal_a,
            store=store,
            settings=settings,
            requested_binding_id=pending.id,
        )
    assert getattr(inactive.value, "detail", None) == "exchange_binding_inactive"

    with pytest.raises(Exception) as env_mismatch:
        require_active_binding_for_principal(
            principal=principal_a,
            store=store,
            settings=settings,
            requested_binding_id=binding_a.id,
            environment=ExchangeEnvironment.MAINNET,
        )
    assert getattr(env_mismatch.value, "detail", None) == "exchange_environment_mismatch"


def test_credential_ref_allowlist_blocks_injection() -> None:
    assert is_allowlisted_credential_ref("env:BYBIT_OPERATOR")
    assert not is_allowlisted_credential_ref("BYBIT_API_SECRET")
    assert not is_allowlisted_credential_ref("env:BYBIT_OPERATOR;cat")
    with pytest.raises(ValueError):
        enroll_operator_binding(
            InMemoryBindingStore(),
            __import__(
                "apps.api.app.exchange.bindings", fromlist=["OperatorEnrollmentSpec"]
            ).OperatorEnrollmentSpec(
                owner_user_id=uuid.uuid4(),
                environment=ExchangeEnvironment.TESTNET,
                credential_ref="not-allowlisted",
                display_label="x",
                attestation="attestation",
            ),
        )


def test_private_reads_remain_fail_closed_by_default() -> None:
    clear_settings_cache()
    settings = _settings()
    assert settings.private_data_reads_enabled is False
    store = InMemoryBindingStore()
    principal = AuthenticatedPrincipal(user_id=str(uuid.uuid4()), role="authenticated")
    with pytest.raises(Exception) as exc:
        require_active_binding_for_principal(
            principal=principal, store=store, settings=settings
        )
    assert getattr(exc.value, "detail", None) == "ownership_schema_required"


def test_alembic_env_embeds_identity_guard() -> None:
    env_py = (ROOT / "apps/api/alembic/env.py").read_text(encoding="utf-8")
    assert "_assert_dev_migration_target" in env_py
    assert "verify_dev_database_target" in env_py
    assert "wmirifmgaftassgrfbyl" in env_py


def test_deps_do_not_set_role_or_jwt_guc() -> None:
    deps = (ROOT / "apps/api/app/deps.py").read_text(encoding="utf-8")
    assert "Does not SET ROLE" in deps
    assert "session.execute" not in deps or "SET ROLE" not in deps.split("def get_db_session", 1)[-1]
    assert "request.jwt.claim" not in deps
    assert "set_config(" not in deps
    assert 'text("SET' not in deps and "text('SET" not in deps


def test_proxy_source_rejects_mixing_break_glass_semantics() -> None:
    proxy = (
        ROOT / "apps/web/src/lib/security/authenticated-proxy.ts"
    ).read_text(encoding="utf-8")
    assert "Bearer" in proxy
    assert "authentication_required" in proxy
    assert "X-Forwarded-For" in proxy  # documented as not forwarded
    assert "allowOperatorBreakGlass" in proxy


def test_privileged_bypass_documented_in_ownership_module() -> None:
    ownership = (ROOT / "apps/api/app/ownership.py").read_text(encoding="utf-8")
    assert "bypass" in ownership.lower()
    assert "RLS" in ownership
    catalog = (ROOT / "apps/api/app/catalog_service.py").read_text(encoding="utf-8")
    assert "Application authorization is primary" in catalog
