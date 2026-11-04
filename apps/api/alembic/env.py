"""
Alembic environment — requires DATABASE_URL; does not invent credentials.

Bootstrap: CREATE SCHEMA app BEFORE Alembic tries to create app.alembic_version
on a fresh database (version_table_schema=app).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Ensure repository root is importable when Alembic is invoked from anywhere.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from apps.api.app.config import get_api_settings  # noqa: E402
from apps.api.app.database_url import APP_SCHEMA, DatabaseUrlError  # noqa: E402
from apps.api.app.models import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    settings = get_api_settings()
    try:
        return settings.sqlalchemy_url()
    except DatabaseUrlError as exc:
        raise RuntimeError(str(exc)) from None


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Limit autogenerate / reflection scope to application schema only."""
    if type_ == "schema":
        return name == APP_SCHEMA
    return True


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    if type_ == "table":
        schema = getattr(object_, "schema", None)
        if schema is not None and schema != APP_SCHEMA:
            return False
    return True


def _ensure_app_schema_sql() -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {APP_SCHEMA}"


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        version_table="alembic_version",
        version_table_schema=APP_SCHEMA,
    )
    with context.begin_transaction():
        # Emit before version table DDL in offline scripts.
        context.execute(text(_ensure_app_schema_sql()))
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_api_settings()
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()
    # Never log configuration["sqlalchemy.url"].
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=settings.engine_connect_args(),
    )
    with connectable.connect() as connection:
        # Critical bootstrap: schema must exist before app.alembic_version.
        connection.execute(text(_ensure_app_schema_sql()))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            include_object=include_object,
            version_table="alembic_version",
            version_table_schema=APP_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
