"""
Fail-closed identity checks for CryptoNova development database targets.

Never print passwords or full DATABASE_URL values. Use redacted host/project-ref only.

Operator clarification (2026-11-06): project ``wmirifmgaftassgrfbyl`` is the
explicitly approved **development** Supabase project (never designated production).
Future production projects must be listed in CRYPTONOVA_PROD_PROJECT_REFS.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps.api.app.database_url import (  # noqa: E402
    DatabaseUrlError,
    inspect_database_url,
)

# Operator-approved development project (existing Supabase project; no second project).
DEFAULT_APPROVED_DEV_PROJECT_REFS: frozenset[str] = frozenset(
    {
        "wmirifmgaftassgrfbyl",
    }
)

# Future production deny-list (empty until a production project is designated).
# Override/extend with CRYPTONOVA_PROD_PROJECT_REFS=ref1,ref2
DEFAULT_PRODUCTION_PROJECT_REFS: frozenset[str] = frozenset()

_DIRECT_HOST_RE = re.compile(
    r"^db\.(?P<ref>[a-z0-9]+)\.supabase\.co$",
    re.IGNORECASE,
)
_POOLER_USER_RE = re.compile(
    r"^(?:postgres\.)(?P<ref>[a-z0-9]+)$",
    re.IGNORECASE,
)


class DevTargetError(RuntimeError):
    """Fail-closed identity / approval error — message must not include secrets."""


@dataclass(frozen=True, slots=True)
class DevTargetIdentity:
    classification: str
    project_ref: str | None
    host: str
    database: str
    user: str
    pooler_hint: str
    redacted_url: str
    is_supabase_like: bool
    migrations_approved: bool


def extract_project_ref(*, host: str, user: str) -> str | None:
    """Derive Supabase project ref from direct host or pooler username."""
    host_l = (host or "").lower().strip()
    user_l = unquote(user or "").strip()
    m = _DIRECT_HOST_RE.match(host_l)
    if m:
        return m.group("ref").lower()
    m = _POOLER_USER_RE.match(user_l)
    if m:
        return m.group("ref").lower()
    if user_l and "." not in user_l and host_l.startswith("db.") and "supabase" in host_l:
        parts = host_l.split(".")
        if len(parts) >= 3 and parts[0] == "db":
            return parts[1].lower()
    return None


def _env_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _production_refs(environ: Mapping[str, str]) -> frozenset[str]:
    refs = set(DEFAULT_PRODUCTION_PROJECT_REFS)
    extra = (environ.get("CRYPTONOVA_PROD_PROJECT_REFS") or "").strip()
    if extra:
        for part in extra.split(","):
            token = part.strip().lower()
            if token:
                refs.add(token)
    return frozenset(refs)


def _approved_dev_refs(environ: Mapping[str, str]) -> frozenset[str]:
    refs = set(DEFAULT_APPROVED_DEV_PROJECT_REFS)
    extra = (environ.get("CRYPTONOVA_APPROVED_DEV_PROJECT_REFS") or "").strip()
    if extra:
        for part in extra.split(","):
            token = part.strip().lower()
            if token:
                refs.add(token)
    return frozenset(refs)


def resolve_dev_database_url(environ: Mapping[str, str]) -> str:
    """
    Prefer DEV_DATABASE_URL for development ops.
    Never treat a variable name alone as proof of isolation.
    """
    for key in ("DEV_DATABASE_URL", "CRYPTONOVA_DEV_DATABASE_URL"):
        value = (environ.get(key) or "").strip()
        if value:
            return value
    if (environ.get("CRYPTONOVA_DB_TARGET") or "").strip().lower() == "development":
        shared = (environ.get("DATABASE_URL") or "").strip()
        if shared and _env_truthy(environ.get("CRYPTONOVA_ALLOW_SHARED_DATABASE_URL")):
            return shared
        # Operator-approved single-project development: allow DATABASE_URL when
        # project ref is in the approved-dev allowlist AND explicitly opted in
        # via CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true (still fail-closed otherwise).
        if shared and _env_truthy(environ.get("CRYPTONOVA_USE_DATABASE_URL_AS_DEV")):
            return shared
    raise DevTargetError(
        "missing_dev_database_url: set DEV_DATABASE_URL or "
        "CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true with DATABASE_URL for the approved "
        "development project"
    )


def verify_dev_database_target(
    environ: Mapping[str, str] | None = None,
    *,
    require_migration_approval: bool = False,
    connect: bool = False,
) -> DevTargetIdentity:
    """
    Multi-check fail-closed verification for development migration targets.

    Checks:
    1) CRYPTONOVA_DB_TARGET must be exactly 'development'
    2) Operator-approved CRYPTONOVA_DEV_PROJECT_REF required
    3) Approved ref must be in DEFAULT_APPROVED_DEV_PROJECT_REFS (or env extend)
    4) DEV_DATABASE_URL / allowed DATABASE_URL present
    5) Parsed host/user project ref must match approved dev ref
    6) Project ref must not be in production deny-list
    7) Optional live connection metadata check (connect=True)
    8) Migration writes require CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes
    """
    env = environ if environ is not None else os.environ
    classification = (env.get("CRYPTONOVA_DB_TARGET") or "").strip().lower()
    if not classification:
        raise DevTargetError("missing_db_target: set CRYPTONOVA_DB_TARGET=development")
    if classification in {"production", "prod", "main", "live"}:
        raise DevTargetError("production_target_forbidden")
    if classification != "development":
        raise DevTargetError("ambiguous_db_target: only 'development' is accepted here")

    approved_ref = (env.get("CRYPTONOVA_DEV_PROJECT_REF") or "").strip().lower()
    if not approved_ref:
        raise DevTargetError(
            "missing_dev_project_ref: set CRYPTONOVA_DEV_PROJECT_REF to the "
            "operator-approved development Supabase project reference"
        )
    if not re.fullmatch(r"[a-z0-9]{10,}", approved_ref):
        raise DevTargetError("invalid_dev_project_ref_format")

    approved_allow = _approved_dev_refs(env)
    if approved_ref not in approved_allow:
        raise DevTargetError(
            "dev_project_ref_not_in_allowlist: unknown project; add only after "
            "operator approval via CRYPTONOVA_APPROVED_DEV_PROJECT_REFS"
        )

    prod_refs = _production_refs(env)
    if approved_ref in prod_refs:
        raise DevTargetError(
            "dev_project_ref_matches_production: project is listed as production"
        )

    raw_url = resolve_dev_database_url(env)
    try:
        info = inspect_database_url(raw_url, require_ssl_for_remote=True)
    except DatabaseUrlError as exc:
        raise DevTargetError(f"database_url_invalid:{exc}") from exc

    if info.host in {"localhost", "127.0.0.1", "::1"}:
        if not _env_truthy(env.get("CRYPTONOVA_ALLOW_LOCAL_DISPOSABLE_DB")):
            raise DevTargetError(
                "local_db_requires_CRYPTONOVA_ALLOW_LOCAL_DISPOSABLE_DB=true"
            )
        project_ref = approved_ref
    else:
        if not info.is_supabase_like:
            raise DevTargetError("non_supabase_remote_host_rejected")
        project_ref = extract_project_ref(host=info.host, user=info.user)
        if not project_ref:
            raise DevTargetError("unable_to_extract_project_ref_from_connection")
        if project_ref != approved_ref:
            raise DevTargetError("project_ref_hostname_mismatch")
        if project_ref not in approved_allow:
            raise DevTargetError("connection_project_ref_not_in_allowlist")
        if project_ref in prod_refs:
            raise DevTargetError("connection_targets_production_project_ref")

    migrations_approved = _env_truthy(env.get("CRYPTONOVA_ALLOW_DEV_MIGRATIONS"))
    if require_migration_approval and not migrations_approved:
        raise DevTargetError(
            "migrations_not_approved: set CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes after "
            "reviewing the development migration preflight"
        )

    identity = DevTargetIdentity(
        classification=classification,
        project_ref=project_ref,
        host=info.host,
        database=info.database,
        user=info.user.split(".")[0] if info.user else "",
        pooler_hint=info.pooler_hint,
        redacted_url=info.redacted_url,
        is_supabase_like=info.is_supabase_like
        or info.host in {"localhost", "127.0.0.1", "::1"},
        migrations_approved=migrations_approved,
    )

    if connect:
        _verify_live_connection(raw_url)

    return identity


def _verify_live_connection(raw_url: str) -> None:
    """Optional SELECT-only probe — never prints URL/password."""
    try:
        from sqlalchemy import create_engine, text

        from apps.api.app.database_url import normalize_database_url

        url = normalize_database_url(raw_url, require_ssl_for_remote=True)
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            try:
                conn.execute(text("SELECT version_num FROM app.alembic_version LIMIT 1"))
            except Exception:
                pass
        engine.dispose()
    except DevTargetError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DevTargetError(f"live_connection_failed:{type(exc).__name__}") from exc


def summarize_identity(identity: DevTargetIdentity) -> dict[str, object]:
    """Operator-safe summary (no secrets)."""
    return {
        "classification": identity.classification,
        "project_ref": identity.project_ref,
        "host": identity.host,
        "database": identity.database,
        "pooler_hint": identity.pooler_hint,
        "redacted_url": identity.redacted_url,
        "migrations_approved": identity.migrations_approved,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Verify CryptoNova development database target (fail-closed)."
    )
    parser.add_argument(
        "--require-migration-approval",
        action="store_true",
        help="Require CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Perform a SELECT-only live connectivity check",
    )
    args = parser.parse_args(argv)
    try:
        identity = verify_dev_database_target(
            require_migration_approval=args.require_migration_approval,
            connect=args.connect,
        )
    except DevTargetError as exc:
        print(f"DEV_TARGET_REJECTED detail={exc}")
        return 2
    print("DEV_TARGET_OK")
    print(json.dumps(summarize_identity(identity), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
