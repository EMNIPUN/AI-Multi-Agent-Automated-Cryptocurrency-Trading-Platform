"""Prompt 69E — append-only news revisions and shadow-run metadata.

Revision ID: 20261108_0010
Revises: 20261108_0009

Not applied. Requires 20261108_0008 and 20261108_0009 first.
Development apply needs operator approval. Do not apply to production.

Rows are append-only. Updating or deleting a revision is rejected so a later
classification cannot rewrite an earlier snapshot. There is no foreign key to
``app.news_events``: deleting the latest upsert must not erase history.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0010"
down_revision: Union[str, None] = "20261108_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_event_revisions",
        sa.Column("revision_id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("classification_version", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("sentiment", sa.String(length=32), nullable=False),
        sa.Column("verification", sa.String(length=32), nullable=False),
        sa.Column("symbols_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_observed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_available_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("revision_available_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("recorded_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("delayed_provider", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("event_id", "revision_number", name="uq_news_event_revisions_event_rev"),
        schema="app",
    )
    op.create_index(
        "ix_news_event_revisions_symbol_recorded",
        "news_event_revisions",
        ["recorded_at_ms"],
        schema="app",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.prevent_news_revision_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'news_event_revisions are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER news_event_revisions_no_mutation
        BEFORE UPDATE OR DELETE ON app.news_event_revisions
        FOR EACH ROW
        EXECUTE FUNCTION app.prevent_news_revision_mutation()
        """
    )
    op.execute('ALTER TABLE app."news_event_revisions" ENABLE ROW LEVEL SECURITY')
    op.execute(
        """
        CREATE POLICY news_event_revisions_select_own
        ON app."news_event_revisions"
        FOR SELECT
        TO authenticated
        USING (owner_user_id IS NULL OR owner_user_id = auth.uid())
        """
    )

    op.create_table(
        "backtest_shadow_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_ms", sa.BigInteger(), nullable=True),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("news_dataset_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("provenance_status", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("llm_changed_decision", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        schema="app",
    )
    op.execute('ALTER TABLE app."backtest_shadow_runs" ENABLE ROW LEVEL SECURITY')
    op.execute(
        """
        CREATE POLICY backtest_shadow_runs_select_own
        ON app."backtest_shadow_runs"
        FOR SELECT
        TO authenticated
        USING (owner_user_id IS NULL OR owner_user_id = auth.uid())
        """
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS backtest_shadow_runs_select_own ON app."backtest_shadow_runs"')
    op.drop_table("backtest_shadow_runs", schema="app")
    op.execute('DROP POLICY IF EXISTS news_event_revisions_select_own ON app."news_event_revisions"')
    op.execute("DROP TRIGGER IF EXISTS news_event_revisions_no_mutation ON app.news_event_revisions")
    op.execute("DROP FUNCTION IF EXISTS app.prevent_news_revision_mutation()")
    op.drop_index("ix_news_event_revisions_symbol_recorded", table_name="news_event_revisions", schema="app")
    op.drop_table("news_event_revisions", schema="app")
