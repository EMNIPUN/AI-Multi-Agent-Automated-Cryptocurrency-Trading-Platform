"""Supabase / SQLAlchemy signal history + scheduler state (SoT cutover)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from agent.multi_agent.risk_agent import SignalRiskState
from agent.multi_agent.types import CoordinatorDecision
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.signal_extra_models import (
    SchedulerLockRow,
    SignalDayRiskStateRow,
)
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
    supabase_sot_enabled,
)
from apps.api.app.sanitize import sanitize_public_json
from apps.api.app.signals.cloud_models import (
    SchedulerAuditRow,
    SchedulerEvaluationHistoryRow,
    SignalAgentContributionRow,
    SignalHistoryRow as SignalHistoryOrm,
)

_SCHEMA_VERSION = 4


@dataclass(frozen=True)
class CheckpointWrite:
    eval_key: str
    strategy_version: str
    category: str
    symbol: str
    interval: str
    candle_start_ms: int
    candle_close_ms: int
    decision_id: str | None
    status: str


def resolve_signal_db_path(db_path: str | Path | None = None) -> Path:
    """Legacy path hint — ignored when SUPABASE_SOT_ENABLED (default true)."""
    if db_path is not None:
        return Path(db_path)
    env = (
        os.getenv("MULTI_AGENT_SIGNALS_DB")
        or os.getenv("SIGNAL_HISTORY_DB")
        or ""
    ).strip()
    if env:
        return Path(env)
    root = Path(__file__).resolve().parents[2]
    return root / "data" / "multi_agent_signals.sqlite3"


def evaluation_key(
    *,
    strategy_version: str,
    category: str,
    symbol: str,
    interval: str,
    candle_close_ms: int,
) -> str:
    return (
        f"{strategy_version}|{category}|{symbol.upper()}|{interval}|{int(candle_close_ms)}"
    )


@dataclass(frozen=True)
class SignalHistoryRowView:
    decision_id: str
    idempotent_key: str
    correlation_id: str
    timestamp_ms: int
    symbol: str
    category: str
    interval: str
    strategy_version: str
    config_hash: str
    action: str
    signal_strength: float
    directional_conviction: float
    market_quality: float
    risk_verdict: str
    source_mode: str
    explanation: str
    reason_codes: list[str]
    contributions: list[dict[str, Any]]
    risk: dict[str, Any]
    levels: dict[str, Any]
    market: dict[str, Any]
    indicators: dict[str, Any]


class SignalHistoryStoreError(RuntimeError):
    """Fail-closed store error."""


class SignalHistoryStore:
    """Durable signal history for Phase 4B+ — Postgres SoT (offline SQLite when SoT off)."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_signal_db_path(db_path)
        self._owner = resolve_sot_owner_user_id()
        self._engine = create_agent_engine(db_path if not supabase_sot_enabled() else None)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()
        self._ensure_outbox_table()
        self._ensure_risk_row()

    def _session(self) -> Session:
        return self._Session()

    def _ensure_risk_row(self) -> None:
        with self._lock:
            session = self._session()
            try:
                row = session.get(SignalDayRiskStateRow, self._owner)
                if row is None:
                    session.add(
                        SignalDayRiskStateRow(
                            owner_user_id=self._owner,
                            day_key="",
                            hypothetical_day_pnl=0.0,
                            last_signal_key="",
                            last_signal_ms=0,
                            halted=False,
                            seen_keys_json=[],
                            updated_at_ms=0,
                            corrupt=False,
                        )
                    )
                    session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"schema_init_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def schema_version(self) -> int:
        return _SCHEMA_VERSION

    def persist_decision_and_risk(
        self,
        decision: CoordinatorDecision,
        state: SignalRiskState,
        *,
        now_ms: int,
        checkpoint: CheckpointWrite | None = None,
        outbox_payload: dict[str, Any] | None = None,
        enqueue_outbox: bool = True,
    ) -> bool:
        inserted = False
        public = sanitize_public_json(decision.to_public_dict())
        indicators: dict[str, Any] = {}
        for c in public.get("contributions") or []:
            if isinstance(c, dict) and c.get("indicators"):
                indicators[str(c.get("agent_id"))] = c["indicators"]
        decided_at = datetime.fromtimestamp(decision.timestamp_ms / 1000.0, tz=timezone.utc)
        keys = sorted(state.seen_keys)[-500:]
        fail_after = getattr(self, "_test_fail_after", None)
        with self._lock:
            session = self._session()
            try:
                hist = SignalHistoryOrm(
                    owner_user_id=self._owner,
                    decision_id=decision.decision_id,
                    idempotent_key=decision.idempotent_key,
                    correlation_id=decision.correlation_id,
                    timestamp_ms=int(decision.timestamp_ms),
                    decided_at=decided_at,
                    symbol=decision.symbol,
                    category=decision.category,
                    interval=decision.interval,
                    strategy_version=decision.strategy_version,
                    config_hash=decision.config_hash,
                    action=decision.action.value,
                    signal_strength=float(decision.signal_strength),
                    directional_conviction=float(decision.directional_conviction),
                    market_quality=float(decision.market_quality),
                    risk_verdict=decision.risk.verdict.value,
                    source_mode=decision.source_mode,
                    explanation=decision.explanation[:2000],
                    reason_codes=public.get("reason_codes") or [],
                    risk_json=public.get("risk") or {},
                    levels_json=public.get("levels") or {},
                    market_json=public.get("market") or {},
                    indicators_json=indicators,
                )
                try:
                    session.add(hist)
                    session.flush()
                    inserted = True
                except IntegrityError:
                    session.rollback()
                    inserted = False
                    hist = session.scalar(
                        select(SignalHistoryOrm).where(
                            SignalHistoryOrm.owner_user_id == self._owner,
                            SignalHistoryOrm.decision_id == decision.decision_id,
                        )
                    )
                    if hist is None:
                        raise SignalHistoryStoreError("persist_atomic_failed:integrity")
                    session = self._session()
                if fail_after == "decision":
                    raise SignalHistoryStoreError("persist_atomic_failed:injected_decision")
                self._upsert_risk(session, state, now_ms=now_ms, keys=keys)
                if fail_after == "risk":
                    raise SignalHistoryStoreError("persist_atomic_failed:injected_risk")
                if inserted and hist is not None:
                    self._upsert_contributions(session, hist, public)
                if fail_after == "outbox":
                    raise SignalHistoryStoreError("persist_atomic_failed:injected_outbox")
                if checkpoint is not None:
                    cp_decision_id = checkpoint.decision_id or decision.decision_id
                    self._upsert_checkpoint(
                        session,
                        checkpoint=checkpoint,
                        decision_id=cp_decision_id,
                        now_ms=now_ms,
                    )
                if fail_after == "checkpoint":
                    raise SignalHistoryStoreError("persist_atomic_failed:injected_checkpoint")
                if enqueue_outbox and outbox_payload is not None and inserted:
                    self._insert_outbox(
                        session,
                        event_id=str(decision.decision_id),
                        event_type="signal_decision",
                        payload=outbox_payload,
                        now_ms=now_ms,
                    )
                session.commit()
                return inserted
            except SignalHistoryStoreError:
                session.rollback()
                raise
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(
                    f"persist_atomic_failed:{type(exc).__name__}"
                ) from exc
            finally:
                session.close()

    def _upsert_contributions(
        self, session: Session, hist: SignalHistoryOrm, public: dict[str, Any]
    ) -> None:
        for c in public.get("contributions") or []:
            if not isinstance(c, dict):
                continue
            agent_id = str(c.get("agent_id") or "")
            if not agent_id:
                continue
            row = SignalAgentContributionRow(
                owner_user_id=self._owner,
                signal_id=hist.id,
                decision_id=hist.decision_id,
                agent_id=agent_id,
                agent_version=str(c.get("agent_version") or ""),
                bias=str(c.get("bias") or ""),
                confidence=float(c.get("confidence") or 0.0),
                reason_codes=c.get("reason_codes") or [],
                explanation=str(c.get("explanation") or "")[:2000],
                indicators=c.get("indicators") or {},
                timed_out=bool(c.get("timed_out")),
                error=c.get("error"),
            )
            try:
                session.merge(row)
            except IntegrityError:
                pass

    def _upsert_risk(
        self, session: Session, state: SignalRiskState, *, now_ms: int, keys: list[str]
    ) -> None:
        session.execute(
            update(SignalDayRiskStateRow)
            .where(SignalDayRiskStateRow.owner_user_id == self._owner)
            .values(
                day_key=state.day_key,
                hypothetical_day_pnl=float(state.hypothetical_day_pnl),
                last_signal_key=state.last_signal_key,
                last_signal_ms=int(state.last_signal_ms),
                halted=bool(state.halted),
                seen_keys_json=keys,
                updated_at_ms=int(now_ms),
                corrupt=False,
            )
        )

    def _upsert_checkpoint(
        self,
        session: Session,
        *,
        checkpoint: CheckpointWrite,
        decision_id: str | None,
        now_ms: int,
    ) -> None:
        existing = session.scalar(
            select(SchedulerEvaluationHistoryRow).where(
                SchedulerEvaluationHistoryRow.owner_user_id == self._owner,
                SchedulerEvaluationHistoryRow.eval_key == checkpoint.eval_key,
            )
        )
        if existing is None:
            session.add(
                SchedulerEvaluationHistoryRow(
                    owner_user_id=self._owner,
                    eval_key=checkpoint.eval_key,
                    strategy_version=checkpoint.strategy_version,
                    category=checkpoint.category,
                    symbol=checkpoint.symbol.upper(),
                    interval=checkpoint.interval,
                    candle_start_ms=int(checkpoint.candle_start_ms),
                    candle_close_ms=int(checkpoint.candle_close_ms),
                    decision_id=decision_id,
                    status=checkpoint.status,
                    updated_at_ms=int(now_ms),
                )
            )
        else:
            existing.decision_id = decision_id
            existing.status = checkpoint.status
            existing.updated_at_ms = int(now_ms)

    def record_decision(self, decision: CoordinatorDecision) -> bool:
        return self.persist_decision_and_risk(
            decision, SignalRiskState(), now_ms=int(decision.timestamp_ms), enqueue_outbox=False
        )

    def list_signals(
        self,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        action: str | None = None,
        strategy_version: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalHistoryRowView]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        with self._lock:
            session = self._session()
            try:
                stmt = select(SignalHistoryOrm).where(
                    SignalHistoryOrm.owner_user_id == self._owner
                )
                if symbol:
                    stmt = stmt.where(SignalHistoryOrm.symbol == symbol.upper())
                if interval:
                    stmt = stmt.where(SignalHistoryOrm.interval == interval)
                if action:
                    stmt = stmt.where(SignalHistoryOrm.action == action.upper())
                if strategy_version:
                    stmt = stmt.where(SignalHistoryOrm.strategy_version == strategy_version)
                stmt = stmt.order_by(
                    SignalHistoryOrm.timestamp_ms.desc(), SignalHistoryOrm.id.desc()
                ).limit(limit).offset(offset)
                rows = session.scalars(stmt).all()
                return [self._to_view(session, r) for r in rows]
            finally:
                session.close()

    def get_decision(self, decision_id: str) -> SignalHistoryRowView | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(SignalHistoryOrm).where(
                        SignalHistoryOrm.owner_user_id == self._owner,
                        SignalHistoryOrm.decision_id == decision_id,
                    )
                )
                return self._to_view(session, row) if row else None
            finally:
                session.close()

    def analytics(self) -> dict[str, Any]:
        with self._lock:
            session = self._session()
            try:
                total = session.scalar(
                    select(func.count())
                    .select_from(SignalHistoryOrm)
                    .where(SignalHistoryOrm.owner_user_id == self._owner)
                )
                by_action = {
                    r[0]: r[1]
                    for r in session.execute(
                        select(SignalHistoryOrm.action, func.count())
                        .where(SignalHistoryOrm.owner_user_id == self._owner)
                        .group_by(SignalHistoryOrm.action)
                    )
                }
                recent_rows = session.scalars(
                    select(SignalHistoryOrm)
                    .where(SignalHistoryOrm.owner_user_id == self._owner)
                    .order_by(SignalHistoryOrm.timestamp_ms.desc())
                    .limit(20)
                ).all()
                recent = [self._to_view(session, r).__dict__ for r in recent_rows]
                return {
                    "total_signals": int(total or 0),
                    "by_action": by_action,
                    "by_symbol_interval": [],
                    "risk_veto_or_blocked": 0,
                    "agent_disagreement": 0,
                    "by_strategy_version": [],
                    "recent_timeline": recent,
                    "metrics_note": (
                        "No win-rate or profit metrics — outcome evaluation not in Phase 4B/4C scope."
                    ),
                }
            finally:
                session.close()

    def load_risk_state(self) -> SignalRiskState:
        with self._lock:
            session = self._session()
            try:
                row = session.get(SignalDayRiskStateRow, self._owner)
                if row is None:
                    raise SignalHistoryStoreError("paper_risk_state_missing")
                if row.corrupt:
                    state = SignalRiskState(halted=True, day_key=str(row.day_key or ""))
                    state.hypothetical_day_pnl = float(row.hypothetical_day_pnl or 0)
                    return state
                keys_raw = row.seen_keys_json or []
                if not isinstance(keys_raw, list):
                    row.corrupt = True
                    row.halted = True
                    session.commit()
                    raise SignalHistoryStoreError("paper_risk_state_corrupt")
                seen = {str(k) for k in keys_raw if isinstance(k, str)}
                return SignalRiskState(
                    day_key=str(row.day_key or ""),
                    hypothetical_day_pnl=float(row.hypothetical_day_pnl or 0),
                    last_signal_key=str(row.last_signal_key or ""),
                    last_signal_ms=int(row.last_signal_ms or 0),
                    halted=bool(row.halted),
                    seen_keys=seen,
                )
            finally:
                session.close()

    def save_risk_state(self, state: SignalRiskState, *, now_ms: int) -> None:
        keys = sorted(state.seen_keys)[-500:]
        with self._lock:
            session = self._session()
            try:
                self._upsert_risk(session, state, now_ms=now_ms, keys=keys)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"save_risk_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def mark_risk_corrupt(self) -> None:
        with self._lock:
            session = self._session()
            try:
                session.execute(
                    update(SignalDayRiskStateRow)
                    .where(SignalDayRiskStateRow.owner_user_id == self._owner)
                    .values(corrupt=True, halted=True)
                )
                session.commit()
            finally:
                session.close()

    def has_checkpoint(self, eval_key: str) -> bool:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(SchedulerEvaluationHistoryRow).where(
                        SchedulerEvaluationHistoryRow.owner_user_id == self._owner,
                        SchedulerEvaluationHistoryRow.eval_key == eval_key,
                        SchedulerEvaluationHistoryRow.status == "completed",
                    )
                )
                return row is not None
            finally:
                session.close()

    def last_checkpoint_close_ms(
        self,
        *,
        strategy_version: str,
        category: str,
        symbol: str,
        interval: str,
    ) -> int | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(SchedulerEvaluationHistoryRow.candle_close_ms)
                    .where(
                        SchedulerEvaluationHistoryRow.owner_user_id == self._owner,
                        SchedulerEvaluationHistoryRow.strategy_version == strategy_version,
                        SchedulerEvaluationHistoryRow.category == category,
                        SchedulerEvaluationHistoryRow.symbol == symbol.upper(),
                        SchedulerEvaluationHistoryRow.interval == interval,
                        SchedulerEvaluationHistoryRow.status == "completed",
                    )
                    .order_by(SchedulerEvaluationHistoryRow.candle_close_ms.desc())
                    .limit(1)
                )
                return int(row) if row is not None else None
            finally:
                session.close()

    def mark_checkpoint(
        self,
        *,
        eval_key: str,
        strategy_version: str,
        category: str,
        symbol: str,
        interval: str,
        candle_start_ms: int,
        candle_close_ms: int,
        decision_id: str | None,
        status: str,
        now_ms: int,
    ) -> None:
        cp = CheckpointWrite(
            eval_key=eval_key,
            strategy_version=strategy_version,
            category=category,
            symbol=symbol,
            interval=interval,
            candle_start_ms=candle_start_ms,
            candle_close_ms=candle_close_ms,
            decision_id=decision_id,
            status=status,
        )
        with self._lock:
            session = self._session()
            try:
                self._upsert_checkpoint(
                    session, checkpoint=cp, decision_id=decision_id, now_ms=now_ms
                )
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"checkpoint_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def try_acquire_scheduler_lock(
        self,
        *,
        owner_id: str,
        hostname: str,
        pid: int,
        now_ms: int,
        lease_ms: int = 30_000,
    ) -> bool:
        lease_until = int(now_ms) + max(5_000, int(lease_ms))
        with self._lock:
            session = self._session()
            try:
                row = session.get(SchedulerLockRow, self._owner)
                if row is None:
                    session.add(
                        SchedulerLockRow(
                            owner_user_id=self._owner,
                            owner_id=owner_id,
                            lease_until_ms=lease_until,
                            hostname=hostname,
                            pid=int(pid),
                            updated_at_ms=int(now_ms),
                        )
                    )
                    session.commit()
                    return True
                if row.owner_id == owner_id or int(row.lease_until_ms) <= int(now_ms):
                    row.owner_id = owner_id
                    row.lease_until_ms = lease_until
                    row.hostname = hostname
                    row.pid = int(pid)
                    row.updated_at_ms = int(now_ms)
                    session.commit()
                    return True
                session.rollback()
                return False
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"scheduler_lock_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def release_scheduler_lock(self, *, owner_id: str, now_ms: int) -> None:
        with self._lock:
            session = self._session()
            try:
                session.execute(
                    update(SchedulerLockRow)
                    .where(
                        SchedulerLockRow.owner_user_id == self._owner,
                        SchedulerLockRow.owner_id == owner_id,
                    )
                    .values(lease_until_ms=0, updated_at_ms=int(now_ms))
                )
                session.commit()
            finally:
                session.close()

    def write_audit(self, event_type: str, detail: dict[str, Any], *, now_ms: int) -> None:
        safe = sanitize_public_json(detail)
        with self._lock:
            session = self._session()
            try:
                nxt = session.scalar(
                    select(func.max(SchedulerAuditRow.local_audit_id)).where(
                        SchedulerAuditRow.owner_user_id == self._owner
                    )
                )
                session.add(
                    SchedulerAuditRow(
                        owner_user_id=self._owner,
                        local_audit_id=int(nxt or 0) + 1,
                        event_type=event_type[:64],
                        detail_json=safe,
                        created_at_ms=int(now_ms),
                    )
                )
                session.commit()
                stale = session.scalars(
                    select(SchedulerAuditRow)
                    .where(SchedulerAuditRow.owner_user_id == self._owner)
                    .order_by(SchedulerAuditRow.created_at_ms.desc())
                    .offset(2000)
                ).all()
                for old in stale:
                    session.delete(old)
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"audit_write_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def _ensure_outbox_table(self) -> None:
        if self._engine.dialect.name != "sqlite":
            return
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS cloud_sync_outbox (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_user_id TEXT NOT NULL,
                        event_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        lease_until_ms INTEGER,
                        last_error TEXT,
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        UNIQUE (owner_user_id, event_id)
                    )
                    """
                )
            )

    def _insert_outbox(
        self,
        session: Session,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        now_ms: int,
    ) -> bool:
        if self._engine.dialect.name != "sqlite":
            # The signal row is already the durable Postgres write. This mirror
            # queue exists only for the SQLite-to-cloud worker.
            return False
        result = session.execute(
            text(
                """
                INSERT OR IGNORE INTO cloud_sync_outbox (
                    owner_user_id, event_id, event_type, payload_json, status,
                    attempts, created_at_ms, updated_at_ms
                ) VALUES (
                    :owner, :event_id, :event_type, :payload, 'PENDING',
                    0, :now_ms, :now_ms
                )
                """
            ),
            {
                "owner": str(self._owner),
                "event_id": event_id,
                "event_type": event_type,
                "payload": json.dumps(payload, sort_keys=True, default=str),
                "now_ms": int(now_ms),
            },
        )
        return int(result.rowcount or 0) > 0

    def _require_sqlite_outbox(self) -> None:
        if self.outbox_backend() != "sqlite":
            raise SignalHistoryStoreError(
                "outbox_not_applicable_signal_history_is_authoritative"
            )

    def _mark_outbox(
        self, *, event_id: str, status: str, now_ms: int, error: str | None
    ) -> None:
        self._require_sqlite_outbox()
        with self._lock:
            session = self._session()
            try:
                session.execute(
                    text(
                        """
                        UPDATE cloud_sync_outbox
                        SET status = :status, last_error = :error, updated_at_ms = :now,
                            lease_until_ms = NULL
                        WHERE owner_user_id = :owner AND event_id = :event_id
                        """
                    ),
                    {
                        "status": status,
                        "error": (error or "")[:500],
                        "now": int(now_ms),
                        "owner": str(self._owner),
                        "event_id": event_id,
                    },
                )
                session.commit()
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"outbox_mark_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def outbox_backend(self) -> str:
        """SQLite keeps a mirror queue. Postgres signal_history is the durable row."""
        if self._engine.dialect.name == "sqlite":
            return "sqlite"
        return "not_applicable"

    def enqueue_cloud_outbox(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
        now_ms: int,
    ) -> bool:
        if self.outbox_backend() != "sqlite":
            raise SignalHistoryStoreError(
                "outbox_not_applicable_signal_history_is_authoritative"
            )
        with self._lock:
            session = self._session()
            try:
                inserted = self._insert_outbox(
                    session,
                    event_id=event_id,
                    event_type=event_type,
                    payload=payload,
                    now_ms=now_ms,
                )
                session.commit()
                return inserted
            except SQLAlchemyError as exc:
                session.rollback()
                raise SignalHistoryStoreError(f"outbox_enqueue_failed:{type(exc).__name__}") from exc
            finally:
                session.close()

    def outbox_stats(self) -> dict[str, Any]:
        counts = {
            "PENDING": 0,
            "IN_PROGRESS": 0,
            "RETRY_WAIT": 0,
            "FAILED": 0,
            "PERMANENT_FAILURE": 0,
            "SYNCED": 0,
        }
        if self._engine.dialect.name == "sqlite":
            with self._lock:
                session = self._session()
                try:
                    rows = session.execute(
                        text(
                            "SELECT status, COUNT(*) AS n FROM cloud_sync_outbox "
                            "WHERE owner_user_id = :owner GROUP BY status"
                        ),
                        {"owner": str(self._owner)},
                    ).all()
                    for status, count in rows:
                        counts[str(status)] = int(count)
                except SQLAlchemyError:
                    session.rollback()
                finally:
                    session.close()
        return {
            "pending": counts["PENDING"],
            "in_progress": counts["IN_PROGRESS"],
            "retry_wait": counts["RETRY_WAIT"],
            "failed": counts["FAILED"],
            "permanent_failure": counts["PERMANENT_FAILURE"],
            "synced": counts["SYNCED"],
            "by_status": counts,
            "last_synced_at_ms": None,
            "cloud_confirmed_only_when_synced": True,
            "note": (
                "SQLite outbox is a mirror queue. Postgres signal_history is authoritative "
                "and has no second outbox. SYNCED is set only after cloud commit."
            ),
            "backend": self.outbox_backend(),
        }

    def recover_stale_in_progress(self, *, now_ms: int) -> int:
        self._require_sqlite_outbox()
        with self._lock:
            session = self._session()
            try:
                result = session.execute(
                    text(
                        "UPDATE cloud_sync_outbox SET status = 'PENDING', lease_until_ms = NULL, "
                        "updated_at_ms = :now WHERE owner_user_id = :owner AND status = 'IN_PROGRESS' "
                        "AND lease_until_ms IS NOT NULL AND lease_until_ms < :now"
                    ),
                    {"owner": str(self._owner), "now": int(now_ms)},
                )
                session.commit()
                return int(result.rowcount or 0)
            except SQLAlchemyError:
                session.rollback()
                return 0
            finally:
                session.close()

    def claim_outbox_batch(
        self, *, now_ms: int, limit: int = 25, lease_ms: int = 60_000
    ) -> list[dict[str, Any]]:
        self._require_sqlite_outbox()
        owner = str(self._owner)
        until = int(now_ms) + int(lease_ms)
        with self._lock:
            session = self._session()
            try:
                ids = session.execute(
                    text(
                        "SELECT id FROM cloud_sync_outbox WHERE owner_user_id = :owner "
                        "AND status IN ('PENDING', 'RETRY_WAIT') "
                        "ORDER BY id ASC LIMIT :limit"
                    ),
                    {"owner": owner, "limit": int(limit)},
                ).scalars().all()
                if not ids:
                    return []
                session.execute(
                    text(
                        "UPDATE cloud_sync_outbox SET status = 'IN_PROGRESS', "
                        "lease_until_ms = :until, attempts = attempts + 1, updated_at_ms = :now "
                        "WHERE id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"until": until, "now": int(now_ms), "ids": list(ids)},
                )
                rows = session.execute(
                    text(
                        "SELECT event_id, event_type, payload_json, attempts FROM cloud_sync_outbox "
                        "WHERE id IN :ids"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(ids)},
                ).all()
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                return []
            finally:
                session.close()
        claimed: list[dict[str, Any]] = []
        for event_id, event_type, payload_json, attempts in rows:
            try:
                payload = json.loads(payload_json or "{}")
            except json.JSONDecodeError:
                payload = {}
            claimed.append(
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "payload": payload,
                    "attempts": int(attempts or 0),
                }
            )
        return claimed

    def list_outbox_pending(self, *, now_ms: int, limit: int = 50) -> list[dict[str, Any]]:
        del now_ms
        self._require_sqlite_outbox()
        with self._lock:
            session = self._session()
            try:
                rows = session.execute(
                    text(
                        "SELECT event_id, event_type, payload_json FROM cloud_sync_outbox "
                        "WHERE owner_user_id = :owner AND status = 'PENDING' "
                        "ORDER BY id ASC LIMIT :limit"
                    ),
                    {"owner": str(self._owner), "limit": int(limit)},
                ).all()
            finally:
                session.close()
        return [
            {"event_id": event_id, "event_type": event_type, "payload_json": payload}
            for event_id, event_type, payload in rows
        ]

    def mark_outbox_synced(self, *, event_id: str, now_ms: int) -> None:
        self._mark_outbox(event_id=event_id, status="SYNCED", now_ms=now_ms, error=None)

    def mark_outbox_failed(
        self,
        *,
        event_id: str,
        error: str,
        now_ms: int,
        backoff_ms: int,
        permanent: bool = False,
    ) -> None:
        del backoff_ms
        self._mark_outbox(
            event_id=event_id,
            status="PERMANENT_FAILURE" if permanent else "RETRY_WAIT",
            now_ms=now_ms,
            error=error,
        )

    def recent_audit(self, *, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self._lock:
            session = self._session()
            try:
                rows = session.scalars(
                    select(SchedulerAuditRow)
                    .where(SchedulerAuditRow.owner_user_id == self._owner)
                    .order_by(SchedulerAuditRow.created_at_ms.desc())
                    .limit(limit)
                ).all()
                return [
                    {
                        "event_type": r.event_type,
                        "detail": r.detail_json if isinstance(r.detail_json, dict) else {},
                        "created_at_ms": int(r.created_at_ms),
                    }
                    for r in rows
                ]
            finally:
                session.close()

    def _to_view(self, session: Session, row: SignalHistoryOrm) -> SignalHistoryRowView:
        contribs = session.scalars(
            select(SignalAgentContributionRow).where(
                SignalAgentContributionRow.signal_id == row.id,
                SignalAgentContributionRow.owner_user_id == self._owner,
            )
        ).all()
        contributions = [
            {
                "agent_id": c.agent_id,
                "agent_version": c.agent_version,
                "bias": c.bias,
                "confidence": c.confidence,
                "reason_codes": c.reason_codes,
                "explanation": c.explanation,
                "indicators": c.indicators,
                "timed_out": c.timed_out,
                "error": c.error,
            }
            for c in contribs
        ]
        return SignalHistoryRowView(
            decision_id=row.decision_id,
            idempotent_key=row.idempotent_key,
            correlation_id=row.correlation_id,
            timestamp_ms=int(row.timestamp_ms),
            symbol=row.symbol,
            category=row.category,
            interval=row.interval,
            strategy_version=row.strategy_version,
            config_hash=row.config_hash,
            action=row.action,
            signal_strength=float(row.signal_strength),
            directional_conviction=float(row.directional_conviction),
            market_quality=float(row.market_quality),
            risk_verdict=row.risk_verdict,
            source_mode=row.source_mode,
            explanation=row.explanation,
            reason_codes=list(row.reason_codes or []),
            contributions=contributions,
            risk=dict(row.risk_json or {}),
            levels=dict(row.levels_json or {}),
            market=dict(row.market_json or {}),
            indicators=dict(row.indicators_json or {}),
        )
