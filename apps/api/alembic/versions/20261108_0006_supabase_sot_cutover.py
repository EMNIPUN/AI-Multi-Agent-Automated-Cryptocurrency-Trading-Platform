"""Supabase SoT cutover — paper broker, ledgers, scheduler aux tables.

Revision ID: 20261108_0006
Revises: 20261108_0005
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0006"
down_revision: Union[str, None] = "20261108_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_TABLES = (
    "signal_day_risk_state",
    "scheduler_lock",
    "paper_meta",
    "paper_sessions",
    "paper_orders",
    "paper_fills",
    "paper_positions",
    "paper_account_events",
    "paper_candle_cursor",
    "paper_processed_events",
    "paper_risk_state",
    "paper_equity_snapshots",
    "order_intents",
    "order_executions",
    "account_risk_snapshots",
    "signal_ledger_entries",
    "automation_exec_intents",
    "automation_exec_events",
    "observation_events",
)


def _rls_select_own(table: str) -> None:
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


def upgrade() -> None:
    op.create_table(
        "signal_day_risk_state",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("day_key", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("hypothetical_day_pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_signal_key", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("last_signal_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("seen_keys_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("corrupt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.PrimaryKeyConstraint("owner_user_id"),
        schema="app",
    )

    op.create_table(
        "scheduler_lock",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("lease_until_ms", sa.BigInteger(), nullable=False),
        sa.Column("hostname", sa.String(length=128), nullable=False),
        sa.Column("pid", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("owner_user_id"),
        schema="app",
    )

    op.create_table(
        "paper_meta",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "key", name="uq_paper_meta_owner_key"),
        schema="app",
    )

    op.create_table(
        "paper_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("initial_balance", sa.Text(), nullable=False),
        sa.Column("available_balance", sa.Text(), nullable=False),
        sa.Column("reserved_capital", sa.Text(), nullable=False),
        sa.Column("realized_pnl", sa.Text(), nullable=False),
        sa.Column("fees_paid", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_ms", sa.BigInteger(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="USDT"),
        sa.PrimaryKeyConstraint("session_id"),
        schema="app",
    )
    op.create_index(
        "ix_paper_sessions_owner_updated",
        "paper_sessions",
        ["owner_user_id", "updated_ms"],
        schema="app",
    )

    op.create_table(
        "paper_orders",
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("source_signal_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("intended_entry_price", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_ms", sa.BigInteger(), nullable=False),
        sa.Column("filled_ms", sa.BigInteger(), nullable=True),
        sa.Column("fill_price", sa.Text(), nullable=True),
        sa.Column("fee", sa.Text(), nullable=False, server_default="0"),
        sa.Column("slippage", sa.Text(), nullable=False, server_default="0"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("stop_loss", sa.Text(), nullable=True),
        sa.Column("take_profit", sa.Text(), nullable=True),
        sa.Column("signal_candle_start_ms", sa.BigInteger(), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["session_id"], ["app.paper_sessions.session_id"]),
        sa.PrimaryKeyConstraint("order_id"),
        sa.UniqueConstraint(
            "session_id", "source_signal_id", "side", name="uq_paper_orders_session_signal_side"
        ),
        schema="app",
    )
    op.create_index(
        "ix_paper_orders_session_status",
        "paper_orders",
        ["session_id", "status"],
        schema="app",
    )

    op.create_table(
        "paper_fills",
        sa.Column("fill_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("price", sa.Text(), nullable=False),
        sa.Column("fee", sa.Text(), nullable=False),
        sa.Column("slippage", sa.Text(), nullable=False),
        sa.Column("filled_ms", sa.BigInteger(), nullable=False),
        sa.Column("candle_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["app.paper_orders.order_id"]),
        sa.ForeignKeyConstraint(["session_id"], ["app.paper_sessions.session_id"]),
        sa.PrimaryKeyConstraint("fill_id"),
        sa.UniqueConstraint("order_id", "role", name="uq_paper_fills_order_role"),
        sa.UniqueConstraint(
            "session_id", "order_id", "candle_start_ms", "role", name="uq_paper_fills_session"
        ),
        schema="app",
    )

    op.create_table(
        "paper_positions",
        sa.Column("position_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=False),
        sa.Column("entry_price", sa.Text(), nullable=False),
        sa.Column("entry_fee", sa.Text(), nullable=False),
        sa.Column("entry_order_id", sa.String(length=64), nullable=False),
        sa.Column("entry_signal_id", sa.String(length=128), nullable=False),
        sa.Column("stop_loss", sa.Text(), nullable=True),
        sa.Column("take_profit", sa.Text(), nullable=True),
        sa.Column("opened_ms", sa.BigInteger(), nullable=False),
        sa.Column("closed_ms", sa.BigInteger(), nullable=True),
        sa.Column("exit_price", sa.Text(), nullable=True),
        sa.Column("exit_fee", sa.Text(), nullable=False, server_default="0"),
        sa.Column("exit_order_id", sa.String(length=64), nullable=True),
        sa.Column("exit_reason", sa.Text(), nullable=True),
        sa.Column("realized_pnl", sa.Text(), nullable=False, server_default="0"),
        sa.Column("mark_price", sa.Text(), nullable=True),
        sa.Column("unrealized_pnl", sa.Text(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["session_id"], ["app.paper_sessions.session_id"]),
        sa.PrimaryKeyConstraint("position_id"),
        sa.UniqueConstraint(
            "session_id", "entry_signal_id", name="uq_paper_positions_session_signal"
        ),
        schema="app",
    )
    op.create_index(
        "ix_paper_positions_open",
        "paper_positions",
        ["session_id", "status", "symbol"],
        schema="app",
    )

    op.create_table(
        "paper_account_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_ms", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["app.paper_sessions.session_id"]),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_paper_events_idem"),
        schema="app",
    )

    op.create_table(
        "paper_candle_cursor",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("last_candle_start_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "session_id", "symbol", "interval"),
        schema="app",
    )

    op.create_table(
        "paper_processed_events",
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=256), nullable=False),
        sa.Column("created_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("owner_user_id", "session_id", "event_key"),
        schema="app",
    )

    op.create_table(
        "paper_risk_state",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("halted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("halt_reason", sa.Text(), nullable=True),
        sa.Column("halt_ms", sa.BigInteger(), nullable=True),
        sa.Column("peak_marked_equity", sa.Text(), nullable=True),
        sa.Column("day_key", sa.String(length=32), nullable=True),
        sa.Column("day_start_equity", sa.Text(), nullable=True),
        sa.Column("updated_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["app.paper_sessions.session_id"]),
        sa.PrimaryKeyConstraint("session_id"),
        schema="app",
    )

    op.create_table(
        "paper_equity_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("as_of_ms", sa.BigInteger(), nullable=False),
        sa.Column("available_balance", sa.Text(), nullable=False),
        sa.Column("reserved_capital", sa.Text(), nullable=False),
        sa.Column("realized_pnl", sa.Text(), nullable=False),
        sa.Column("unrealized_pnl", sa.Text(), nullable=True),
        sa.Column("marked_equity", sa.Text(), nullable=True),
        sa.Column("valuation_status", sa.String(length=32), nullable=False),
        sa.Column("open_position_count", sa.Integer(), nullable=False),
        sa.Column("gross_exposure", sa.Text(), nullable=False),
        sa.Column("day_key", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["app.paper_sessions.session_id"]),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint("session_id", "as_of_ms", name="uq_paper_equity_session_asof"),
        schema="app",
    )
    op.create_index(
        "ix_paper_equity_session",
        "paper_equity_snapshots",
        ["session_id", "as_of_ms"],
        schema="app",
    )

    op.create_table(
        "order_intents",
        sa.Column("intent_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("env_scope", sa.String(length=32), nullable=False),
        sa.Column("account_fp", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Text(), nullable=False),
        sa.Column("reduce_only", sa.Boolean(), nullable=False),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=False),
        sa.Column("take_profit", sa.Text(), nullable=True),
        sa.Column("stop_loss", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("risk_auth_ref", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=64), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("exchange_order_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("filled_qty", sa.Text(), nullable=False, server_default=""),
        sa.Column("remaining_qty", sa.Text(), nullable=False, server_default=""),
        sa.Column("avg_exec_price", sa.Text(), nullable=False, server_default=""),
        sa.Column("cum_fee", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_status", sa.Text(), nullable=False, server_default=""),
        sa.Column("submission_attempted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("intent_id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "env_scope",
            "account_fp",
            "client_order_id",
            name="uq_order_intents_owner_client",
        ),
        schema="app",
    )
    op.create_index(
        "ix_order_intents_owner_state",
        "order_intents",
        ["owner_user_id", "env_scope", "account_fp", "state"],
        schema="app",
    )

    op.create_table(
        "order_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("env_scope", sa.String(length=32), nullable=False),
        sa.Column("account_fp", sa.String(length=128), nullable=False),
        sa.Column("intent_id", sa.String(length=64), nullable=False),
        sa.Column("exec_id", sa.String(length=128), nullable=False),
        sa.Column("order_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("order_link_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("exec_qty", sa.Text(), nullable=False),
        sa.Column("exec_price", sa.Text(), nullable=False),
        sa.Column("exec_fee", sa.Text(), nullable=False, server_default=""),
        sa.Column("fee_currency", sa.Text(), nullable=False, server_default=""),
        sa.Column("exec_time_ms", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_maker", sa.Boolean(), nullable=True),
        sa.Column("leaves_qty", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["intent_id"], ["app.order_intents.intent_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id", "env_scope", "account_fp", "exec_id", name="uq_order_exec"
        ),
        schema="app",
    )
    op.create_index(
        "ix_order_executions_intent", "order_executions", ["intent_id"], schema="app"
    )

    op.create_table(
        "account_risk_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("env_scope", sa.String(length=32), nullable=False),
        sa.Column("account_fp", sa.String(length=128), nullable=False),
        sa.Column("risk_date", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("start_equity", sa.Float(), nullable=True),
        sa.Column("latest_equity", sa.Float(), nullable=True),
        sa.Column("equity_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("unrealized_pnl", sa.Float(), nullable=True),
        sa.Column("daily_loss_pct_threshold", sa.Float(), nullable=False),
        sa.Column("daily_loss_pct_current", sa.Float(), nullable=True),
        sa.Column("emergency_halt", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("halt_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("recovery_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "env_scope",
            "account_fp",
            "risk_date",
            name="uq_account_risk_owner_day",
        ),
        schema="app",
    )
    op.create_index(
        "ix_account_risk_updated",
        "account_risk_snapshots",
        ["owner_user_id", "env_scope", "account_fp", "updated_at"],
        schema="app",
    )

    op.create_table(
        "signal_ledger_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("env_scope", sa.String(length=32), nullable=False),
        sa.Column("account_fp", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("candle_close_ms", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "env_scope",
            "account_fp",
            "signal_id",
            name="uq_signal_ledger_entry",
        ),
        schema="app",
    )
    op.create_index(
        "ix_signal_ledger_symbol_close",
        "signal_ledger_entries",
        [
            "owner_user_id",
            "env_scope",
            "account_fp",
            "symbol",
            "category",
            "interval",
            "candle_close_ms",
        ],
        schema="app",
    )

    op.create_table(
        "automation_exec_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("decision_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("exchange_order_id", sa.Text(), nullable=True),
        sa.Column("stop_loss", sa.Text(), nullable=True),
        sa.Column("take_profit", sa.Text(), nullable=True),
        sa.Column("protection_state", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "intent_id", name="uq_auto_exec_intent"),
        sa.UniqueConstraint("owner_user_id", "client_order_id", name="uq_auto_exec_client"),
        schema="app",
    )
    op.create_index(
        "ix_auto_exec_intents_state",
        "automation_exec_intents",
        ["owner_user_id", "state", "updated_at_ms"],
        schema="app",
    )

    op.create_table(
        "automation_exec_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_auto_exec_events_intent",
        "automation_exec_events",
        ["owner_user_id", "intent_id", "created_at_ms"],
        schema="app",
    )

    op.create_table(
        "observation_events",
        sa.Column("seq", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("env_scope", sa.String(length=32), nullable=False),
        sa.Column("account_scope_label", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("interval", sa.String(length=8), nullable=True),
        sa.Column("execution_mode", sa.String(length=32), nullable=False),
        sa.Column("pipeline_step", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("owner_user_id", "event_id", name="uq_observation_event_id"),
        schema="app",
    )
    op.create_index(
        "ix_observation_owner_seq",
        "observation_events",
        ["owner_user_id", "seq"],
        schema="app",
    )

    for table in _TENANT_TABLES:
        _rls_select_own(table)


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_select_own ON app.{table}")
        op.drop_table(table, schema="app")
