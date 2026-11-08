"""PROPOSED — Phase 4D signal / scheduler mirror tables (NOT APPLIED).

Revision ID: 20261107_0004
Revises: 20261105_0003

*** DO NOT move this file into alembic/versions/ or run alembic upgrade
    until the operator explicitly approves Phase 4D cloud DDL. ***

Creates owner-scoped signal history + contributions + risk events and
scheduler evaluation/audit mirrors. Does NOT create paper/backtest/candle
warehouses (documented as future schema only).

Does NOT enable exchange binding persistence.
Does NOT grant privileges to anon/authenticated beyond SELECT RLS pattern.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0004"
down_revision: Union[str, None] = "20261105_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("idempotent_key", sa.String(length=256), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("signal_strength", sa.Float(), nullable=False),
        sa.Column("directional_conviction", sa.Float(), nullable=False),
        sa.Column("market_quality", sa.Float(), nullable=False),
        sa.Column("risk_verdict", sa.String(length=16), nullable=False),
        sa.Column("source_mode", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("levels_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("market_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("indicators_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_id", name="uq_signal_history_decision_id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "idempotent_key",
            name="uq_signal_history_owner_idempotent",
        ),
        sa.CheckConstraint(
            "category IN ('spot', 'linear')",
            name="ck_signal_history_category",
        ),
        sa.CheckConstraint(
            "action IN ('BUY', 'SELL', 'HOLD', 'BLOCKED')",
            name="ck_signal_history_action",
        ),
        schema="app",
    )
    op.create_index(
        "ix_signal_history_owner_ts",
        "signal_history",
        ["owner_user_id", "timestamp_ms"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_signal_history_owner_symbol_tf",
        "signal_history",
        ["owner_user_id", "symbol", "interval", "timestamp_ms"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_signal_history_owner_strategy",
        "signal_history",
        ["owner_user_id", "strategy_version", "timestamp_ms"],
        unique=False,
        schema="app",
    )

    op.create_table(
        "signal_agent_contributions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=32), nullable=False),
        sa.Column("bias", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("indicators", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("timed_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["app.signal_history.id"],
            name="fk_signal_contrib_signal",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signal_id",
            "agent_id",
            name="uq_signal_contrib_signal_agent",
        ),
        schema="app",
    )
    op.create_index(
        "ix_signal_contrib_owner_decision",
        "signal_agent_contributions",
        ["owner_user_id", "decision_id"],
        unique=False,
        schema="app",
    )

    op.create_table(
        "signal_risk_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=True),
        sa.Column("decision_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["app.signal_history.id"],
            name="fk_signal_risk_signal",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_signal_risk_owner_ms",
        "signal_risk_events",
        ["owner_user_id", "event_ms"],
        unique=False,
        schema="app",
    )

    op.create_table(
        "scheduler_evaluation_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("eval_key", sa.String(length=256), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("candle_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("candle_close_ms", sa.BigInteger(), nullable=False),
        sa.Column("decision_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "eval_key",
            name="uq_sched_eval_owner_key",
        ),
        sa.CheckConstraint(
            "category IN ('spot', 'linear')",
            name="ck_sched_eval_category",
        ),
        schema="app",
    )
    op.create_index(
        "ix_sched_eval_owner_stream",
        "scheduler_evaluation_history",
        [
            "owner_user_id",
            "strategy_version",
            "category",
            "symbol",
            "interval",
            "candle_close_ms",
        ],
        unique=False,
        schema="app",
    )

    op.create_table(
        "scheduler_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("local_audit_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "local_audit_id",
            name="uq_sched_audit_owner_local",
        ),
        schema="app",
    )
    op.create_index(
        "ix_sched_audit_owner_ms",
        "scheduler_audit",
        ["owner_user_id", "created_at_ms"],
        unique=False,
        schema="app",
    )

    # RLS defense-in-depth for Supabase authenticated role (Data API).
    # FastAPI privileged role STILL bypasses RLS — application filters required.
    for table in (
        "signal_history",
        "signal_agent_contributions",
        "signal_risk_events",
        "scheduler_evaluation_history",
        "scheduler_audit",
    ):
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_select_own
            ON app.{table}
            FOR SELECT
            TO authenticated
            USING (owner_user_id = auth.uid())
            """
        )


def downgrade() -> None:
    for table in (
        "scheduler_audit",
        "scheduler_evaluation_history",
        "signal_risk_events",
        "signal_agent_contributions",
        "signal_history",
    ):
        op.execute(f"DROP POLICY IF EXISTS {table}_select_own ON app.{table}")
        op.drop_table(table, schema="app")
