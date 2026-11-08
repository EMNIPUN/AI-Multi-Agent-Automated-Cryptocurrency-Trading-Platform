"""Shared SQLAlchemy models and guards for Supabase SoT persistence."""

from apps.api.app.persistence.owner import require_sot_owner_user_id, resolve_sot_owner_user_id
from apps.api.app.persistence.sqlite_guard import (
    assert_no_sqlite_import,
    bootstrap_agent_schema,
    create_agent_engine,
    supabase_sot_enabled,
)

__all__ = [
    "assert_no_sqlite_import",
    "bootstrap_agent_schema",
    "create_agent_engine",
    "require_sot_owner_user_id",
    "resolve_sot_owner_user_id",
    "supabase_sot_enabled",
]
