"""
Read-only Supabase pre-flight for Phase 2B.

- No DDL / DML writes
- No Alembic upgrade/downgrade/stamp
- Prints redacted identity only (never raw DATABASE_URL / password)
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.config import clear_settings_cache, get_api_settings  # noqa: E402
from apps.api.app.db import reset_engine  # noqa: E402
from apps.api.app.migration_audit import audit_initial_migration  # noqa: E402

EXPECTED_TABLES = {
    "alembic_version",
    "agent_decisions",
    "system_events",
    "strategy_configs",
}
TARGET_REVISION = "20261104_0001"


def main() -> int:
    clear_settings_cache()
    reset_engine()
    settings = get_api_settings()

    if not settings.database_configured:
        print("RESULT=NOT_READY")
        print("reason=DATABASE_URL_not_configured")
        return 2

    info = settings.database_url_info()
    print("database_configured=True")
    print(f"redacted_url={info.redacted_url}")
    print(f"host={info.host}")
    print(f"port={info.port}")
    print(f"database_name={info.database}")
    print(f"user={info.user}")
    print(f"is_remote={info.is_remote}")
    print(f"is_supabase_like={info.is_supabase_like}")
    print(f"pooler_hint={info.pooler_hint}")
    print(f"sslmode={info.sslmode}")

    migrate_conn_ok = info.port == 5432 and info.pooler_hint in {
        "direct",
        "session_pooler",
        "unknown",
    }
    # unknown + 5432 on supabase host often still session/direct
    if info.port == 5432 and info.is_supabase_like:
        migrate_conn_ok = info.pooler_hint != "transaction_pooler"
    print(f"migrate_connection_mode_ok={migrate_conn_ok}")
    print(f"tls_required_flag={settings.database_ssl_require}")
    print(f"tls_effective={info.sslmode == 'require' or not info.is_remote}")

    engine = create_engine(
        settings.sqlalchemy_url(),
        pool_pre_ping=True,
        future=True,
        connect_args=settings.engine_connect_args(),
    )

    try:
        with engine.connect() as conn:
            # Read-only session best-effort (may be ignored by pooler)
            try:
                conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
            except Exception:
                pass

            row = conn.execute(
                text(
                    "SELECT current_database() AS db, current_user AS usr, "
                    "inet_server_addr()::text AS addr, current_setting('transaction_read_only') AS ro"
                )
            ).mappings().one()
            print(f"current_database={row['db']}")
            print(f"current_user={row['usr']}")
            print(f"server_addr={row['addr']}")
            print(f"transaction_read_only={row['ro']}")
            print("connectivity=CONNECT_SUCCESS")

            schema_exists = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = 'app')")
            ).scalar()
            print(f"schema_app_exists={bool(schema_exists)}")

            tables = set(
                conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'app'"
                    )
                ).scalars().all()
            )
            print(f"app_tables={sorted(tables)}")
            print(f"has_alembic_version={'alembic_version' in tables}")
            print(f"has_agent_decisions={'agent_decisions' in tables}")
            print(f"has_system_events={'system_events' in tables}")
            print(f"has_strategy_configs={'strategy_configs' in tables}")

            version = None
            if "alembic_version" in tables:
                version = conn.execute(
                    text("SELECT version_num FROM app.alembic_version LIMIT 1")
                ).scalar()
            print(f"alembic_version={version!s}")

            if version == TARGET_REVISION:
                migration_state = "already_applied"
            elif version is None and not tables:
                migration_state = "pending_fresh"
            elif version is None and tables:
                migration_state = "partial_or_manual_objects"
            else:
                migration_state = f"other_revision:{version}"
            print(f"migration_state={migration_state}")
            print(f"migration_required={migration_state != 'already_applied'}")

            # Data API exposure cannot be fully proven from SQL alone.
            print("data_api_exposure=REQUIRES_OPERATOR_DASHBOARD_CONFIRMATION")
            print(
                "data_api_note=Confirm Settings > API > Exposed schemas does not include app"
            )

            # Soft signal: privileges for anon on app (informative only)
            try:
                anon_usage = conn.execute(
                    text(
                        "SELECT has_schema_privilege('anon', 'app', 'USAGE') "
                        "WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')"
                    )
                ).scalar()
                print(f"anon_has_usage_on_app={anon_usage}")
            except Exception as exc:  # noqa: BLE001
                print(f"anon_privilege_check=unavailable:{type(exc).__name__}")

        audit = audit_initial_migration()
        print(f"migration_targets_app_only_audit_ok={audit.ok}")
        if audit.issues:
            print(f"migration_audit_issues={audit.issues}")

        blockers: list[str] = []
        if not info.is_supabase_like and info.is_remote:
            blockers.append("host_not_recognized_as_supabase_like")
        if not migrate_conn_ok:
            blockers.append("use_direct_or_session_port_5432_not_transaction_6543")
        if info.sslmode != "require" and info.is_remote:
            blockers.append("sslmode_not_require")
        if migration_state == "partial_or_manual_objects":
            blockers.append("unexpected_app_objects_without_alembic_version")
        if migration_state.startswith("other_revision:"):
            blockers.append("unexpected_alembic_revision")
        if not audit.ok:
            blockers.append("migration_audit_failed")
        blockers.append("operator_must_confirm_app_not_in_exposed_schemas")
        if migration_state == "already_applied":
            # Still need dashboard confirmation, but migrate not required
            pass

        ready = (
            migrate_conn_ok
            and (info.sslmode == "require" or not info.is_remote)
            and audit.ok
            and migration_state in {"pending_fresh", "already_applied"}
            and info.is_supabase_like
        )
        # Dashboard confirmation is always a remaining checklist item, but
        # READY means technical preflight passed for an approved migrate.
        print(f"blockers={blockers}")
        if ready and migration_state == "already_applied":
            print("RESULT=READY_NO_MIGRATE_NEEDED")
            print("recommendation=Migration already at 20261104_0001; skip upgrade head")
        elif ready and migration_state == "pending_fresh":
            print("RESULT=READY")
            print(
                "recommendation=READY for operator-approved alembic upgrade head "
                "after dashboard Exposed-schemas confirmation"
            )
        else:
            print("RESULT=NOT_READY")
            print("recommendation=NOT READY — resolve blockers before migrate")
        return 0 if ready else 3
    except Exception as exc:  # noqa: BLE001 — never include URL/password in message
        print(f"connectivity=CONNECT_FAILED error={type(exc).__name__}")
        print("RESULT=NOT_READY")
        print("recommendation=NOT READY — fix connectivity (and ensure .env URL is active)")
        return 4
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
