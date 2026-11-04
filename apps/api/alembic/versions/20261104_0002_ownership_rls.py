"""Add owner_user_id + RLS (defense in depth) for app catalog tables.

Revision ID: 20261104_0002
Revises: 20261104_0001
Create Date: 2026-11-04

- owner_user_id is nullable: existing rows stay unowned and API-inaccessible.
- Does not invent owners for legacy rows.
- RLS policies target role ``authenticated`` (Data API / future least-privilege).
- Table owner / postgres still bypasses RLS unless FORCE — FastAPI MUST filter by
  principal.user_id regardless (application authorization is primary).
- Does not GRANT schema USAGE to anon/authenticated.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261104_0002"
down_revision: Union[str, None] = "20261104_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_decisions",
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        schema="app",
    )
    op.add_column(
        "system_events",
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        schema="app",
    )
    op.add_column(
        "strategy_configs",
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        schema="app",
    )

    op.create_index(
        "ix_agent_decisions_owner_created",
        "agent_decisions",
        ["owner_user_id", "created_at"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_system_events_owner_created",
        "system_events",
        ["owner_user_id", "created_at"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_strategy_configs_owner_created",
        "strategy_configs",
        ["owner_user_id", "created_at"],
        unique=False,
        schema="app",
    )

    # Replace global unique name with per-owner unique (owned rows only).
    op.drop_index("ix_strategy_configs_name", table_name="strategy_configs", schema="app")
    op.execute(
        """
        CREATE UNIQUE INDEX ix_strategy_configs_owner_name
        ON app.strategy_configs (owner_user_id, name)
        WHERE owner_user_id IS NOT NULL
        """
    )

    # RLS: defense in depth for non-owner roles. No broad GRANTs here.
    op.execute("ALTER TABLE app.agent_decisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.system_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.strategy_configs ENABLE ROW LEVEL SECURITY")

    # Policies only if Supabase `authenticated` role exists.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE $p$
              CREATE POLICY agent_decisions_select_own
              ON app.agent_decisions
              FOR SELECT
              TO authenticated
              USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())
            $p$;
            EXECUTE $p$
              CREATE POLICY system_events_select_own
              ON app.system_events
              FOR SELECT
              TO authenticated
              USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())
            $p$;
            EXECUTE $p$
              CREATE POLICY strategy_configs_select_own
              ON app.strategy_configs
              FOR SELECT
              TO authenticated
              USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())
            $p$;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE 'DROP POLICY IF EXISTS agent_decisions_select_own ON app.agent_decisions';
            EXECUTE 'DROP POLICY IF EXISTS system_events_select_own ON app.system_events';
            EXECUTE 'DROP POLICY IF EXISTS strategy_configs_select_own ON app.strategy_configs';
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE app.strategy_configs DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.system_events DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.agent_decisions DISABLE ROW LEVEL SECURITY")

    op.execute("DROP INDEX IF EXISTS app.ix_strategy_configs_owner_name")
    op.create_index(
        "ix_strategy_configs_name",
        "strategy_configs",
        ["name"],
        unique=True,
        schema="app",
    )

    op.drop_index(
        "ix_strategy_configs_owner_created",
        table_name="strategy_configs",
        schema="app",
    )
    op.drop_index(
        "ix_system_events_owner_created", table_name="system_events", schema="app"
    )
    op.drop_index(
        "ix_agent_decisions_owner_created", table_name="agent_decisions", schema="app"
    )

    op.drop_column("strategy_configs", "owner_user_id", schema="app")
    op.drop_column("system_events", "owner_user_id", schema="app")
    op.drop_column("agent_decisions", "owner_user_id", schema="app")
