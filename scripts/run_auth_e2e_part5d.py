"""
Class D Auth E2E runner for development project wmirifmgaftassgrfbyl.

Defaults to preflight-only. Creating users / signing in requires:
  CRYPTONOVA_APPROVE_AUTH_E2E=yes
  SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) in env — never logged.

Never prints tokens, passwords, or API keys.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env", override=False)
load_dotenv(_ROOT / "apps" / "web" / ".env.local", override=False)

PROJECT = "wmirifmgaftassgrfbyl"
META_PROBE = "phase3c_part5d"
EMAIL_A = "cryptonova.part5d.a+dev@example.com"
EMAIL_B = "cryptonova.part5d.b+dev@example.com"
STATE_PATH = _ROOT / ".local" / "part5d_auth_e2e_state.json"  # gitignored via .local if needed


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip(
        "/"
    )


def _publishable() -> str:
    return (os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "").strip()


def _admin_key() -> str:
    for k in (
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SECRET",
    ):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict | list | str]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for hk, hv in headers.items():
        req.add_header(hk, hv)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            parsed: dict | list | str = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def preflight() -> dict:
    from sqlalchemy import create_engine, text

    from apps.api.app.database_url import normalize_database_url
    from scripts.verify_dev_database_target import (
        resolve_dev_database_url,
        summarize_identity,
        verify_dev_database_target,
    )

    os.environ.setdefault("CRYPTONOVA_DB_TARGET", "development")
    os.environ.setdefault("CRYPTONOVA_DEV_PROJECT_REF", PROJECT)
    os.environ.setdefault("CRYPTONOVA_USE_DATABASE_URL_AS_DEV", "true")

    identity = verify_dev_database_target(connect=False)
    if identity.project_ref != PROJECT:
        raise RuntimeError("project_ref_mismatch")
    raw = resolve_dev_database_url(os.environ)
    eng = create_engine(normalize_database_url(raw), pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        rev = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
    eng.dispose()
    if rev != "20261105_0003":
        raise RuntimeError(f"unexpected_revision:{rev}")

    private = (os.environ.get("PRIVATE_DATA_READS_ENABLED") or "false").strip().lower()
    if private in {"1", "true", "yes", "on"}:
        raise RuntimeError("private_reads_must_remain_false")
    if (os.environ.get("AGENT_ALLOW_LIVE") or "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError("live_trading_must_remain_disabled")
    if (os.environ.get("OPERATOR_LOCAL_BROWSER_PROXY_ENABLED") or "false").strip().lower() == "true":
        raise RuntimeError("break_glass_must_remain_disabled")

    base = _supabase_url()
    if PROJECT not in base:
        raise RuntimeError("supabase_url_not_dev_project")
    pub = _publishable()
    if not pub:
        raise RuntimeError("publishable_key_missing")

    # Auth public settings
    st, settings = _http_json(
        "GET",
        f"{base}/auth/v1/settings",
        headers={"apikey": pub, "Authorization": f"Bearer {pub}"},
    )
    if st != 200 or not isinstance(settings, dict):
        raise RuntimeError(f"auth_settings_unavailable:{st}")
    autoconfirm = bool(settings.get("mailer_autoconfirm"))
    disable_signup = bool(settings.get("disable_signup"))

    admin = bool(_admin_key())
    return {
        "identity": summarize_identity(identity),
        "alembic": rev,
        "supabase_host": base.split("//")[-1],
        "publishable_set": True,
        "admin_key_set": admin,
        "mailer_autoconfirm": autoconfirm,
        "disable_signup": disable_signup,
        "private_reads": False,
        "break_glass": False,
        "data_api_gate_env": _truthy("CRYPTONOVA_DATA_API_APP_NOT_EXPOSED"),
    }


def create_users() -> dict:
    admin = _admin_key()
    if not admin:
        raise RuntimeError(
            "missing_admin_key: set SUPABASE_SERVICE_ROLE_KEY in gitignored .env"
        )
    if not _truthy("CRYPTONOVA_APPROVE_AUTH_E2E"):
        raise RuntimeError("missing_CRYPTONOVA_APPROVE_AUTH_E2E")
    base = _supabase_url()
    created = []
    for email, alias in ((EMAIL_A, "A"), (EMAIL_B, "B")):
        password = secrets.token_urlsafe(24)
        status, body = _http_json(
            "POST",
            f"{base}/auth/v1/admin/users",
            headers={
                "apikey": admin,
                "Authorization": f"Bearer {admin}",
            },
            body={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"cryptonova_probe": META_PROBE, "alias": alias},
            },
        )
        if status not in {200, 201} or not isinstance(body, dict):
            raise RuntimeError(f"create_user_failed:{alias}:http_{status}")
        uid = body.get("id")
        if not uid:
            raise RuntimeError(f"create_user_missing_id:{alias}")
        created.append(
            {
                "alias": alias,
                "email": email,
                "id": uid,
                # password kept only in local state file with restricted use — never print
                "password": password,
            }
        )
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {"project": PROJECT, "probe": META_PROBE, "users": created},
            indent=2,
        ),
        encoding="utf-8",
    )
    # Return without passwords
    return {
        "users": [{"alias": u["alias"], "email": u["email"], "id": u["id"]} for u in created],
        "state_path": str(STATE_PATH.relative_to(_ROOT)),
    }


def sign_in(email: str, password: str) -> str:
    pub = _publishable()
    base = _supabase_url()
    status, body = _http_json(
        "POST",
        f"{base}/auth/v1/token?grant_type=password",
        headers={"apikey": pub, "Authorization": f"Bearer {pub}"},
        body={"email": email, "password": password},
    )
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"sign_in_failed:http_{status}")
    token = body.get("access_token")
    if not token or not isinstance(token, str):
        raise RuntimeError("sign_in_missing_access_token")
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true", default=True)
    parser.add_argument("--create-users", action="store_true")
    parser.add_argument("--execute-jwt-tests", action="store_true")
    args = parser.parse_args(argv)
    # argparse default True for preflight is awkward when other flags set
    try:
        info = preflight()
    except Exception as exc:  # noqa: BLE001
        print(f"AUTH_E2E_PREFLIGHT_FAIL detail={type(exc).__name__}:{exc}")
        return 2
    print("AUTH_E2E_PREFLIGHT_OK")
    print(json.dumps({k: v for k, v in info.items() if k != "identity"}, indent=2, default=str))
    print(json.dumps({"identity": info["identity"]}, indent=2, default=str))

    if not info["admin_key_set"]:
        print(
            "AUTH_E2E_BLOCKED reason=missing_SUPABASE_SERVICE_ROLE_KEY "
            "(required for Admin createUser with email_confirm; avoids confirmation emails)"
        )
        return 3

    if args.create_users:
        try:
            created = create_users()
        except Exception as exc:  # noqa: BLE001
            print(f"AUTH_E2E_CREATE_FAIL detail={type(exc).__name__}:{exc}")
            return 1
        print("AUTH_E2E_USERS_CREATED")
        print(json.dumps(created, indent=2))

    if args.execute_jwt_tests:
        print("AUTH_E2E_JWT_TESTS use dedicated follow-up after users exist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
