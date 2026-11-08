"""Signal scheduler / day-risk tables (SoT cutover)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models import Base, _JsonType


class SignalDayRiskStateRow(Base):
    __tablename__ = "signal_day_risk_state"
    __table_args__ = {"schema": "app"}

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True
    )
    day_key: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    hypothetical_day_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_signal_key: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    last_signal_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    halted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seen_keys_json: Mapped[dict | list] = mapped_column(_JsonType, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    corrupt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SchedulerLockRow(Base):
    __tablename__ = "scheduler_lock"
    __table_args__ = {"schema": "app"}

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lease_until_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hostname: Mapped[str] = mapped_column(String(128), nullable=False)
    pid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
