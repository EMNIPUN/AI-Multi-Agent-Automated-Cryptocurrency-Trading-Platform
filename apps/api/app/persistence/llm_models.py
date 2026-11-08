"""ORM for Prompt 69D LLM audit rows. Schema app. Not created until Alembic 0009."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.app.models import Base, _JsonType


class LlmEvaluationRow(Base):
    __tablename__ = "llm_evaluations"
    __table_args__ = {"schema": "app"}

    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    signal_decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    interval: Mapped[str] = mapped_column(String(16), nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prompt_template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completed_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    evidence_event_ids_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reasoning_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_result: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    abstain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    coordinator_action: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    position_notional: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    agreement: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_changed_decision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    warnings_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    risk_warnings_json: Mapped[list] = mapped_column(_JsonType, nullable=False)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uncertainty: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    technical_bias: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    news_bias: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
