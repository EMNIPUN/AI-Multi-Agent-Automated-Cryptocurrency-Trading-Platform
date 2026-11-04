"""SQLite persistence for account risk state (no secrets)."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from agent.risk_modes import AccountRiskMode

_DEFAULT_DB = Path("data") / "account_risk.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_risk_state (
    env_scope TEXT NOT NULL,
    account_fp TEXT NOT NULL,
    risk_date TEXT NOT NULL,
    mode TEXT NOT NULL,
    start_equity REAL,
    latest_equity REAL,
    equity_confirmed INTEGER NOT NULL DEFAULT 0,
    realized_pnl REAL,
    unrealized_pnl REAL,
    daily_loss_pct_threshold REAL NOT NULL,
    daily_loss_pct_current REAL,
    emergency_halt INTEGER NOT NULL DEFAULT 0,
    halt_reason TEXT NOT NULL DEFAULT '',
    recovery_required INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (env_scope, account_fp, risk_date)
);
CREATE INDEX IF NOT EXISTS idx_account_risk_updated
    ON account_risk_state (env_scope, account_fp, updated_at);
"""


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
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._lock = threading.RLock()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
        except OSError as exc:
            raise RiskStoreError(f"risk store unavailable: {type(exc).__name__}") from exc

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            return conn
        except sqlite3.Error as exc:
            raise RiskStoreError(f"risk store connect failed: {type(exc).__name__}") from exc

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
            except sqlite3.Error as exc:
                raise RiskStoreError(f"risk store schema failed: {type(exc).__name__}") from exc
            finally:
                conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> AccountRiskRecord:
        try:
            mode = AccountRiskMode(row["mode"])
        except ValueError as exc:
            raise RiskStoreError(f"corrupt risk mode: {row['mode']}") from exc
        return AccountRiskRecord(
            env_scope=row["env_scope"],
            account_fp=row["account_fp"],
            risk_date=row["risk_date"],
            mode=mode,
            start_equity=row["start_equity"],
            latest_equity=row["latest_equity"],
            equity_confirmed=bool(row["equity_confirmed"]),
            realized_pnl=row["realized_pnl"],
            unrealized_pnl=row["unrealized_pnl"],
            daily_loss_pct_threshold=float(row["daily_loss_pct_threshold"]),
            daily_loss_pct_current=row["daily_loss_pct_current"],
            emergency_halt=bool(row["emergency_halt"]),
            halt_reason=row["halt_reason"] or "",
            recovery_required=bool(row["recovery_required"]),
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get(
        self, env_scope: str, account_fp: str, risk_date: str
    ) -> AccountRiskRecord | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM account_risk_state
                    WHERE env_scope = ? AND account_fp = ? AND risk_date = ?
                    """,
                    (env_scope, account_fp, risk_date),
                ).fetchone()
                return self._row_to_record(row) if row else None
            except sqlite3.Error as exc:
                raise RiskStoreError(f"risk store read failed: {type(exc).__name__}") from exc
            finally:
                conn.close()

    def latest_emergency(
        self, env_scope: str, account_fp: str
    ) -> AccountRiskRecord | None:
        """Most recent row with emergency_halt for carry-forward across UTC days."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM account_risk_state
                    WHERE env_scope = ? AND account_fp = ? AND emergency_halt = 1
                    ORDER BY risk_date DESC
                    LIMIT 1
                    """,
                    (env_scope, account_fp),
                ).fetchone()
                return self._row_to_record(row) if row else None
            except sqlite3.Error as exc:
                raise RiskStoreError(
                    f"risk store emergency lookup failed: {type(exc).__name__}"
                ) from exc
            finally:
                conn.close()

    def insert_new_day(self, record: AccountRiskRecord) -> AccountRiskRecord:
        """Create today's row. Fails closed on conflict (never overwrite baseline)."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    """
                    SELECT * FROM account_risk_state
                    WHERE env_scope = ? AND account_fp = ? AND risk_date = ?
                    """,
                    (record.env_scope, record.account_fp, record.risk_date),
                ).fetchone()
                if existing is not None:
                    conn.execute("COMMIT")
                    return self._row_to_record(existing)
                conn.execute(
                    """
                    INSERT INTO account_risk_state (
                        env_scope, account_fp, risk_date, mode,
                        start_equity, latest_equity, equity_confirmed,
                        realized_pnl, unrealized_pnl,
                        daily_loss_pct_threshold, daily_loss_pct_current,
                        emergency_halt, halt_reason, recovery_required,
                        version, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.env_scope,
                        record.account_fp,
                        record.risk_date,
                        record.mode.value,
                        record.start_equity,
                        record.latest_equity,
                        1 if record.equity_confirmed else 0,
                        record.realized_pnl,
                        record.unrealized_pnl,
                        record.daily_loss_pct_threshold,
                        record.daily_loss_pct_current,
                        1 if record.emergency_halt else 0,
                        record.halt_reason,
                        1 if record.recovery_required else 0,
                        record.version,
                        record.created_at,
                        record.updated_at,
                    ),
                )
                conn.execute("COMMIT")
                return record
            except sqlite3.Error as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise RiskStoreError(f"risk store insert failed: {type(exc).__name__}") from exc
            finally:
                conn.close()

    def update_cas(self, expected: AccountRiskRecord, new: AccountRiskRecord) -> AccountRiskRecord:
        """
        Compare-and-swap on version. Raises RiskStoreError if lost the race
        or storage fails (callers must fail closed).
        """
        if (
            expected.env_scope != new.env_scope
            or expected.account_fp != new.account_fp
            or expected.risk_date != new.risk_date
        ):
            raise RiskStoreError("CAS key mismatch")
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    """
                    UPDATE account_risk_state SET
                        mode = ?,
                        start_equity = ?,
                        latest_equity = ?,
                        equity_confirmed = ?,
                        realized_pnl = ?,
                        unrealized_pnl = ?,
                        daily_loss_pct_threshold = ?,
                        daily_loss_pct_current = ?,
                        emergency_halt = ?,
                        halt_reason = ?,
                        recovery_required = ?,
                        version = version + 1,
                        updated_at = ?
                    WHERE env_scope = ? AND account_fp = ? AND risk_date = ?
                      AND version = ?
                    """,
                    (
                        new.mode.value,
                        new.start_equity,
                        new.latest_equity,
                        1 if new.equity_confirmed else 0,
                        new.realized_pnl,
                        new.unrealized_pnl,
                        new.daily_loss_pct_threshold,
                        new.daily_loss_pct_current,
                        1 if new.emergency_halt else 0,
                        new.halt_reason,
                        1 if new.recovery_required else 0,
                        utc_now_iso(),
                        expected.env_scope,
                        expected.account_fp,
                        expected.risk_date,
                        expected.version,
                    ),
                )
                if cur.rowcount != 1:
                    conn.execute("ROLLBACK")
                    raise RiskStoreError("concurrent risk update conflict")
                conn.execute("COMMIT")
                refreshed = conn.execute(
                    """
                    SELECT * FROM account_risk_state
                    WHERE env_scope = ? AND account_fp = ? AND risk_date = ?
                    """,
                    (expected.env_scope, expected.account_fp, expected.risk_date),
                ).fetchone()
                return self._row_to_record(refreshed)
            except RiskStoreError:
                raise
            except sqlite3.Error as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise RiskStoreError(f"risk store update failed: {type(exc).__name__}") from exc
            finally:
                conn.close()
