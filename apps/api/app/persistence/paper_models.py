"""Paper broker tables — TEXT money fields matching agent/paper/store.py."""

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


class PaperMetaRow(Base):
    __tablename__ = "paper_meta"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "key", name="uq_paper_meta_owner_key"),
        {"schema": "app"},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class PaperSessionRow(Base):
    __tablename__ = "paper_sessions"
    __table_args__ = (
        Index("ix_paper_sessions_owner_updated", "owner_user_id", "updated_ms"),
        {"schema": "app"},
    )

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    initial_balance: Mapped[str] = mapped_column(Text, nullable=False)
    available_balance: Mapped[str] = mapped_column(Text, nullable=False)
    reserved_capital: Mapped[str] = mapped_column(Text, nullable=False)
    realized_pnl: Mapped[str] = mapped_column(Text, nullable=False)
    fees_paid: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USDT")


class PaperOrderRow(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "source_signal_id", "side", name="uq_paper_orders_session_signal_side"
        ),
        Index("ix_paper_orders_session_status", "session_id", "status"),
        {"schema": "app"},
    )

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_sessions.session_id"), nullable=False
    )
    source_signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)
    intended_entry_price: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filled_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fill_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    slippage: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    stop_loss: Mapped[str | None] = mapped_column(Text, nullable=True)
    take_profit: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_candle_start_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PaperFillRow(Base):
    __tablename__ = "paper_fills"
    __table_args__ = (
        UniqueConstraint("order_id", "role", name="uq_paper_fills_order_role"),
        UniqueConstraint(
            "session_id", "order_id", "candle_start_ms", "role", name="uq_paper_fills_session"
        ),
        {"schema": "app"},
    )

    fill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_orders.order_id"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_sessions.session_id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[str] = mapped_column(Text, nullable=False)
    fee: Mapped[str] = mapped_column(Text, nullable=False)
    slippage: Mapped[str] = mapped_column(Text, nullable=False)
    filled_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candle_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class PaperPositionRow(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("session_id", "entry_signal_id", name="uq_paper_positions_session_signal"),
        Index("ix_paper_positions_open", "session_id", "status", "symbol"),
        {"schema": "app"},
    )

    position_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_sessions.session_id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[str] = mapped_column(Text, nullable=False)
    entry_price: Mapped[str] = mapped_column(Text, nullable=False)
    entry_fee: Mapped[str] = mapped_column(Text, nullable=False)
    entry_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_signal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    stop_loss: Mapped[str | None] = mapped_column(Text, nullable=True)
    take_profit: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closed_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    exit_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_fee: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    exit_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    realized_pnl: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    mark_price: Mapped[str | None] = mapped_column(Text, nullable=True)
    unrealized_pnl: Mapped[str] = mapped_column(Text, nullable=False, default="0")


class PaperAccountEventRow(Base):
    __tablename__ = "paper_account_events"
    __table_args__ = (
        UniqueConstraint("session_id", "idempotency_key", name="uq_paper_events_idem"),
        {"schema": "app"},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_sessions.session_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)


class PaperCandleCursorRow(Base):
    __tablename__ = "paper_candle_cursor"
    __table_args__ = {"schema": "app"}

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    interval: Mapped[str] = mapped_column(String(8), primary_key=True)
    last_candle_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PaperProcessedEventRow(Base):
    __tablename__ = "paper_processed_events"
    __table_args__ = {"schema": "app"}

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    created_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PaperRiskStateRow(Base):
    __tablename__ = "paper_risk_state"
    __table_args__ = {"schema": "app"}

    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_sessions.session_id"), primary_key=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    halted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    halt_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    halt_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    peak_marked_equity: Mapped[str | None] = mapped_column(Text, nullable=True)
    day_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    day_start_equity: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PaperEquitySnapshotRow(Base):
    __tablename__ = "paper_equity_snapshots"
    __table_args__ = (
        UniqueConstraint("session_id", "as_of_ms", name="uq_paper_equity_session_asof"),
        Index("ix_paper_equity_session", "session_id", "as_of_ms"),
        {"schema": "app"},
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("app.paper_sessions.session_id"), nullable=False
    )
    as_of_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    available_balance: Mapped[str] = mapped_column(Text, nullable=False)
    reserved_capital: Mapped[str] = mapped_column(Text, nullable=False)
    realized_pnl: Mapped[str] = mapped_column(Text, nullable=False)
    unrealized_pnl: Mapped[str | None] = mapped_column(Text, nullable=True)
    marked_equity: Mapped[str | None] = mapped_column(Text, nullable=True)
    valuation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    open_position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_exposure: Mapped[str] = mapped_column(Text, nullable=False)
    day_key: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
