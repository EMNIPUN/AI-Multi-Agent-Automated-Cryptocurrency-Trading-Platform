"""Phase 2B offline tests — Supabase URL safety + migration bootstrap audit."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.database_url import (
    APP_SCHEMA,
    DatabaseUrlError,
    inspect_database_url,
    normalize_database_url,
    redact_database_url,
)
from apps.api.app.migration_audit import audit_initial_migration, audit_ownership_migration


@pytest.fixture(autouse=True)
def _clear() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_normalize_psycopg_and_ssl_for_remote() -> None:
    url = normalize_database_url(
        "postgresql://user:secret@db.example.supabase.co:5432/postgres"
    )
    assert url.startswith("postgresql+psycopg://")
    assert "sslmode=require" in url
    assert "secret" in url  # still present for connection — never log this string


def test_redact_hides_password() -> None:
    raw = "postgresql+psycopg://user:s3cret@db.example.supabase.co:5432/postgres?sslmode=require"
    red = redact_database_url(raw)
    assert "s3cret" not in red
    assert "***" in red
    assert "db.example.supabase.co" in red


def test_password_url_encoding_special_chars() -> None:
    # Passwords with @/: must be percent-encoded in DATABASE_URL.
    encoded = (
        "postgresql://user:p%40ss%2Fw%3Aord@db.example.supabase.co:5432/postgres"
    )
    url = normalize_database_url(encoded)
    info = inspect_database_url(encoded)
    assert info.sslmode == "require"
    red = redact_database_url(url)
    assert "***" in red
    assert "p@ss" not in red
    assert "%40ss" not in red


def test_session_vs_transaction_pooler_hints() -> None:
    session = inspect_database_url(
        "postgresql://u:p@aws-0-xyz.pooler.supabase.com:5432/postgres"
    )
    tx = inspect_database_url(
        "postgresql://u:p@aws-0-xyz.pooler.supabase.com:6543/postgres"
    )
    assert session.pooler_hint == "session_pooler"
    assert tx.pooler_hint == "transaction_pooler"
    assert session.is_supabase_like is True


def test_localhost_skips_forced_ssl() -> None:
    url = normalize_database_url(
        "postgresql://u:p@127.0.0.1:5432/postgres", require_ssl_for_remote=True
    )
    assert "sslmode" not in url or "sslmode=require" not in url


def test_placeholder_and_empty_rejected() -> None:
    with pytest.raises(DatabaseUrlError):
        normalize_database_url("")
    with pytest.raises(DatabaseUrlError):
        normalize_database_url("driver://user:pass@localhost/dbname")


def test_settings_sqlalchemy_url_safe_errors() -> None:
    settings = ApiSettings(_env_file=None, database_url=None)
    with pytest.raises(DatabaseUrlError):
        settings.sqlalchemy_url()


def test_migration_audit_passes() -> None:
    result = audit_initial_migration()
    assert result.ok, result.issues
    assert f"{APP_SCHEMA}.agent_decisions" in result.model_tables
    ownership = audit_ownership_migration()
    assert ownership.ok, ownership.issues


def test_alembic_env_bootstraps_schema_before_version_table() -> None:
    env = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "api"
        / "alembic"
        / "env.py"
    ).read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS" in env
    assert "version_table_schema" in env
    # Bootstrap helper appears before run_migrations in online path.
    assert env.index("_ensure_app_schema") < env.index("context.run_migrations")
    assert "include_name" in env
    assert "include_object" in env
    assert 'version_table_schema=APP_SCHEMA' in env or 'version_table_schema=APP_SCHEMA' in env.replace(
        " ", ""
    )


def test_security_sql_revokes_anon() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "api"
        / "sql"
        / "revoke_public_api_access.sql"
    ).read_text(encoding="utf-8")
    assert "REVOKE ALL ON SCHEMA app" in sql
    assert "anon" in sql
    assert "authenticated" in sql
    assert "MANUAL" in sql.upper() or "DO NOT auto-run" in sql


def test_app_import_and_no_create_all_in_runtime() -> None:
    from apps.api import main
    from apps.api.app import db as db_mod

    assert main.app is not None
    src = Path(db_mod.__file__).read_text(encoding="utf-8")
    assert "create_all" not in src
