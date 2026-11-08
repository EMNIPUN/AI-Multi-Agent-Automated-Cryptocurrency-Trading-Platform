"""Automation execution audit buffer — Postgres SoT."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.api.app.persistence.ledger_models import (
    AutomationExecEventRow,
    AutomationExecIntentRow,
)
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
)


class ExecStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionIntentRow:
    intent_id: str
    client_order_id: str
    decision_id: str | None
    symbol: str
    category: str
    side: str
    qty: str
    state: str
    exchange_order_id: str | None
    stop_loss: str | None
    take_profit: str | None
    protection_state: str
    payload: dict[str, Any]


class AutomationExecStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._owner = resolve_sot_owner_user_id()
        self._engine = create_agent_engine(db_path)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()

    def insert_intent(self, row: ExecutionIntentRow, *, now_ms: int) -> bool:
        with self._lock:
            session = self._Session()
            try:
                session.add(
                    AutomationExecIntentRow(
                        owner_user_id=self._owner,
                        intent_id=row.intent_id,
                        client_order_id=row.client_order_id,
                        decision_id=row.decision_id,
                        symbol=row.symbol,
                        category=row.category,
                        side=row.side,
                        qty=row.qty,
                        state=row.state,
                        exchange_order_id=row.exchange_order_id,
                        stop_loss=row.stop_loss,
                        take_profit=row.take_profit,
                        protection_state=row.protection_state,
                        payload_json=row.payload,
                        created_at_ms=int(now_ms),
                        updated_at_ms=int(now_ms),
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False
            except SQLAlchemyError as exc:
                session.rollback()
                raise ExecStoreError(str(exc)) from exc
            finally:
                session.close()

    def update_intent(
        self,
        intent_id: str,
        *,
        state: str | None = None,
        exchange_order_id: str | None = None,
        protection_state: str | None = None,
        now_ms: int,
    ) -> None:
        values: dict[str, Any] = {"updated_at_ms": int(now_ms)}
        if state is not None:
            values["state"] = state
        if exchange_order_id is not None:
            values["exchange_order_id"] = exchange_order_id
        if protection_state is not None:
            values["protection_state"] = protection_state
        with self._lock:
            session = self._Session()
            try:
                session.execute(
                    update(AutomationExecIntentRow)
                    .where(
                        AutomationExecIntentRow.owner_user_id == self._owner,
                        AutomationExecIntentRow.intent_id == intent_id,
                    )
                    .values(**values)
                )
                session.commit()
            finally:
                session.close()

    def get_by_client_order_id(self, client_order_id: str) -> ExecutionIntentRow | None:
        with self._lock:
            session = self._Session()
            try:
                r = session.scalar(
                    select(AutomationExecIntentRow).where(
                        AutomationExecIntentRow.owner_user_id == self._owner,
                        AutomationExecIntentRow.client_order_id == client_order_id,
                    )
                )
                return self._row(r) if r else None
            finally:
                session.close()

    def append_event(
        self, *, intent_id: str, event_type: str, detail: dict[str, Any], now_ms: int
    ) -> None:
        with self._lock:
            session = self._Session()
            try:
                session.add(
                    AutomationExecEventRow(
                        owner_user_id=self._owner,
                        intent_id=intent_id,
                        event_type=event_type[:64],
                        detail_json=detail,
                        created_at_ms=int(now_ms),
                    )
                )
                session.commit()
            finally:
                session.close()

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            session = self._Session()
            try:
                by_state = {
                    str(r[0]): int(r[1])
                    for r in session.execute(
                        select(AutomationExecIntentRow.state, func.count())
                        .where(AutomationExecIntentRow.owner_user_id == self._owner)
                        .group_by(AutomationExecIntentRow.state)
                    )
                }
                pending = int(
                    by_state.get("SUBMISSION_PENDING", 0) + by_state.get("ACCEPTED", 0)
                )
                return {
                    "by_state": by_state,
                    "pending_or_accepted": pending,
                    "db_path": "supabase",
                    "ack_is_not_fill": True,
                }
            finally:
                session.close()

    @staticmethod
    def _row(r: AutomationExecIntentRow) -> ExecutionIntentRow:
        payload = r.payload_json if isinstance(r.payload_json, dict) else {}
        return ExecutionIntentRow(
            intent_id=r.intent_id,
            client_order_id=r.client_order_id,
            decision_id=r.decision_id,
            symbol=r.symbol,
            category=r.category,
            side=r.side,
            qty=r.qty,
            state=r.state,
            exchange_order_id=r.exchange_order_id,
            stop_loss=r.stop_loss,
            take_profit=r.take_profit,
            protection_state=r.protection_state,
            payload=payload,
        )
