"""Gate 63B — fail-closed runtime DB URL selection (no remote)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from apps.api.app.config import ApiSettings
from apps.api.app.database_url import DatabaseUrlError
from apps.api.app.db import configure_engine, reset_engine
from apps.api.app.runtime_db import (
    RuntimeDatabaseConfigError,
    assert_runtime_url_username_allowed,
    is_privileged_runtime_username,
    resolve_application_database_url,
)


def test_legacy_mode_uses_database_url() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://appuser:x@127.0.0.1:5432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=False,
        database_runtime_url=None,
    )
    url = resolve_application_database_url(settings)
    assert "127.0.0.1" in url
    assert "appuser" in url


def test_runtime_mode_requires_runtime_url() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://postgres:x@127.0.0.1:5432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=True,
        database_runtime_url=None,
    )
    with pytest.raises(RuntimeDatabaseConfigError, match="database_runtime_url_required"):
        resolve_application_database_url(settings)


def test_runtime_mode_rejects_postgres_username() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://postgres:x@127.0.0.1:5432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=True,
        database_runtime_url="postgresql://postgres.wmirifmgaftassgrfbyl:x@127.0.0.1:5432/postgres",
    )
    with pytest.raises(
        RuntimeDatabaseConfigError, match="runtime_url_privileged_username_rejected"
    ):
        resolve_application_database_url(settings)


def test_runtime_mode_accepts_login_username() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://postgres:x@127.0.0.1:5432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=True,
        database_runtime_url="postgresql://cryptonova_api_login:secret@127.0.0.1:5432/postgres",
    )
    url = resolve_application_database_url(settings)
    assert "cryptonova_api_login" in url
    assert "postgres:" not in url.split("@")[0]


def test_no_silent_fallback_when_runtime_missing_even_if_admin_present() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://postgres:x@127.0.0.1:5432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=True,
        database_runtime_url="  ",
    )
    with pytest.raises(RuntimeDatabaseConfigError, match="database_runtime_url_required"):
        settings.sqlalchemy_url()


def test_privileged_username_helper() -> None:
    assert is_privileged_runtime_username("postgres")
    assert is_privileged_runtime_username("postgres.wmirifmgaftassgrfbyl")
    assert is_privileged_runtime_username("service_role")
    assert not is_privileged_runtime_username("cryptonova_api_login")
    with pytest.raises(RuntimeDatabaseConfigError):
        assert_runtime_url_username_allowed("supabase_admin")


def test_sqlalchemy_url_legacy_still_works() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://postgres:x@127.0.0.1:5432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=False,
    )
    legacy = settings.sqlalchemy_url_legacy()
    assert "postgresql+psycopg://" in legacy


def test_configure_engine_legacy_does_not_require_runtime_url() -> None:
    reset_engine()
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql://cryptonova_test@127.0.0.1:55432/postgres",
        database_ssl_require=False,
        runtime_db_identity_enabled=False,
    )
    try:
        eng = create_engine(settings.sqlalchemy_url(), future=True)
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local disposable PG unavailable: {type(exc).__name__}")
    finally:
        reset_engine()
