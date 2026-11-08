"""
Owner-scoped Supabase signal repository (writes gated OFF by default).

Application-layer owner filters are mandatory — privileged DATABASE_URL bypasses RLS.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from agent.multi_agent.decision_payload import validate_decision_sync_payload
from agent.multi_agent.types import CoordinatorDecision
from apps.api.app.sanitize import sanitize_public_json
from apps.api.app.signals.cloud_gates import get_signal_cloud_gates
from apps.api.app.signals.cloud_models import (
    SchedulerAuditRow,
    SchedulerEvaluationHistoryRow,
    SignalAgentContributionRow,
    SignalHistoryRow,
    SignalRiskEventRow,
)


class SignalCloudWriteDenied(RuntimeError):
    """Raised when cloud write gates are closed or owner is missing."""


class SignalCloudError(RuntimeError):
    """Classified database / validation failure for sync worker."""

    def __init__(self, code: str, *, permanent: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.permanent = permanent


class SignalCloudRepository(Protocol):
    def upsert_decision(
        self, *, owner_user_id: uuid.UUID, decision: CoordinatorDecision
    ) -> uuid.UUID | None: ...

    def list_history(
        self,
        *,
        owner_user_id: uuid.UUID,
        symbol: str | None = None,
        interval: str | None = None,
        action: str | None = None,
        strategy_version: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...


class SqlAlchemySignalCloudRepository:
    """Postgres-backed repository. Never trusts client-supplied owner ids."""

    def __init__(self, session: Session, *, require_gates: bool = True) -> None:
        self._session = session
        self._require_gates = require_gates

    def _assert_write_allowed(self) -> None:
        if not self._require_gates:
            return
        gates = get_signal_cloud_gates()
        if not gates.cloud_writes_allowed:
            raise SignalCloudWriteDenied("signal_supabase_writes_gated_off")

    def upsert_decision(
        self, *, owner_user_id: uuid.UUID, decision: CoordinatorDecision
    ) -> uuid.UUID | None:
        public = sanitize_public_json(decision.to_public_dict())
        indicators: dict[str, Any] = {}
        for c in public.get("contributions") or []:
            if isinstance(c, dict) and c.get("indicators"):
                indicators[str(c.get("agent_id"))] = c["indicators"]
        return self._upsert_public(
            owner_user_id=owner_user_id,
            public=public,
            indicators_by_agent=indicators,
        )

    def upsert_decision_payload(
        self, *, owner_user_id: uuid.UUID, payload: dict[str, Any]
    ) -> uuid.UUID | None:
        """Idempotent upsert from versioned outbox envelope (no CoordinatorDecision rebuild)."""
        ok, reason = validate_decision_sync_payload(payload)
        if not ok:
            raise SignalCloudError(f"payload_invalid:{reason}", permanent=True)
        public = sanitize_public_json(dict(payload.get("decision") or {}))
        indicators = dict(payload.get("indicators_by_agent") or {})
        if not indicators:
            for c in public.get("contributions") or []:
                if isinstance(c, dict) and c.get("indicators"):
                    indicators[str(c.get("agent_id"))] = c["indicators"]
        return self._upsert_public(
            owner_user_id=owner_user_id,
            public=public,
            indicators_by_agent=indicators,
        )

    def _upsert_public(
        self,
        *,
        owner_user_id: uuid.UUID,
        public: dict[str, Any],
        indicators_by_agent: dict[str, Any],
    ) -> uuid.UUID | None:
        self._assert_write_allowed()
        if not isinstance(owner_user_id, uuid.UUID):
            raise SignalCloudWriteDenied("owner_user_id_invalid")

        decision_id = str(public.get("decision_id") or "")
        if not decision_id:
            raise SignalCloudError("missing_decision_id", permanent=True)

        existing = self._session.scalar(
            select(SignalHistoryRow).where(
                SignalHistoryRow.owner_user_id == owner_user_id,
                SignalHistoryRow.decision_id == decision_id,
            )
        )
        if existing is not None:
            return existing.id

        ts_ms = int(public.get("timestamp_ms") or 0)
        decided_at = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        risk = dict(public.get("risk") or {})
        row = SignalHistoryRow(
            id=uuid.uuid4(),
            owner_user_id=owner_user_id,
            decision_id=decision_id,
            idempotent_key=str(public.get("idempotent_key") or "")[:256],
            correlation_id=str(public.get("correlation_id") or "")[:128],
            timestamp_ms=ts_ms,
            decided_at=decided_at,
            symbol=str(public.get("symbol") or "").upper()[:64],
            category=str(public.get("category") or "")[:16],
            interval=str(public.get("interval") or "")[:8],
            strategy_version=str(public.get("strategy_version") or "")[:32],
            config_hash=str(public.get("config_hash") or "")[:64],
            action=str(public.get("action") or "").upper()[:16],
            signal_strength=float(public.get("signal_strength") or 0.0),
            directional_conviction=float(public.get("directional_conviction") or 0.0),
            market_quality=float(public.get("market_quality") or 0.0),
            risk_verdict=str(risk.get("verdict") or "UNKNOWN")[:16],
            source_mode=str(public.get("source_mode") or "")[:32],
            explanation=str(public.get("explanation") or "")[:4000],
            reason_codes=list(public.get("reason_codes") or []),
            risk_json=risk,
            levels_json=dict(public.get("levels") or {}),
            market_json=dict(public.get("market") or {}),
            indicators_json=dict(indicators_by_agent or {}),
        )

        try:
            self._session.add(row)
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            again = self._session.scalar(
                select(SignalHistoryRow).where(
                    SignalHistoryRow.owner_user_id == owner_user_id,
                    SignalHistoryRow.decision_id == decision_id,
                )
            )
            return again.id if again else None
        except OperationalError as exc:
            raise SignalCloudError(f"db_operational:{type(exc).__name__}") from exc
        except SQLAlchemyError as exc:
            raise SignalCloudError(f"db_error:{type(exc).__name__}") from exc

        contribs = list(public.get("contributions") or [])
        for c in contribs:
            if not isinstance(c, dict):
                continue
            self._session.add(
                SignalAgentContributionRow(
                    id=uuid.uuid4(),
                    owner_user_id=owner_user_id,
                    signal_id=row.id,
                    decision_id=decision_id,
                    agent_id=str(c.get("agent_id") or "")[:64],
                    agent_version=str(c.get("agent_version") or "")[:32],
                    bias=str(c.get("bias") or "")[:64],
                    confidence=float(c.get("confidence") or 0.0),
                    reason_codes=list(c.get("reason_codes") or []),
                    explanation=str(c.get("explanation") or "")[:2000],
                    indicators=dict(c.get("indicators") or {}),
                    timed_out=bool(c.get("timed_out")),
                    error=(str(c["error"])[:128] if c.get("error") else None),
                )
            )

        self._session.add(
            SignalRiskEventRow(
                id=uuid.uuid4(),
                owner_user_id=owner_user_id,
                signal_id=row.id,
                decision_id=decision_id,
                event_type="signal_risk_verdict",
                verdict=str(risk.get("verdict") or "UNKNOWN")[:16],
                reason_codes=list(risk.get("reason_codes") or []),
                explanation=str(risk.get("explanation") or "")[:2000],
                payload_json=risk,
                event_ms=ts_ms,
            )
        )
        return row.id

    def upsert_checkpoint(
        self,
        *,
        owner_user_id: uuid.UUID,
        eval_key: str,
        strategy_version: str,
        category: str,
        symbol: str,
        interval: str,
        candle_start_ms: int,
        candle_close_ms: int,
        decision_id: str | None,
        status: str,
        updated_at_ms: int,
    ) -> None:
        self._assert_write_allowed()
        existing = self._session.scalar(
            select(SchedulerEvaluationHistoryRow).where(
                SchedulerEvaluationHistoryRow.owner_user_id == owner_user_id,
                SchedulerEvaluationHistoryRow.eval_key == eval_key,
            )
        )
        if existing is not None:
            existing.status = status
            existing.decision_id = decision_id
            existing.updated_at_ms = int(updated_at_ms)
            return
        self._session.add(
            SchedulerEvaluationHistoryRow(
                id=uuid.uuid4(),
                owner_user_id=owner_user_id,
                eval_key=eval_key,
                strategy_version=strategy_version,
                category=category,
                symbol=symbol.upper(),
                interval=interval,
                candle_start_ms=int(candle_start_ms),
                candle_close_ms=int(candle_close_ms),
                decision_id=decision_id,
                status=status,
                updated_at_ms=int(updated_at_ms),
            )
        )

    def append_audit(
        self,
        *,
        owner_user_id: uuid.UUID,
        event_type: str,
        detail: dict[str, Any],
        created_at_ms: int,
        local_audit_id: int | None = None,
    ) -> None:
        self._assert_write_allowed()
        if local_audit_id is not None:
            exists = self._session.scalar(
                select(SchedulerAuditRow.id).where(
                    SchedulerAuditRow.owner_user_id == owner_user_id,
                    SchedulerAuditRow.local_audit_id == local_audit_id,
                )
            )
            if exists is not None:
                return
        self._session.add(
            SchedulerAuditRow(
                id=uuid.uuid4(),
                owner_user_id=owner_user_id,
                local_audit_id=local_audit_id,
                event_type=event_type[:64],
                detail_json=sanitize_public_json(detail),
                created_at_ms=int(created_at_ms),
            )
        )

    def list_history(
        self,
        *,
        owner_user_id: uuid.UUID,
        symbol: str | None = None,
        category: str | None = None,
        interval: str | None = None,
        action: str | None = None,
        strategy_version: str | None = None,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        stmt: Select[Any] = select(SignalHistoryRow).where(
            SignalHistoryRow.owner_user_id == owner_user_id
        )
        if symbol:
            stmt = stmt.where(SignalHistoryRow.symbol == symbol.upper())
        if category:
            stmt = stmt.where(SignalHistoryRow.category == category)
        if interval:
            stmt = stmt.where(SignalHistoryRow.interval == interval)
        if action:
            stmt = stmt.where(SignalHistoryRow.action == action.upper())
        if strategy_version:
            stmt = stmt.where(SignalHistoryRow.strategy_version == strategy_version)
        if from_ms is not None:
            stmt = stmt.where(SignalHistoryRow.timestamp_ms >= int(from_ms))
        if to_ms is not None:
            stmt = stmt.where(SignalHistoryRow.timestamp_ms <= int(to_ms))
        stmt = (
            stmt.order_by(SignalHistoryRow.timestamp_ms.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self._session.scalars(stmt))
        return [self._row_public(r) for r in rows]

    def get_decision(
        self, *, owner_user_id: uuid.UUID, decision_id: str
    ) -> dict[str, Any] | None:
        row = self._session.scalar(
            select(SignalHistoryRow).where(
                SignalHistoryRow.owner_user_id == owner_user_id,
                SignalHistoryRow.decision_id == decision_id,
            )
        )
        return self._row_public(row) if row else None

    def list_contributions(
        self, *, owner_user_id: uuid.UUID, decision_id: str
    ) -> list[dict[str, Any]]:
        rows = list(
            self._session.scalars(
                select(SignalAgentContributionRow).where(
                    SignalAgentContributionRow.owner_user_id == owner_user_id,
                    SignalAgentContributionRow.decision_id == decision_id,
                )
            )
        )
        return [
            {
                "agent_id": r.agent_id,
                "agent_version": r.agent_version,
                "bias": r.bias,
                "confidence": float(r.confidence),
                "reason_codes": r.reason_codes,
                "explanation": r.explanation,
                "indicators": r.indicators,
                "timed_out": bool(r.timed_out),
                "error": r.error,
            }
            for r in rows
        ]

    def list_risk_events(
        self,
        *,
        owner_user_id: uuid.UUID,
        decision_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        stmt = select(SignalRiskEventRow).where(
            SignalRiskEventRow.owner_user_id == owner_user_id
        )
        if decision_id:
            stmt = stmt.where(SignalRiskEventRow.decision_id == decision_id)
        stmt = (
            stmt.order_by(SignalRiskEventRow.event_ms.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self._session.scalars(stmt))
        return [
            {
                "decision_id": r.decision_id,
                "event_type": r.event_type,
                "verdict": r.verdict,
                "reason_codes": r.reason_codes,
                "explanation": r.explanation,
                "payload": r.payload_json,
                "event_ms": int(r.event_ms),
            }
            for r in rows
        ]

    def list_strategy_versions(self, *, owner_user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(SignalHistoryRow.strategy_version, func.count())
            .where(SignalHistoryRow.owner_user_id == owner_user_id)
            .group_by(SignalHistoryRow.strategy_version)
            .order_by(SignalHistoryRow.strategy_version.asc())
        ).all()
        return [{"strategy_version": v, "count": int(n)} for v, n in rows]

    def analytics(self, *, owner_user_id: uuid.UUID) -> dict[str, Any]:
        total = self._session.scalar(
            select(func.count())
            .select_from(SignalHistoryRow)
            .where(SignalHistoryRow.owner_user_id == owner_user_id)
        )
        by_action_rows = self._session.execute(
            select(SignalHistoryRow.action, func.count())
            .where(SignalHistoryRow.owner_user_id == owner_user_id)
            .group_by(SignalHistoryRow.action)
        ).all()
        by_symbol = self._session.execute(
            select(SignalHistoryRow.symbol, func.count())
            .where(SignalHistoryRow.owner_user_id == owner_user_id)
            .group_by(SignalHistoryRow.symbol)
        ).all()
        by_strategy = self._session.execute(
            select(SignalHistoryRow.strategy_version, func.count())
            .where(SignalHistoryRow.owner_user_id == owner_user_id)
            .group_by(SignalHistoryRow.strategy_version)
        ).all()
        return {
            "total_signals": int(total or 0),
            "by_action": {a: int(n) for a, n in by_action_rows},
            "by_symbol": {s: int(n) for s, n in by_symbol},
            "by_strategy_version": {v: int(n) for v, n in by_strategy},
            "owner_filtered": True,
            "metrics_note": "No win-rate/PnL — outcome evaluation not in Phase 4D scope.",
            "cloud_source": "supabase_app_signal_history",
            "cloud_confirmed": True,
        }

    @staticmethod
    def _row_public(row: SignalHistoryRow) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "decision_id": row.decision_id,
            "idempotent_key": row.idempotent_key,
            "timestamp_ms": int(row.timestamp_ms),
            "symbol": row.symbol,
            "category": row.category,
            "interval": row.interval,
            "strategy_version": row.strategy_version,
            "config_hash": row.config_hash,
            "action": row.action,
            "signal_strength": float(row.signal_strength),
            "directional_conviction": float(row.directional_conviction),
            "market_quality": float(row.market_quality),
            "risk_verdict": row.risk_verdict,
            "source_mode": row.source_mode,
            "explanation": row.explanation,
            "reason_codes": row.reason_codes,
            "risk": row.risk_json,
            "levels": row.levels_json,
            "market": row.market_json,
            "indicators": row.indicators_json,
            "persistence": "supabase",
            "not_an_order": True,
            "execution_allowed": False,
        }
