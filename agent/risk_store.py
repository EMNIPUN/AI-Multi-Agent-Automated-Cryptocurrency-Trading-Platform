"""Account risk persistence (Postgres SoT)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from agent.risk_modes import AccountRiskMode
from apps.api.app.persistence.ledger_models import AccountRiskSnapshotRow
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AccountRiskRecord:
    env_scope: str
    account_fp: str
    risk_date: str
    mode: AccountRiskMode
    start_equity: float | None
    latest_equity: float | None
    equity_confirmed: bool
    realized_pnl: float | None
    unrealized_pnl: float | None
    daily_loss_pct_threshold: float
    daily_loss_pct_current: float | None
    emergency_halt: bool
    halt_reason: str
    recovery_required: bool
    version: int
    created_at: str
    updated_at: str


class RiskStoreError(RuntimeError):
    """Raised when risk persistence is unavailable or corrupt — fail closed."""


class RiskStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._owner = resolve_sot_owner_user_id()
        self._engine = create_agent_engine(db_path)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()

    def _row_to_record(self, row: AccountRiskSnapshotRow) -> AccountRiskRecord:
        try:
            mode = AccountRiskMode(row.mode)
        except ValueError as exc:
            raise RiskStoreError(f"corrupt risk mode: {row.mode}") from exc
        return AccountRiskRecord(
            env_scope=row.env_scope,
            account_fp=row.account_fp,
            risk_date=row.risk_date,
            mode=mode,
            start_equity=row.start_equity,
            latest_equity=row.latest_equity,
            equity_confirmed=bool(row.equity_confirmed),
            realized_pnl=row.realized_pnl,
            unrealized_pnl=row.unrealized_pnl,
            daily_loss_pct_threshold=float(row.daily_loss_pct_threshold),
            daily_loss_pct_current=row.daily_loss_pct_current,
            emergency_halt=bool(row.emergency_halt),
            halt_reason=row.halt_reason or "",
            recovery_required=bool(row.recovery_required),
            version=int(row.version),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def get(
        self, env_scope: str, account_fp: str, risk_date: str
    ) -> AccountRiskRecord | None:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(AccountRiskSnapshotRow).where(
                        AccountRiskSnapshotRow.owner_user_id == self._owner,
                        AccountRiskSnapshotRow.env_scope == env_scope,
                        AccountRiskSnapshotRow.account_fp == account_fp,
                        AccountRiskSnapshotRow.risk_date == risk_date,
                    )
                )
                return self._row_to_record(row) if row else None
            except SQLAlchemyError as exc:
                raise RiskStoreError(f"risk store read failed: {type(exc).__name__}") from exc
            finally:
                session.close()

    def latest_emergency(
        self, env_scope: str, account_fp: str
    ) -> AccountRiskRecord | None:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(AccountRiskSnapshotRow)
                    .where(
                        AccountRiskSnapshotRow.owner_user_id == self._owner,
                        AccountRiskSnapshotRow.env_scope == env_scope,
                        AccountRiskSnapshotRow.account_fp == account_fp,
                        AccountRiskSnapshotRow.emergency_halt.is_(True),
                    )
                    .order_by(AccountRiskSnapshotRow.risk_date.desc())
                    .limit(1)
                )
                return self._row_to_record(row) if row else None
            except SQLAlchemyError as exc:
                raise RiskStoreError(
                    f"risk store emergency lookup failed: {type(exc).__name__}"
                ) from exc
            finally:
                session.close()

    def insert_new_day(self, record: AccountRiskRecord) -> AccountRiskRecord:
        with self._lock:
            session = self._Session()
            try:
                existing = session.scalar(
                    select(AccountRiskSnapshotRow).where(
                        AccountRiskSnapshotRow.owner_user_id == self._owner,
                        AccountRiskSnapshotRow.env_scope == record.env_scope,
                        AccountRiskSnapshotRow.account_fp == record.account_fp,
                        AccountRiskSnapshotRow.risk_date == record.risk_date,
                    )
                )
                if existing is not None:
                    return self._row_to_record(existing)
                session.add(
                    AccountRiskSnapshotRow(
                        owner_user_id=self._owner,
                        env_scope=record.env_scope,
                        account_fp=record.account_fp,
                        risk_date=record.risk_date,
                        mode=record.mode.value,
                        start_equity=record.start_equity,
                        latest_equity=record.latest_equity,
                        equity_confirmed=record.equity_confirmed,
                        realized_pnl=record.realized_pnl,
                        unrealized_pnl=record.unrealized_pnl,
                        daily_loss_pct_threshold=record.daily_loss_pct_threshold,
                        daily_loss_pct_current=record.daily_loss_pct_current,
                        emergency_halt=record.emergency_halt,
                        halt_reason=record.halt_reason,
                        recovery_required=record.recovery_required,
                        version=record.version,
                        created_at=record.created_at,
                        updated_at=record.updated_at,
                    )
                )
                session.commit()
                return record
            except IntegrityError as exc:
                session.rollback()
                raise RiskStoreError(f"risk store insert failed: {type(exc).__name__}") from exc
            except SQLAlchemyError as exc:
                session.rollback()
                raise RiskStoreError(f"risk store insert failed: {type(exc).__name__}") from exc
            finally:
                session.close()

    def update_cas(self, expected: AccountRiskRecord, new: AccountRiskRecord) -> AccountRiskRecord:
        if (
            expected.env_scope != new.env_scope
            or expected.account_fp != new.account_fp
            or expected.risk_date != new.risk_date
        ):
            raise RiskStoreError("CAS key mismatch")
        with self._lock:
            session = self._Session()
            try:
                result = session.execute(
                    update(AccountRiskSnapshotRow)
                    .where(
                        AccountRiskSnapshotRow.owner_user_id == self._owner,
                        AccountRiskSnapshotRow.env_scope == expected.env_scope,
                        AccountRiskSnapshotRow.account_fp == expected.account_fp,
                        AccountRiskSnapshotRow.risk_date == expected.risk_date,
                        AccountRiskSnapshotRow.version == expected.version,
                    )
                    .values(
                        mode=new.mode.value,
                        start_equity=new.start_equity,
                        latest_equity=new.latest_equity,
                        equity_confirmed=new.equity_confirmed,
                        realized_pnl=new.realized_pnl,
                        unrealized_pnl=new.unrealized_pnl,
                        daily_loss_pct_threshold=new.daily_loss_pct_threshold,
                        daily_loss_pct_current=new.daily_loss_pct_current,
                        emergency_halt=new.emergency_halt,
                        halt_reason=new.halt_reason,
                        recovery_required=new.recovery_required,
                        version=expected.version + 1,
                        updated_at=utc_now_iso(),
                    )
                )
                if result.rowcount != 1:
                    session.rollback()
                    raise RiskStoreError("concurrent risk update conflict")
                session.commit()
                refreshed = session.scalar(
                    select(AccountRiskSnapshotRow).where(
                        AccountRiskSnapshotRow.owner_user_id == self._owner,
                        AccountRiskSnapshotRow.env_scope == expected.env_scope,
                        AccountRiskSnapshotRow.account_fp == expected.account_fp,
                        AccountRiskSnapshotRow.risk_date == expected.risk_date,
                    )
                )
                assert refreshed is not None
                return self._row_to_record(refreshed)
            except RiskStoreError:
                raise
            except SQLAlchemyError as exc:
                session.rollback()
                raise RiskStoreError(f"risk store update failed: {type(exc).__name__}") from exc
            finally:
                session.close()
