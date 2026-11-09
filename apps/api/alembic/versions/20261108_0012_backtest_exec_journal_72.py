"""Backtest execution journal. Not applied.

Revises 20261108_0011. Prompt 74 replaced fill uniqueness
(run_id, order_id, filled_at_ms) with (run_id, order_id, fill_seq).
Apply needs a fresh operator approval of this exact file.
Does not alter paper_sessions or existing news rows.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0012"
down_revision: Union[str, None] = "20261108_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "backtest_exec_runs",
    "backtest_exec_orders",
    "backtest_exec_fills",
    "backtest_exec_positions",
    "backtest_exec_equity",
    "backtest_exec_risk",
)


def _rls(table: str) -> None:
    op.execute(f'ALTER TABLE app."{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE app."{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY {table}_select_own
        ON app."{table}"
        FOR SELECT
        TO authenticated
        USING (owner_user_id = auth.uid())
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_insert_own
        ON app."{table}"
        FOR INSERT
        TO authenticated
        WITH CHECK (owner_user_id = auth.uid())
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_update_own
        ON app."{table}"
        FOR UPDATE
        TO authenticated
        USING (owner_user_id = auth.uid())
        WITH CHECK (owner_user_id = auth.uid())
        """
    )


def upgrade() -> None:
    op.create_table(
        "backtest_exec_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        schema="app",
    )
    op.create_table(
        "backtest_exec_orders",
        sa.Column("order_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["app.backtest_exec_runs.run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_backtest_exec_orders_idem"),
        schema="app",
    )
    op.create_table(
        "backtest_exec_fills",
        sa.Column("fill_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("fill_seq", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(28, 12), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("fee", sa.Numeric(28, 12), nullable=False),
        sa.Column("slippage", sa.Numeric(28, 12), nullable=False),
        sa.Column("filled_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["app.backtest_exec_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["order_id"], ["app.backtest_exec_orders.order_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", "order_id", "fill_seq", name="uq_backtest_exec_fills_seq"),
        sa.CheckConstraint("fill_seq >= 1", name="ck_backtest_exec_fills_seq"),
        schema="app",
    )
    op.create_table(
        "backtest_exec_equity",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("at_ms", sa.BigInteger(), nullable=False),
        sa.Column("equity", sa.Numeric(28, 12), nullable=False),
        sa.Column("cash", sa.Numeric(28, 12), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["app.backtest_exec_runs.run_id"], ondelete="CASCADE"),
        schema="app",
    )
    op.create_table(
        "backtest_exec_positions",
        sa.Column("position_id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("avg_price", sa.Numeric(28, 12), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["app.backtest_exec_runs.run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "symbol", name="uq_backtest_exec_positions_symbol"),
        schema="app",
    )
    op.create_table(
        "backtest_exec_risk",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("halted", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["app.backtest_exec_runs.run_id"], ondelete="CASCADE"),
        schema="app",
    )
    op.create_index("ix_backtest_exec_orders_run", "backtest_exec_orders", ["run_id"], schema="app")
    op.create_index("ix_backtest_exec_fills_run", "backtest_exec_fills", ["run_id"], schema="app")
    op.create_index(
        "ix_backtest_exec_fills_order_seq",
        "backtest_exec_fills",
        ["run_id", "order_id", "fill_seq"],
        schema="app",
    )
    op.create_index("ix_backtest_exec_equity_run", "backtest_exec_equity", ["run_id"], schema="app")
    for table in _TABLES:
        _rls(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f'DROP POLICY IF EXISTS {table}_update_own ON app."{table}"')
        op.execute(f'DROP POLICY IF EXISTS {table}_insert_own ON app."{table}"')
        op.execute(f'DROP POLICY IF EXISTS {table}_select_own ON app."{table}"')
        op.drop_table(table, schema="app")
