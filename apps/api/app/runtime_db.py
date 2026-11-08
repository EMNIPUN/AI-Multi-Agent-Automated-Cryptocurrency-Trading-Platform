"""
Least-privilege runtime database URL selection (disabled by default).

When RUNTIME_DB_IDENTITY_ENABLED is false, callers keep using DATABASE_URL.
When true (future Gate 63 only): require DATABASE_RUNTIME_URL, reject privileged
usernames, never fall back to DATABASE_URL.

URL username checks are heuristic only — startup must also verify effective
session_user / rolbypassrls against live PostgreSQL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import Engine

from apps.api.app.database_url import (
    DatabaseUrlError,
    inspect_database_url,
    normalize_database_url,
    redact_database_url,
)

if TYPE_CHECKING:
    from apps.api.app.config import ApiSettings

# Heuristic denylist for runtime URL usernames (not proof of role privileges).
_PRIVILEGED_USER_RE = re.compile(
    r"^(postgres|supabase_admin|supabase_auth_admin|service_role|"
    r"authenticator|dashboard_user|neon_superuser)(\.|$)",
    re.IGNORECASE,
)

_ALLOWED_RUNTIME_USERS = frozenset(
    {
        "cryptonova_api_login",
        "cryptonova_api_runtime_login",  # local harness alias
    }
)


class RuntimeDatabaseConfigError(DatabaseUrlError):
    """Fail-closed runtime DB configuration — message must not include secrets."""


@dataclass(frozen=True)
class RuntimeDbIdentityProbe:
    session_user: str
    current_user: str
    rolbypassrls: bool
    rolsuper: bool
    redacted_url: str


def is_privileged_runtime_username(user: str) -> bool:
    text_u = (user or "").strip()
    if not text_u:
        return True
    # pooler form postgres.<projectref>
    if _PRIVILEGED_USER_RE.match(text_u):
        return True
    base = text_u.split(".", 1)[0].lower()
    return base in {
        "postgres",
        "supabase_admin",
        "supabase_auth_admin",
        "service_role",
        "authenticator",
        "dashboard_user",
    }


def assert_runtime_url_username_allowed(user: str) -> None:
    if is_privileged_runtime_username(user):
        raise RuntimeDatabaseConfigError("runtime_url_privileged_username_rejected")
    # Prefer known login names; still allow other non-privileged names for local tests.
    _ = _ALLOWED_RUNTIME_USERS  # documented allowlist for operators


def resolve_application_database_url(settings: ApiSettings) -> str:
    """
    Select the SQLAlchemy URL for the application runtime engine.

    Legacy (default): DATABASE_URL.
    Least-privilege mode: DATABASE_RUNTIME_URL only — no privileged fallback.
    """
    if not settings.runtime_db_identity_enabled:
        return settings.sqlalchemy_url_legacy()

    raw = (settings.database_runtime_url or "").strip()
    if not raw:
        raise RuntimeDatabaseConfigError("database_runtime_url_required")

    try:
        info = inspect_database_url(
            raw, require_ssl_for_remote=settings.database_ssl_require
        )
    except DatabaseUrlError as exc:
        raise RuntimeDatabaseConfigError("database_runtime_url_invalid") from exc

    assert_runtime_url_username_allowed(info.user)

    # Explicitly refuse falling back even if DATABASE_URL is present.
    if settings.database_url and raw.strip() == settings.database_url.strip():
        # Same string as admin URL is not automatically wrong if admin was already
        # least-privilege — still reject privileged usernames above.
        pass

    try:
        return normalize_database_url(
            raw, require_ssl_for_remote=settings.database_ssl_require
        )
    except DatabaseUrlError as exc:
        raise RuntimeDatabaseConfigError("database_runtime_url_invalid") from exc


def probe_runtime_db_identity(
    engine: Engine, *, redacted_url: str = "<redacted>"
) -> RuntimeDbIdentityProbe:
    """Read-only identity probe — never logs passwords."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT session_user,
                       current_user,
                       r.rolbypassrls,
                       r.rolsuper
                FROM pg_roles r
                WHERE r.rolname = session_user
                """
            )
        ).one()
    return RuntimeDbIdentityProbe(
        session_user=str(row[0]),
        current_user=str(row[1]),
        rolbypassrls=bool(row[2]),
        rolsuper=bool(row[3]),
        redacted_url=redacted_url,
    )


def assert_runtime_identity_safe(probe: RuntimeDbIdentityProbe) -> None:
    """Fail closed if the live session is privileged or BYPASSRLS."""
    if probe.rolsuper:
        raise RuntimeDatabaseConfigError("runtime_session_is_superuser")
    if probe.rolbypassrls:
        raise RuntimeDatabaseConfigError("runtime_session_bypassrls")
    if is_privileged_runtime_username(probe.session_user):
        raise RuntimeDatabaseConfigError("runtime_session_privileged_username")


def validate_runtime_engine_or_raise(engine: Engine, settings: ApiSettings) -> RuntimeDbIdentityProbe:
    """
    Startup validation for least-privilege mode.

    Call only when RUNTIME_DB_IDENTITY_ENABLED is true (future Gate 63).
    """
    if not settings.runtime_db_identity_enabled:
        raise RuntimeDatabaseConfigError("runtime_identity_not_enabled")
    redacted = redact_database_url(resolve_application_database_url(settings))
    probe = probe_runtime_db_identity(engine, redacted_url=redacted)
    assert_runtime_identity_safe(probe)
    return probe
