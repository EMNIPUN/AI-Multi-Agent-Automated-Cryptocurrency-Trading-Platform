"""Prompt 69B — news alerts, deliveries, preferences, collection lease.

Revision ID: 20261108_0008
Revises: 20261108_0007

Do not apply to production. Development apply requires operator approval
(CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes plus the existing identity guard).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0008"
down_revision: Union[str, None] = "20261108_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "news_alerts",
    "news_alert_deliveries",
    "news_alert_preferences",
    "news_collection_lease",
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
        "news_alerts",
        sa.Column("alert_id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("symbols_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verification", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("article_hashes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("first_observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("detected_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("available_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("acknowledged_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("material_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("warnings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("freshness", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("agent_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["app.news_events.event_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_news_alerts_idempotency"),
        schema="app",
    )
    op.create_index("ix_news_alerts_status_created", "news_alerts", ["status", "created_at_ms"], schema="app")
    op.create_index("ix_news_alerts_severity_created", "news_alerts", ["severity", "created_at_ms"], schema="app")

    op.create_table(
        "news_alert_deliveries",
        sa.Column("delivery_id", sa.String(length=64), primary_key=True),
        sa.Column("alert_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("confirmed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["app.news_alerts.alert_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("idempotency_key", name="uq_news_alert_deliveries_idempotency"),
        schema="app",
    )
    op.create_index(
        "ix_news_alert_deliveries_alert",
        "news_alert_deliveries",
        ["alert_id", "channel"],
        schema="app",
    )

    op.create_table(
        "news_alert_preferences",
        sa.Column("preference_id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("min_severity", sa.String(length=32), nullable=False, server_default="HIGH"),
        sa.Column("symbols_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cooldown_ms", sa.BigInteger(), nullable=False),
        sa.Column("ttl_ms", sa.BigInteger(), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("telegram_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("owner_user_id", name="uq_news_alert_preferences_owner"),
        schema="app",
    )

    op.create_table(
        "news_collection_lease",
        sa.Column("lease_name", sa.String(length=64), primary_key=True),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("acquired_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("expires_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        schema="app",
    )

    for table in _TABLES:
        _rls_select_own(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_select_own ON app.{table}")
        op.drop_table(table, schema="app")
