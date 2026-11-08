"""
Phase 4D SQLAlchemy models for proposed Supabase signal tables.

Tables are NOT created until the proposed Alembic revision is approved and applied.
Models exist so offline tests and gated repositories can compile against the schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models import Base, _JsonType


class SignalHistoryRow(Base):
    __tablename__ = "signal_history"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_signal_history_decision_id"),
        UniqueConstraint(
            "owner_user_id",
            "idempotent_key",
            name="uq_signal_history_owner_idempotent",
        ),
        Index("ix_signal_history_owner_ts", "owner_user_id", "timestamp_ms"),
        Index(
            "ix_signal_history_owner_symbol_tf",
            "owner_user_id",
            "symbol",
            "interval",
            "timestamp_ms",
        ),
        Index(
            "ix_signal_history_owner_strategy",
            "owner_user_id",
            "strategy_version",
            "timestamp_ms",
        ),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotent_key: Mapped[str] = mapped_column(String(256), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_strength: Mapped[float] = mapped_column(Float, nullable=False)
    directional_conviction: Mapped[float] = mapped_column(Float, nullable=False)
    market_quality: Mapped[float] = mapped_column(Float, nullable=False)
    risk_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    reason_codes: Mapped[dict | list] = mapped_column(_JsonType, nullable=False)
    risk_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    levels_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    market_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    indicators_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SignalAgentContributionRow(Base):
    __tablename__ = "signal_agent_contributions"
    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "agent_id",
            name="uq_signal_contrib_signal_agent",
        ),
        Index(
            "ix_signal_contrib_owner_decision",
            "owner_user_id",
            "decision_id",
        ),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    signal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app.signal_history.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    bias: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reason_codes: Mapped[dict | list] = mapped_column(_JsonType, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    indicators: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SignalRiskEventRow(Base):
    __tablename__ = "signal_risk_events"
    __table_args__ = (
        Index("ix_signal_risk_owner_ms", "owner_user_id", "event_ms"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("app.signal_history.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_codes: Mapped[dict | list] = mapped_column(_JsonType, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    event_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SchedulerEvaluationHistoryRow(Base):
    __tablename__ = "scheduler_evaluation_history"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "eval_key",
            name="uq_sched_eval_owner_key",
        ),
        Index(
            "ix_sched_eval_owner_stream",
            "owner_user_id",
            "strategy_version",
            "category",
            "symbol",
            "interval",
            "candle_close_ms",
        ),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    eval_key: Mapped[str] = mapped_column(String(256), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    candle_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candle_close_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decision_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SchedulerAuditRow(Base):
    __tablename__ = "scheduler_audit"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "local_audit_id",
            name="uq_sched_audit_owner_local",
        ),
        Index("ix_sched_audit_owner_ms", "owner_user_id", "created_at_ms"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    local_audit_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
