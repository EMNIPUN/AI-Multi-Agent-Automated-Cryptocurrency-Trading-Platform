"""PENDING APPROVAL — Option A least-privilege roles + write RLS policies.

Revision ID: 20261108_0005
Revises: 20261107_0004

*** THIS FILE LIVES IN versions_proposed/ — NOT ACTIVE ALEMBIC PATH. ***
*** DO NOT move to alembic/versions/ or run alembic upgrade until a
    separate Option A remote security-change gate is explicitly approved. ***

Design notes (validated on disposable local PostgreSQL 18):
- Base role uses INHERIT so LOGIN members receive GRANTs without SET ROLE.
- LOGIN wrappers MUST be created with INHERIT (PostgreSQL default) and
  `IN ROLE cryptonova_api_runtime`. A NOINHERIT login will not receive grants.
- Policies target the base role; inheriting members are subject to them.
- Scheduler tables: SELECT only for runtime until Gate D authorizes writes.
- No DELETE for runtime.
- auth.uid() privilege: GRANT EXECUTE if required on target (Supabase usually has it).
- Table ownership must remain non-runtime (do not REASSIGN OWNED to runtime).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261108_0005"
down_revision: Union[str, None] = "20261107_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RUNTIME = "cryptonova_api_runtime"
_MIGRATOR = "cryptonova_migrator"

# Writable now (Gate C2+ readiness under dual app gates).
_SIGNAL_WRITE_TABLES = (
    "signal_history",
    "signal_agent_contributions",
    "signal_risk_events",
)

# Deferred writes until Gate D / scheduler sync approval.
_SCHEDULER_READ_TABLES = (
    "scheduler_evaluation_history",
    "scheduler_audit",
)

_CATALOG_READ_TABLES = (
    "agent_decisions",
    "system_events",
    "strategy_configs",
    "exchange_account_bindings",
)


def _create_policy_if_absent(table: str, name: str, body: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'app' AND tablename = '{table}' AND policyname = '{name}'
          ) THEN
            EXECUTE $p${body}$p$;
          END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    # Roles — passwords / LOGIN wrappers are operator-managed (never embed secrets).
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_RUNTIME}') THEN
            CREATE ROLE {_RUNTIME}
              NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_MIGRATOR}') THEN
            CREATE ROLE {_MIGRATOR}
              NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS INHERIT;
          END IF;
        END
        $$;
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA app TO {_RUNTIME}")
    op.execute(f"GRANT USAGE ON SCHEMA app TO {_MIGRATOR}")
    # Needed so runtime can resolve auth.uid() used by policies.
    op.execute(f"GRANT USAGE ON SCHEMA auth TO {_RUNTIME}")
    op.execute(f"GRANT EXECUTE ON FUNCTION auth.uid() TO {_RUNTIME}")

    for table in _SIGNAL_WRITE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE app.{table} TO {_RUNTIME}")
        _create_policy_if_absent(
            table,
            f"{table}_runtime_select_own",
            f"""
            CREATE POLICY {table}_runtime_select_own
            ON app.{table}
            FOR SELECT TO {_RUNTIME}
            USING (owner_user_id = auth.uid())
            """,
        )
        _create_policy_if_absent(
            table,
            f"{table}_runtime_insert_own",
            f"""
            CREATE POLICY {table}_runtime_insert_own
            ON app.{table}
            FOR INSERT TO {_RUNTIME}
            WITH CHECK (owner_user_id = auth.uid())
            """,
        )
        _create_policy_if_absent(
            table,
            f"{table}_runtime_update_own",
            f"""
            CREATE POLICY {table}_runtime_update_own
            ON app.{table}
            FOR UPDATE TO {_RUNTIME}
            USING (owner_user_id = auth.uid())
            WITH CHECK (owner_user_id = auth.uid())
            """,
        )

    for table in _SCHEDULER_READ_TABLES:
        op.execute(f"GRANT SELECT ON TABLE app.{table} TO {_RUNTIME}")
        _create_policy_if_absent(
            table,
            f"{table}_runtime_select_own",
            f"""
            CREATE POLICY {table}_runtime_select_own
            ON app.{table}
            FOR SELECT TO {_RUNTIME}
            USING (owner_user_id = auth.uid())
            """,
        )

    for table in _CATALOG_READ_TABLES:
        op.execute(f"GRANT SELECT ON TABLE app.{table} TO {_RUNTIME}")
        using = (
            "(owner_user_id IS NOT NULL AND owner_user_id = auth.uid())"
            if table != "exchange_account_bindings"
            else "(owner_user_id = auth.uid() AND status = 'active')"
        )
        _create_policy_if_absent(
            table,
            f"{table}_runtime_select_own",
            f"""
            CREATE POLICY {table}_runtime_select_own
            ON app.{table}
            FOR SELECT TO {_RUNTIME}
            USING {using}
            """,
        )

    # Migrator: DML for data migrations + CREATE on schema for future DDL revisions.
    # Still never wire this role into FastAPI DATABASE_URL.
    op.execute(f"GRANT CREATE ON SCHEMA app TO {_MIGRATOR}")
    all_app = _SIGNAL_WRITE_TABLES + _SCHEDULER_READ_TABLES + _CATALOG_READ_TABLES
    for table in all_app:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE app.{table} TO {_MIGRATOR}"
        )


def downgrade() -> None:
    for table in _SIGNAL_WRITE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_runtime_select_own ON app.{table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_runtime_insert_own ON app.{table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_runtime_update_own ON app.{table}")
        op.execute(f"REVOKE ALL ON TABLE app.{table} FROM {_RUNTIME}")
    for table in _SCHEDULER_READ_TABLES + _CATALOG_READ_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_runtime_select_own ON app.{table}")
        op.execute(f"REVOKE ALL ON TABLE app.{table} FROM {_RUNTIME}")
    for table in _SIGNAL_WRITE_TABLES + _SCHEDULER_READ_TABLES + _CATALOG_READ_TABLES:
        op.execute(f"REVOKE ALL ON TABLE app.{table} FROM {_MIGRATOR}")
    op.execute(f"REVOKE CREATE ON SCHEMA app FROM {_MIGRATOR}")
    op.execute(f"REVOKE USAGE ON SCHEMA app FROM {_RUNTIME}")
    op.execute(f"REVOKE USAGE ON SCHEMA app FROM {_MIGRATOR}")
    op.execute(f"REVOKE USAGE ON SCHEMA auth FROM {_RUNTIME}")
    # DROP ROLE intentionally omitted — operator dependency audit required.
