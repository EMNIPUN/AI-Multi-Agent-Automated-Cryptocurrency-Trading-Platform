"""Postgres audit store for LLM evaluations. Rejects SQLite. Fail closed."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agent.llm_intelligence.audit_repository import LlmStorageError
from agent.llm_intelligence.schemas import LlmEvaluation
from apps.api.app.persistence.llm_models import LlmEvaluationRow


def _row_to_record(row: LlmEvaluationRow, *, replay: bool = False) -> LlmEvaluation:
    notional = None if row.position_notional is None else float(row.position_notional)
    return LlmEvaluation(
        evaluation_id=row.evaluation_id,
        status=row.status,
        symbol=row.symbol,
        interval=row.interval,
        signal_decision_id=row.signal_decision_id,
        coordinator_action=row.coordinator_action,
        risk_verdict=row.risk_verdict,
        position_notional=notional,
        suggested_action=row.suggested_action,
        agreement=row.agreement,
        conflict_detected=bool(row.conflict_detected),
        reason=row.reasoning_summary,
        risk_warnings=tuple(row.risk_warnings_json or []),
        evidence_event_ids=tuple(row.evidence_event_ids_json or []),
        uncertainty=row.uncertainty,
        abstain=bool(row.abstain),
        model=row.model,
        provider=row.provider,
        prompt_template_version=row.prompt_template_version,
        context_hash=row.context_hash,
        validation_result=row.validation_result,
        token_usage={
            "prompt_tokens": int(row.prompt_tokens or 0),
            "completion_tokens": int(row.completion_tokens or 0),
        },
        estimated_cost_usd=float(row.estimated_cost_usd or 0),
        persisted=True,
        storage_error=None,
        provider_called=row.status not in {"disabled", "missing_api_key", "missing_model"},
        idempotency_key=row.idempotency_key,
        idempotent_replay=replay,
        warnings=tuple(row.warnings_json or []),
        requested_at_ms=int(row.requested_at_ms),
        completed_at_ms=int(row.completed_at_ms),
        technical_bias=row.technical_bias,
        news_bias=row.news_bias,
        error_code=row.error_code,
        llm_changed_decision=False,
    )


class PostgresLlmAuditRepository:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name == "sqlite":
            raise LlmStorageError("sqlite_forbidden", "LLM audit storage refuses SQLite")
        self._engine = engine

    def storage_kind(self) -> str:
        return "postgres"

    def ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM app.llm_evaluations LIMIT 1"))
            return True
        except SQLAlchemyError:
            return False

    def save(self, record: LlmEvaluation) -> LlmEvaluation:
        try:
            with Session(self._engine) as session:
                existing = session.scalar(
                    select(LlmEvaluationRow).where(LlmEvaluationRow.idempotency_key == record.idempotency_key)
                )
                if existing is not None:
                    return _row_to_record(existing, replay=True)
                session.add(
                    LlmEvaluationRow(
                        evaluation_id=record.evaluation_id,
                        signal_decision_id=record.signal_decision_id or "unknown",
                        symbol=record.symbol or "UNKNOWN",
                        interval=record.interval or "",
                        context_hash=record.context_hash,
                        provider=record.provider,
                        model=record.model,
                        prompt_template_version=record.prompt_template_version,
                        requested_at_ms=record.requested_at_ms,
                        completed_at_ms=record.completed_at_ms,
                        evidence_event_ids_json=list(record.evidence_event_ids),
                        suggested_action=record.suggested_action,
                        reasoning_summary=record.reason[:2000],
                        validation_result=record.validation_result,
                        status=record.status,
                        error_code=record.error_code,
                        abstain=record.abstain,
                        prompt_tokens=int(record.token_usage.get("prompt_tokens") or 0),
                        completion_tokens=int(record.token_usage.get("completion_tokens") or 0),
                        estimated_cost_usd=Decimal(str(record.estimated_cost_usd)),
                        coordinator_action=record.coordinator_action or "HOLD",
                        risk_verdict=record.risk_verdict or "VETO",
                        position_notional=None
                        if record.position_notional is None
                        else Decimal(str(record.position_notional)),
                        agreement=record.agreement,
                        llm_changed_decision=False,
                        idempotency_key=record.idempotency_key,
                        warnings_json=list(record.warnings),
                        risk_warnings_json=list(record.risk_warnings),
                        conflict_detected=record.conflict_detected,
                        uncertainty=record.uncertainty,
                        technical_bias=record.technical_bias,
                        news_bias=record.news_bias,
                    )
                )
                session.commit()
            return record
        except SQLAlchemyError as exc:
            raise LlmStorageError("storage_unavailable", "llm evaluation write failed") from exc

    def get(self, evaluation_id: str) -> LlmEvaluation | None:
        try:
            with Session(self._engine) as session:
                row = session.get(LlmEvaluationRow, evaluation_id)
                return None if row is None else _row_to_record(row)
        except SQLAlchemyError as exc:
            raise LlmStorageError("storage_unavailable", "llm evaluation read failed") from exc

    def get_by_idempotency(self, key: str) -> LlmEvaluation | None:
        try:
            with Session(self._engine) as session:
                row = session.scalar(select(LlmEvaluationRow).where(LlmEvaluationRow.idempotency_key == key))
                return None if row is None else _row_to_record(row)
        except SQLAlchemyError as exc:
            raise LlmStorageError("storage_unavailable", "llm evaluation read failed") from exc

    def list_recent(self, *, limit: int) -> list[LlmEvaluation]:
        try:
            with Session(self._engine) as session:
                rows = session.scalars(
                    select(LlmEvaluationRow).order_by(LlmEvaluationRow.requested_at_ms.desc()).limit(limit)
                ).all()
                return [_row_to_record(row) for row in rows]
        except SQLAlchemyError as exc:
            raise LlmStorageError("storage_unavailable", "llm evaluation list failed") from exc
