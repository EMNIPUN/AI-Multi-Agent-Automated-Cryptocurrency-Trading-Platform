"""Durable ledger of processed actionable signals — Postgres SoT."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from agent.order_intent import utc_now_iso
from apps.api.app.persistence.ledger_models import SignalLedgerEntryRow
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
)


@dataclass(frozen=True)
class ProcessedSignal:
    signal_id: str
    symbol: str
    category: str
    interval: str
    action: str
    candle_close_ms: int


class SignalLedger:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._owner = resolve_sot_owner_user_id()
        self._engine = create_agent_engine(db_path)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()

    def has_processed(self, env_scope: str, account_fp: str, signal_id: str) -> bool:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(SignalLedgerEntryRow).where(
                        SignalLedgerEntryRow.owner_user_id == self._owner,
                        SignalLedgerEntryRow.env_scope == env_scope,
                        SignalLedgerEntryRow.account_fp == account_fp,
                        SignalLedgerEntryRow.signal_id == signal_id,
                    )
                )
                return row is not None
            finally:
                session.close()

    def mark_processed(
        self,
        *,
        env_scope: str,
        account_fp: str,
        signal: ProcessedSignal,
    ) -> bool:
        with self._lock:
            session = self._Session()
            try:
                session.add(
                    SignalLedgerEntryRow(
                        owner_user_id=self._owner,
                        env_scope=env_scope,
                        account_fp=account_fp,
                        signal_id=signal.signal_id,
                        symbol=signal.symbol,
                        category=signal.category,
                        interval=signal.interval,
                        action=signal.action,
                        candle_close_ms=int(signal.candle_close_ms),
                        created_at=utc_now_iso(),
                    )
                )
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False
            except SQLAlchemyError:
                session.rollback()
                raise
            finally:
                session.close()
