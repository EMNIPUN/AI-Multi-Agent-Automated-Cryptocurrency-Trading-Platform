"""Prompt 69D — LLM decision-support audit.

Revision ID: 20261108_0009
Revises: 20261108_0008

Not applied. Requires 20261108_0008 first, then operator approval on the
development database only. Do not apply to production.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0009"
down_revision: Union[str, None] = "20261108_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_evaluations",
        sa.Column("evaluation_id", sa.String(length=64), primary_key=True),
        sa.Column("signal_decision_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("prompt_template_version", sa.String(length=32), nullable=False),
        sa.Column("requested_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("completed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("evidence_event_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("suggested_action", sa.String(length=16), nullable=True),
        sa.Column("reasoning_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("validation_result", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("abstain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("coordinator_action", sa.String(length=16), nullable=False),
        sa.Column("risk_verdict", sa.String(length=16), nullable=False),
        sa.Column("position_notional", sa.Numeric(20, 8), nullable=True),
        sa.Column("agreement", sa.String(length=32), nullable=False),
        sa.Column("llm_changed_decision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conflict_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("uncertainty", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("technical_bias", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.Column("news_bias", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.UniqueConstraint("idempotency_key", name="uq_llm_evaluations_idempotency"),
        schema="app",
    )
    op.create_index(
        "ix_llm_evaluations_symbol_requested",
        "llm_evaluations",
        ["symbol", "requested_at_ms"],
        schema="app",
    )
    op.execute('ALTER TABLE app."llm_evaluations" ENABLE ROW LEVEL SECURITY')
    op.execute(
        """
        CREATE POLICY llm_evaluations_select_own
        ON app."llm_evaluations"
        FOR SELECT
        TO authenticated
        USING (owner_user_id IS NULL OR owner_user_id = auth.uid())
        """
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS llm_evaluations_select_own ON app."llm_evaluations"')
    op.drop_index("ix_llm_evaluations_symbol_requested", table_name="llm_evaluations", schema="app")
    op.drop_table("llm_evaluations", schema="app")
