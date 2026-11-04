"""Initial app schema: agent_decisions, system_events, strategy_configs.

Revision ID: 20261104_0001
Revises:
Create Date: 2026-11-04

These tables are observational / configuration only.
They are NOT an authoritative order or risk ledger (see Phase 1 SQLite stores).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261104_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: alembic/env.py also ensures schema `app` exists *before*
    # creating app.alembic_version on a fresh database.
    op.execute("CREATE SCHEMA IF NOT EXISTS app")

    op.create_table(
        "agent_decisions",
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
        sa.Column("env_scope", sa.String(length=64), nullable=False),
        sa.Column("account_fp", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_agent_decisions_env_created",
        "agent_decisions",
        ["env_scope", "created_at"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_agent_decisions_symbol_created",
        "agent_decisions",
        ["symbol", "created_at"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_agent_decisions_signal_id",
        "agent_decisions",
        ["signal_id"],
        unique=False,
        schema="app",
    )

    op.create_table(
        "system_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("env_scope", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_system_events_env_created",
        "system_events",
        ["env_scope", "created_at"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_system_events_type_created",
        "system_events",
        ["event_type", "created_at"],
        unique=False,
        schema="app",
    )

    op.create_table(
        "strategy_configs",
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
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_strategy_configs_name",
        "strategy_configs",
        ["name"],
        unique=True,
        schema="app",
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_configs_name", table_name="strategy_configs", schema="app")
    op.drop_table("strategy_configs", schema="app")
    op.drop_index("ix_system_events_type_created", table_name="system_events", schema="app")
    op.drop_index("ix_system_events_env_created", table_name="system_events", schema="app")
    op.drop_table("system_events", schema="app")
    op.drop_index("ix_agent_decisions_signal_id", table_name="agent_decisions", schema="app")
    op.drop_index(
        "ix_agent_decisions_symbol_created", table_name="agent_decisions", schema="app"
    )
    op.drop_index(
        "ix_agent_decisions_env_created", table_name="agent_decisions", schema="app"
    )
    op.drop_table("agent_decisions", schema="app")
    # Leave schema `app` in place (may hold alembic_version); drop only if empty ops desire.
    # Explicit: do not DROP SCHEMA CASCADE — safer for shared Supabase projects.
