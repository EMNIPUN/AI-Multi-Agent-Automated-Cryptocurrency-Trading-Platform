"""
PostgreSQL application models (Supabase-compatible).

These tables are observational / configuration — NOT a second execution ledger.
Authoritative order intents, executions, and durable risk remain in local SQLite
(Phase 1B / 1C / 1E) until an explicit, tested sync design lands in a later phase.

Ownership (Phase 2D): owner_user_id is the Supabase Auth user UUID (JWT ``sub``).
NULL owner_user_id = unowned / legacy — inaccessible to ordinary API users.
env_scope / account_fp are NOT proof of ownership.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# JSONB on Postgres; JSON fallback keeps offline SQLite model tests workable.
_JsonType = JSON().with_variant(JSONB(), "postgresql")


class AgentDecision(Base):
    """Non-authoritative decision log for future dashboards (no fill/order authority)."""

    __tablename__ = "agent_decisions"
    __table_args__ = (
        Index("ix_agent_decisions_env_created", "env_scope", "created_at"),
        Index("ix_agent_decisions_symbol_created", "symbol", "created_at"),
        Index("ix_agent_decisions_signal_id", "signal_id"),
        Index("ix_agent_decisions_owner_created", "owner_user_id", "created_at"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    env_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    account_fp: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    signal_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_json: Mapped[dict | None] = mapped_column(_JsonType, nullable=True)


class SystemEvent(Base):
    """Operational events for API/worker observability (no secrets)."""

    __tablename__ = "system_events"
    __table_args__ = (
        Index("ix_system_events_env_created", "env_scope", "created_at"),
        Index("ix_system_events_type_created", "event_type", "created_at"),
        Index("ix_system_events_owner_created", "owner_user_id", "created_at"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    env_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="local")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details_json: Mapped[dict | None] = mapped_column(_JsonType, nullable=True)


class StrategyConfig(Base):
    """Named strategy configuration documents (non-secret parameters only)."""

    __tablename__ = "strategy_configs"
    __table_args__ = (
        # Unique strategy name per owner (NULLs = unowned legacy; not API-visible).
        Index(
            "ix_strategy_configs_owner_name",
            "owner_user_id",
            "name",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL"),
        ),
        Index("ix_strategy_configs_owner_created", "owner_user_id", "created_at"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_json: Mapped[dict | None] = mapped_column(_JsonType, nullable=True)


class ExchangeAccountBindingRow(Base):
    """
    Verified user ↔ exchange account ownership (Phase 3C).

    credential_ref is an opaque server-side pointer (never raw API keys).
    telemetry_scope_id is the non-secret id stamped on worker events.
    Migration 0002 catalog owner columns are NOT exchange-account bindings.
    """

    __tablename__ = "exchange_account_bindings"
    __table_args__ = (
        Index(
            "ix_exchange_bindings_owner_provider_env",
            "owner_user_id",
            "provider",
            "environment",
        ),
        Index("ix_exchange_bindings_telemetry_scope", "telemetry_scope_id", unique=True),
        Index(
            "ix_exchange_bindings_active_cred",
            "provider",
            "credential_ref",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_exchange_bindings_owner_active_env",
            "owner_user_id",
            "provider",
            "environment",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="bybit")
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    display_label: Mapped[str] = mapped_column(String(128), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    telemetry_scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enrollment_attestation: Mapped[str] = mapped_column(Text, nullable=False)
    enrolled_by_operator: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
