"""Phase 2C offline auth tests — mocked verifier / local JWT crypto only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from apps.api.app.auth.errors import AuthConfigError, AuthError
from apps.api.app.auth.jwt_verifier import (
    StaticMappingVerifier,
    SupabaseHS256Verifier,
    principal_from_payload,
)
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.ownership import assert_same_user


ISSUER = "https://example.supabase.co/auth/v1"
AUDIENCE = "authenticated"
SECRET = "test-only-hs256-secret-not-for-production-32b+"


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret=SECRET,
        supabase_jwt_audience=AUDIENCE,
        supabase_jwt_issuer=ISSUER,
        private_data_reads_enabled=False,
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _principal(user_id: str = "user-1") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user_id,
        role="authenticated",
        email="u@example.com",
        scopes=("read:self",),
    )


def _client(
    verifier: StaticMappingVerifier | None = None,
    *,
    settings: ApiSettings | None = None,
) -> TestClient:
    clear_settings_cache()
    settings = settings or _settings()
    app = create_app(settings)
    if verifier is not None:
        app.state.token_verifier = verifier
    return TestClient(app)


def _hs256_token(**claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "user-1",
        "role": "authenticated",
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "nbf": now - timedelta(seconds=5),
        "exp": now + timedelta(minutes=5),
        "email": "u@example.com",
    }
    payload.update(claims)
    return jwt.encode(payload, SECRET, algorithm="HS256")


def test_health_still_public() -> None:
    client = _client(StaticMappingVerifier({}))
    assert client.get("/health").status_code == 200


def test_me_missing_authorization() -> None:
    client = _client(StaticMappingVerifier({}))
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing_authorization"


def test_me_valid_token() -> None:
    p = _principal()
    client = _client(StaticMappingVerifier({"good": p}))
    resp = client.get("/api/v1/me", headers={"Authorization": "Bearer good"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "user-1"
    assert body["role"] == "authenticated"
    assert body["private_data_reads_enabled"] is False
    assert "good" not in resp.text  # token not echoed


def test_expired_jwt_hs256() -> None:
    settings = _settings()
    app = create_app(settings)
    # Use real HS256 verifier path via app state override with concrete verifier
    app.state.token_verifier = SupabaseHS256Verifier(
        secret=SECRET, issuer=ISSUER, audience=AUDIENCE
    )
    client = TestClient(app)
    token = _hs256_token(exp=datetime.now(timezone.utc) - timedelta(minutes=1))
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_expired"


def test_invalid_signature() -> None:
    verifier = SupabaseHS256Verifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    bad = jwt.encode(
        {
            "sub": "user-1",
            "role": "authenticated",
            "aud": AUDIENCE,
            "iss": ISSUER,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "wrong-secret-also-long-enough-for-hs256!!",
        algorithm="HS256",
    )
    with pytest.raises(AuthError) as exc:
        verifier.verify_access_token(bad)
    assert exc.value.code == "invalid_signature"


def test_wrong_issuer_audience() -> None:
    verifier = SupabaseHS256Verifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(AuthError) as exc:
        verifier.verify_access_token(_hs256_token(iss="https://evil.example/auth/v1"))
    assert exc.value.code == "invalid_issuer"
    with pytest.raises(AuthError) as exc2:
        verifier.verify_access_token(_hs256_token(aud="someone-else"))
    assert exc2.value.code == "invalid_audience"


def test_unsupported_algorithm_none() -> None:
    # alg=none style payload rejected by algorithm allowlist / decode
    header = {"alg": "none", "typ": "JWT"}
    import base64
    import json

    def b64(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    token = f"{b64(header)}.{b64({'sub': 'x', 'role': 'authenticated'})}."
    verifier = SupabaseHS256Verifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    with pytest.raises(AuthError) as exc:
        verifier.verify_access_token(token)
    assert exc.value.code in {"unsupported_algorithm", "malformed_token", "invalid_token"}


def test_missing_subject() -> None:
    with pytest.raises(AuthError) as exc:
        principal_from_payload(
            {"role": "authenticated", "aud": AUDIENCE, "iss": ISSUER}
        )
    assert exc.value.code == "missing_claim_sub"


def test_service_role_rejected() -> None:
    with pytest.raises(AuthError) as exc:
        principal_from_payload(
            {
                "sub": "svc",
                "role": "service_role",
                "aud": AUDIENCE,
                "iss": ISSUER,
            }
        )
    assert exc.value.code == "non_user_token"


def test_jwks_unavailable_fail_closed() -> None:
    client = _client(
        StaticMappingVerifier({"t": AuthConfigError("jwks_unavailable")})
    )
    resp = client.get("/api/v1/me", headers={"Authorization": "Bearer t"})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "jwks_unavailable"


def test_catalog_requires_auth() -> None:
    client = _client(StaticMappingVerifier({}))
    for path in (
        "/api/v1/agents/decisions",
        "/api/v1/system/events",
        "/api/v1/strategies",
    ):
        assert client.get(path).status_code == 401


def test_catalog_auth_ok_but_ownership_blocks_real_rows() -> None:
    p = _principal()
    client = _client(StaticMappingVerifier({"good": p}))
    resp = client.get(
        "/api/v1/agents/decisions?limit=10&offset=0",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "ownership_schema_required"


def test_pagination_bounds() -> None:
    p = _principal()
    # Enable catalog gate so query validation is observable (not short-circuited by 403).
    settings = _settings(private_data_reads_enabled=True)
    client = _client(StaticMappingVerifier({"good": p}), settings=settings)
    bad = client.get(
        "/api/v1/strategies?limit=0",
        headers={"Authorization": "Bearer good"},
    )
    assert bad.status_code == 422
    bad2 = client.get(
        "/api/v1/strategies?limit=101",
        headers={"Authorization": "Bearer good"},
    )
    assert bad2.status_code == 422


def test_cross_tenant_forbidden() -> None:
    with pytest.raises(Exception) as exc:
        assert_same_user(_principal("user-a"), "user-b")
    assert getattr(exc.value, "status_code", None) == 403


def test_private_reads_flag_without_db_fail_closed() -> None:
    """When enabled without DATABASE_URL, catalog must fail closed (no row dump)."""
    p = _principal()
    settings = _settings(private_data_reads_enabled=True, database_url=None)
    client = _client(StaticMappingVerifier({"good": p}), settings=settings)
    resp = client.get(
        "/api/v1/agents/decisions",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "database_not_configured"


def test_status_reports_auth_flags() -> None:
    client = _client(StaticMappingVerifier({}))
    body = client.get("/api/v1/system/status").json()
    assert body["authentication_required_for_private_data"] is True
    assert body["private_catalog_reads_enabled"] is False
    assert body["trading_http_endpoints_enabled"] is False
