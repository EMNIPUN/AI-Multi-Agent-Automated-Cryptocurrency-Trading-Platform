"""Phase 3C Part 5B — offline Auth wiring / kill-switch regressions (no DB writes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from apps.api.app.auth.errors import AuthError
from apps.api.app.auth.jwt_verifier import SupabaseHS256Verifier, principal_from_payload
from apps.api.app.config import ApiSettings, clear_settings_cache
from scripts.verify_dev_database_target import DevTargetError, verify_dev_database_target

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "https://wmirifmgaftassgrfbyl.supabase.co/auth/v1"
AUDIENCE = "authenticated"
SECRET = "phase5b-test-only-hs256-secret-not-real-32b"


def test_api_settings_defaults_keep_private_reads_and_jwks() -> None:
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        supabase_url="https://wmirifmgaftassgrfbyl.supabase.co",
        auth_jwt_mode="jwks",
        supabase_jwt_audience="authenticated",
        private_data_reads_enabled=False,
        database_url=None,
    )
    assert settings.private_data_reads_enabled is False
    assert settings.auth_jwt_mode == "jwks"
    assert settings.resolved_jwt_issuer() == ISSUER
    assert settings.resolved_jwks_url().endswith("/auth/v1/.well-known/jwks.json")
    assert "wmirifmgaftassgrfbyl" in settings.resolved_jwks_url()


def test_wrong_project_issuer_rejected() -> None:
    verifier = SupabaseHS256Verifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            "role": "authenticated",
            "aud": AUDIENCE,
            "iss": "https://other-project.supabase.co/auth/v1",
            "iat": now,
            "nbf": now - timedelta(seconds=5),
            "exp": now + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthError) as exc:
        verifier.verify_access_token(token)
    assert exc.value.code == "invalid_issuer"


def test_invalid_signature_rejected() -> None:
    verifier = SupabaseHS256Verifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            "role": "authenticated",
            "aud": AUDIENCE,
            "iss": ISSUER,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    bad = token[:-6] + ("XXXXXX" if not token.endswith("XXXXXX") else "YYYYYY")
    with pytest.raises(AuthError):
        verifier.verify_access_token(bad)


def test_service_role_rejected() -> None:
    with pytest.raises(AuthError) as exc:
        principal_from_payload(
            {
                "sub": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                "role": "service_role",
                "aud": AUDIENCE,
                "iss": ISSUER,
            }
        )
    assert exc.value.code == "non_user_token"


def test_dev_database_guard_still_fail_closed() -> None:
    with pytest.raises(DevTargetError):
        verify_dev_database_target(
            {
                "CRYPTONOVA_DB_TARGET": "production",
                "CRYPTONOVA_DEV_PROJECT_REF": "wmirifmgaftassgrfbyl",
                "DEV_DATABASE_URL": (
                    "postgresql://postgres.wmirifmgaftassgrfbyl:x@"
                    "aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
                ),
            }
        )


def test_operator_proxy_gate_defaults_false_in_example() -> None:
    example = (ROOT / "apps/web/.env.development.example").read_text(encoding="utf-8")
    assert "OPERATOR_LOCAL_BROWSER_PROXY_ENABLED=false" in example
    assert "wmirifmgaftassgrfbyl" in example
    assert "service_role" in example.lower()


def test_session_storage_not_used_when_supabase_configured() -> None:
    src = (ROOT / "apps/web/src/lib/auth/browser-access-token.ts").read_text(
        encoding="utf-8"
    )
    assert "Auth session only" in src or "session only" in src.lower()
    # When supabase client exists, must not fall through to getBrowserAccessToken on miss
    assert "if (supabase)" in src
    assert "return token || null" in src or "return token || null;" in src
    # Sync path must also refuse interim storage when public env is set
    assert "authHeadersSync" in src
    assert 'if (url && anon) return {}' in src


def test_live_trading_flags_off_in_api_example() -> None:
    example = (ROOT / "apps/api/.env.development.example").read_text(encoding="utf-8")
    assert "PRIVATE_DATA_READS_ENABLED=false" in example
    assert "AUTH_JWT_MODE=jwks" in example
    assert "wmirifmgaftassgrfbyl" in example
