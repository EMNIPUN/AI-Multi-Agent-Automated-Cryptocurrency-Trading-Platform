"""Prompt 69A — Supabase news foundation tables (app schema).

Revision ID: 20261108_0007
Revises: 20261108_0006
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0007"
down_revision: Union[str, None] = "20261108_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "news_sources",
    "news_articles",
    "news_events",
    "news_event_assets",
    "news_classifications",
    "news_ingestion_runs",
    "news_provider_health",
)


def _rls_select_own(table: str) -> None:
    op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_select_own
        ON app.{table}
        FOR SELECT
        TO authenticated
        USING (owner_user_id IS NULL OR owner_user_id = auth.uid())
        """
    )


def upgrade() -> None:
    op.create_table(
        "news_sources",
        sa.Column("provider_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="provider"),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="app",
    )

    op.create_table(
        "news_articles",
        sa.Column("content_hash", sa.String(length=64), primary_key=True),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("published_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("ingested_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("provider_latency_ms", sa.BigInteger(), nullable=True),
        sa.Column("is_delayed_feed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("asset_hints_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("provider_id", "external_id", name="uq_news_articles_provider_external"),
        schema="app",
    )
    op.create_index(
        "ix_news_articles_ingested",
        "news_articles",
        ["ingested_at_ms"],
        schema="app",
    )

    op.create_table(
        "news_events",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("sentiment", sa.String(length=32), nullable=False),
        sa.Column("verification", sa.String(length=32), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("published_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("available_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("classification_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("reason_codes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("article_hashes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_quality", sa.String(length=64), nullable=False, server_default="rule_based_v1"),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="app",
    )
    op.create_index(
        "ix_news_events_available",
        "news_events",
        ["available_at_ms"],
        schema="app",
    )
    op.create_index(
        "ix_news_events_severity_available",
        "news_events",
        ["severity", "available_at_ms"],
        schema="app",
    )

    op.create_table(
        "news_event_assets",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("event_id", "symbol"),
        sa.ForeignKeyConstraint(["event_id"], ["app.news_events.event_id"], ondelete="CASCADE"),
        schema="app",
    )
    op.create_index(
        "ix_news_event_assets_symbol",
        "news_event_assets",
        ["symbol"],
        schema="app",
    )

    op.create_table(
        "news_classifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("classifier_version", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["app.news_events.event_id"], ondelete="CASCADE"),
        schema="app",
    )

    op.create_table(
        "news_ingestion_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("started_ms", sa.BigInteger(), nullable=False),
        sa.Column("finished_ms", sa.BigInteger(), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_dropped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="app",
    )

    op.create_table(
        "news_provider_health",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("checked_ms", sa.BigInteger(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        schema="app",
    )
    op.create_index(
        "ix_news_provider_health_checked",
        "news_provider_health",
        ["provider_id", "checked_ms"],
        schema="app",
    )

    for table in _TABLES:
        _rls_select_own(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_select_own ON app.{table}")
        op.drop_table(table, schema="app")
