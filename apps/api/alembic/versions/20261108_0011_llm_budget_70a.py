"""Prompt 70A — durable LLM budget ledger.

Revision ID: 20261108_0011
Revises: 20261108_0010

Not applied. Requires 0008, 0009, and 0010 first.
Development apply needs operator approval. Do not apply to production.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261108_0011"
down_revision: Union[str, None] = "20261108_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_budget_ledger",
        sa.Column("reservation_id", sa.String(length=64), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("actual_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_llm_budget_ledger_idempotency"),
        schema="app",
    )
    op.create_index(
        "ix_llm_budget_ledger_created",
        "llm_budget_ledger",
        ["created_at_ms", "status"],
        schema="app",
    )
    op.execute('ALTER TABLE app."llm_budget_ledger" ENABLE ROW LEVEL SECURITY')
    op.execute(
        """
        CREATE POLICY llm_budget_ledger_select_own
        ON app."llm_budget_ledger"
        FOR SELECT
        TO authenticated
        USING (owner_user_id IS NULL OR owner_user_id = auth.uid())
        """
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS llm_budget_ledger_select_own ON app."llm_budget_ledger"')
    op.drop_index("ix_llm_budget_ledger_created", table_name="llm_budget_ledger", schema="app")
    op.drop_table("llm_budget_ledger", schema="app")
