"""Add app.exchange_account_bindings for verified user↔exchange ownership.

Revision ID: 20261105_0003
Revises: 20261104_0002
Create Date: 2026-11-05

Phase 3C Part 1 — DO NOT auto-apply. Operator-approved upgrade only.

- Separate from 0002 catalog owner_user_id columns.
- Does not store raw Bybit API keys (credential_ref is opaque).
- Does not auto-assign the operator account to every authenticated user.
- RLS is defense in depth; FastAPI ownership checks remain primary.
- No GRANT of schema USAGE to anon/authenticated.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0003"
down_revision: Union[str, None] = "20261104_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exchange_account_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("display_label", sa.String(length=128), nullable=False),
        sa.Column("credential_ref", sa.String(length=128), nullable=False),
        sa.Column("telemetry_scope_id", sa.String(length=64), nullable=False),
        sa.Column("enrollment_attestation", sa.Text(), nullable=False),
        sa.Column("enrolled_by_operator", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "provider = 'bybit'",
            name="ck_exchange_bindings_provider_bybit",
        ),
        sa.CheckConstraint(
            "environment IN ('testnet', 'mainnet', 'demo')",
            name="ck_exchange_bindings_environment",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'revoked', 'error')",
            name="ck_exchange_bindings_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_exchange_bindings_owner_provider_env",
        "exchange_account_bindings",
        ["owner_user_id", "provider", "environment"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_exchange_bindings_telemetry_scope",
        "exchange_account_bindings",
        ["telemetry_scope_id"],
        unique=True,
        schema="app",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_exchange_bindings_active_cred
        ON app.exchange_account_bindings (provider, credential_ref)
        WHERE status = 'active'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_exchange_bindings_owner_active_env
        ON app.exchange_account_bindings (owner_user_id, provider, environment)
        WHERE status = 'active'
        """
    )

    op.execute("ALTER TABLE app.exchange_account_bindings ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY exchange_account_bindings_select_own
          ON app.exchange_account_bindings
          FOR SELECT
          TO authenticated
          USING (owner_user_id = auth.uid() AND status = 'active')
        """
    )
    # No INSERT/UPDATE/DELETE policies for authenticated — enrollment is operator-only.


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS exchange_account_bindings_select_own "
        "ON app.exchange_account_bindings"
    )
    op.execute("ALTER TABLE app.exchange_account_bindings DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS app.ix_exchange_bindings_owner_active_env")
    op.execute("DROP INDEX IF EXISTS app.ix_exchange_bindings_active_cred")
    op.drop_index(
        "ix_exchange_bindings_telemetry_scope",
        table_name="exchange_account_bindings",
        schema="app",
    )
    op.drop_index(
        "ix_exchange_bindings_owner_provider_env",
        table_name="exchange_account_bindings",
        schema="app",
    )
    op.drop_table("exchange_account_bindings", schema="app")
