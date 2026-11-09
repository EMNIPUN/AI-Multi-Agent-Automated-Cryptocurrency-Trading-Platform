"""Guardrails for SQLite → Supabase source-of-truth cutover."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.app.config import get_api_settings
from apps.api.app.database_url import DatabaseUrlError
from apps.api.app.models import Base

_LOCAL_OWNER = "00000000-0000-0000-0000-000000000001"

_engine_lock = threading.RLock()
_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker[Session]] = {}


def supabase_sot_enabled() -> bool:
    try:
        from apps.api.app.config import get_api_settings

        return bool(get_api_settings().supabase_sot_enabled)
    except Exception:  # noqa: BLE001 — offline import without env
        return os.getenv("SUPABASE_SOT_ENABLED", "true").strip().lower() in {
            "1",
            "true",
            "yes",
        }


def assert_no_sqlite_import(source: str, *, module_name: str) -> None:
    if "import sqlite3" in source or "from sqlite3" in source:
        raise RuntimeError(f"{module_name} must not import sqlite3 under Supabase SoT")


def _sqlite_url(db_path: Path) -> str:
    resolved = db_path.resolve()
    return f"sqlite+pysqlite:///{resolved.as_posix()}"


def create_agent_engine(
    db_path: str | Path | None = None,
    *,
    pool_pre_ping: bool = True,
    isolated_sqlite: bool = False,
) -> Engine:
    """
    Process-scoped engine for agent stores.

    When SUPABASE_SOT_ENABLED (default), requires DATABASE_URL — no SQLite files.
    ``isolated_sqlite`` is only for one backtest journal. It does not change
    process environment or the engine used by paper and signal stores.
    When source-of-truth mode is disabled, optional db_path selects file-backed SQLite.
    Offline SQLite maps schema ``app`` → default via schema_translate_map.
    """
    if supabase_sot_enabled() and not isolated_sqlite:
        # db_path is ignored under SoT (Postgres is the only durable store).
        settings = get_api_settings()
        url = settings.sqlalchemy_url()
        key = f"pg:{url}"
        with _engine_lock:
            eng = _engines.get(key)
            if eng is None:
                eng = create_engine(
                    url,
                    pool_pre_ping=pool_pre_ping,
                    future=True,
                    connect_args=settings.engine_connect_args(),
                )
                _engines[key] = eng
            return eng

    if db_path is None:
        url = "sqlite+pysqlite://"
        key = "sqlite::memory:"
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = _sqlite_url(path)
        key = f"sqlite:{path.resolve()}"
    with _engine_lock:
        eng = _engines.get(key)
        if eng is None:
            raw = create_engine(url, pool_pre_ping=False, future=True)

            @event.listens_for(raw, "connect")
            def _fk_on(dbapi_conn, _connection_record):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

            eng = raw.execution_options(schema_translate_map={"app": None})
            _engines[key] = eng
        return eng


def agent_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    eng = engine or create_agent_engine()
    key = str(eng.url)
    with _engine_lock:
        sm = _sessionmakers.get(key)
        if sm is None:
            sm = sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
            _sessionmakers[key] = sm
        return sm


def upgrade_sqlite_missing_columns(engine: Engine) -> None:
    """Add ORM columns onto an existing offline SQLite file without dropping rows.

    Postgres schema changes stay in Alembic. This path is only for local files
    created before owner_user_id and the later execution columns existed.
    """
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import Boolean, Float, Integer, inspect, text
    from sqlalchemy import Uuid as SqlUuid

    from apps.api.app.models import Base

    from apps.api.app.persistence.owner import resolve_sot_owner_user_id

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    local_owner = resolve_sot_owner_user_id(required=False).hex
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {col["name"] for col in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have or col.primary_key:
                    continue
                ddl_type = "TEXT"
                default = "''"
                if isinstance(col.type, SqlUuid):
                    ddl_type = "CHAR(32)"
                    default = f"'{local_owner}'"
                elif isinstance(col.type, (Integer, Boolean)):
                    ddl_type = "INTEGER"
                    default = "0"
                elif isinstance(col.type, Float):
                    ddl_type = "REAL"
                    default = "0"
                elif col.nullable:
                    default = "NULL"
                quoted = f'"{table.name}"'
                column = f'"{col.name}"'
                if col.nullable:
                    conn.execute(text(f"ALTER TABLE {quoted} ADD COLUMN {column} {ddl_type}"))
                else:
                    conn.execute(
                        text(
                            f"ALTER TABLE {quoted} ADD COLUMN {column} {ddl_type} "
                            f"NOT NULL DEFAULT {default}"
                        )
                    )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_meta "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT OR IGNORE INTO schema_meta (key, value) "
                "VALUES ('schema_version', 'orm')"
            )
        )


def bootstrap_agent_schema(engine: Engine) -> None:
    """Create ORM tables for offline SQLite test engines (SUPABASE_SOT_ENABLED=false)."""
    if engine.dialect.name != "sqlite":
        return
    # Import side effect: register all SoT tables on Base.metadata.
    from apps.api.app.persistence import ledger_models, paper_models, signal_extra_models  # noqa: F401
    from apps.api.app.signals import cloud_models  # noqa: F401

    # Keep schema="app"; ATTACH handler in create_agent_engine makes app.* resolvable.
    Base.metadata.create_all(engine, checkfirst=True)
    upgrade_sqlite_missing_columns(engine)
