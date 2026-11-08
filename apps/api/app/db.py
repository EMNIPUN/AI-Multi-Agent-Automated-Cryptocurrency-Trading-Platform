"""SQLAlchemy engine/session helpers for Supabase-hosted PostgreSQL."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.database_url import DatabaseUrlError
from apps.api.app.runtime_db import (
    RuntimeDatabaseConfigError,
    validate_runtime_engine_or_raise,
)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def create_db_engine(settings: ApiSettings | None = None) -> Engine:
    settings = settings or get_api_settings()
    try:
        url = settings.sqlalchemy_url()
    except DatabaseUrlError as exc:
        # Re-raise without attaching URL/password context.
        raise DatabaseUrlError(str(exc)) from None
    connect_args = settings.engine_connect_args()
    # Do not echo SQL with bound URLs; never log the URL string.
    return create_engine(
        url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )


def configure_engine(
    settings: ApiSettings | None = None,
    *,
    validate_runtime_identity: bool = True,
) -> Engine:
    """
    Build the process engine.

    When RUNTIME_DB_IDENTITY_ENABLED is true, optionally probes live session
    identity and refuses BYPASSRLS/superuser sessions (Gate 63 path).
    Default mode leaves behavior unchanged and skips the probe.
    """
    global _engine, _SessionLocal
    settings = settings or get_api_settings()
    _engine = create_db_engine(settings)
    if settings.runtime_db_identity_enabled and validate_runtime_identity:
        try:
            validate_runtime_engine_or_raise(_engine, settings)
        except RuntimeDatabaseConfigError:
            _engine.dispose()
            _engine = None
            _SessionLocal = None
            raise
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return configure_engine()
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        configure_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_database(engine: Engine | None = None) -> bool:
    """Connectivity probe — callers must not log engine URL."""
    eng = engine or get_engine()
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
