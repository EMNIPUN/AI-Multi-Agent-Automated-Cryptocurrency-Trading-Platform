"""Execution, risk, ledger, automation, and observability SoT tables."""

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
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models import Base, _JsonType


class OrderIntentRow(Base):
    __tablename__ = "order_intents"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "env_scope",
            "account_fp",
            "client_order_id",
            name="uq_order_intents_owner_client",
        ),
        Index("ix_order_intents_owner_state", "owner_user_id", "env_scope", "account_fp", "state"),
        {"schema": "app"},
    )

    intent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    env_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    account_fp: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[str] = mapped_column(Text, nullable=False)
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(16), nullable=False)
    take_profit: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_loss: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_auth_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exchange_order_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    filled_qty: Mapped[str] = mapped_column(Text, nullable=False, default="")
    remaining_qty: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avg_exec_price: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cum_fee: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_status: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submission_attempted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class OrderExecutionRow(Base):
    __tablename__ = "order_executions"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id", "env_scope", "account_fp", "exec_id", name="uq_order_exec"
        ),
        Index("ix_order_executions_intent", "intent_id"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    env_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    account_fp: Mapped[str] = mapped_column(String(128), nullable=False)
    intent_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.order_intents.intent_id"), nullable=False
    )
    exec_id: Mapped[str] = mapped_column(String(128), nullable=False)
    order_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_link_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exec_qty: Mapped[str] = mapped_column(Text, nullable=False)
    exec_price: Mapped[str] = mapped_column(Text, nullable=False)
    exec_fee: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fee_currency: Mapped[str] = mapped_column(Text, nullable=False, default="")
    exec_time_ms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_maker: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    leaves_qty: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class AccountRiskSnapshotRow(Base):
    __tablename__ = "account_risk_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "env_scope",
            "account_fp",
            "risk_date",
            name="uq_account_risk_owner_day",
        ),
        Index("ix_account_risk_updated", "owner_user_id", "env_scope", "account_fp", "updated_at"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    env_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    account_fp: Mapped[str] = mapped_column(String(128), nullable=False)
    risk_date: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    start_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_loss_pct_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    daily_loss_pct_current: Mapped[float | None] = mapped_column(Float, nullable=True)
    emergency_halt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    halt_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recovery_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)


class SignalLedgerEntryRow(Base):
    __tablename__ = "signal_ledger_entries"
    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "env_scope",
            "account_fp",
            "signal_id",
            name="uq_signal_ledger_entry",
        ),
        Index(
            "ix_signal_ledger_symbol_close",
            "owner_user_id",
            "env_scope",
            "account_fp",
            "symbol",
            "category",
            "interval",
            "candle_close_ms",
        ),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    env_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    account_fp: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    candle_close_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)


class AutomationExecIntentRow(Base):
    __tablename__ = "automation_exec_intents"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "intent_id", name="uq_auto_exec_intent"),
        UniqueConstraint("owner_user_id", "client_order_id", name="uq_auto_exec_client"),
        Index("ix_auto_exec_intents_state", "owner_user_id", "state", "updated_at_ms"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange_order_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_loss: Mapped[str | None] = mapped_column(Text, nullable=True)
    take_profit: Mapped[str | None] = mapped_column(Text, nullable=True)
    protection_state: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    payload_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class AutomationExecEventRow(Base):
    __tablename__ = "automation_exec_events"
    __table_args__ = (
        Index("ix_auto_exec_events_intent", "owner_user_id", "intent_id", "created_at_ms"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    created_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ObservationEventRow(Base):
    __tablename__ = "observation_events"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "event_id", name="uq_observation_event_id"),
        Index("ix_observation_owner_seq", "owner_user_id", "seq"),
        {"schema": "app"},
    )

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    env_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    account_scope_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interval: Mapped[str | None] = mapped_column(String(8), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    pipeline_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(_JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
