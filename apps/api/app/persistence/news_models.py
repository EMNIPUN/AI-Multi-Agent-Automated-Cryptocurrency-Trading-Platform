"""ORM models for Prompt 69A/69A.1 news foundation tables (schema app)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models import Base, _JsonType


class NewsSourceRow(Base):
    __tablename__ = "news_sources"
    __table_args__ = {"schema": "app"}

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="provider")
    meta_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NewsArticleRow(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id", name="uq_news_articles_provider_external"),
        Index("ix_news_articles_ingested", "ingested_at_ms"),
        {"schema": "app"},
    )

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_observed_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ingested_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    provider_latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_delayed_feed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    asset_hints_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NewsEventRow(Base):
    __tablename__ = "news_events"
    __table_args__ = (
        Index("ix_news_events_available", "available_at_ms"),
        Index("ix_news_events_severity_available", "severity", "available_at_ms"),
        {"schema": "app"},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    sentiment: Mapped[str] = mapped_column(String(32), nullable=False)
    verification: Mapped[str] = mapped_column(String(32), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    published_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_observed_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    available_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    classification_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason_codes_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    warnings_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    article_hashes_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    evidence_quality: Mapped[str] = mapped_column(String(64), nullable=False, default="rule_based_v1")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NewsEventAssetRow(Base):
    __tablename__ = "news_event_assets"
    __table_args__ = (
        Index("ix_news_event_assets_symbol", "symbol"),
        {"schema": "app"},
    )

    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.news_events.event_id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class NewsClassificationRow(Base):
    __tablename__ = "news_classifications"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.news_events.event_id", ondelete="CASCADE"), nullable=False
    )
    classifier_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class NewsIngestionRunRow(Base):
    __tablename__ = "news_ingestion_runs"
    __table_args__ = {"schema": "app"}

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    finished_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_dropped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    provider_ids_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NewsProviderHealthRow(Base):
    __tablename__ = "news_provider_health"
    __table_args__ = (
        Index("ix_news_provider_health_checked", "provider_id", "checked_ms"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    checked_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class NewsAlertRow(Base):
    __tablename__ = "news_alerts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_news_alerts_idempotency"),
        Index("ix_news_alerts_status_created", "status", "created_at_ms"),
        Index("ix_news_alerts_severity_created", "severity", "created_at_ms"),
        {"schema": "app"},
    )

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.news_events.event_id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    symbols_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    verification: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_hashes_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    published_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_observed_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    available_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    acknowledged_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    material_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    warnings_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    freshness: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    agent_context_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)


class NewsAlertDeliveryRow(Base):
    __tablename__ = "news_alert_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_news_alert_deliveries_idempotency"),
        Index("ix_news_alert_deliveries_alert", "alert_id", "channel"),
        {"schema": "app"},
    )

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    alert_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.news_alerts.alert_id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class NewsAlertPreferenceRow(Base):
    __tablename__ = "news_alert_preferences"
    __table_args__ = (
        UniqueConstraint("owner_user_id", name="uq_news_alert_preferences_owner"),
        {"schema": "app"},
    )

    preference_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    min_severity: Mapped[str] = mapped_column(String(32), nullable=False, default="HIGH")
    symbols_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    cooldown_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ttl_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class NewsCollectionLeaseRow(Base):
    __tablename__ = "news_collection_lease"
    __table_args__ = {"schema": "app"}

    lease_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    acquired_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
