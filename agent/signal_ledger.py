"""Durable ledger of processed actionable signals (BUY/SELL). HOLD is not stored."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from agent.order_intent import utc_now_iso

_DEFAULT_DB = Path("data") / "signal_ledger.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_signals (
    env_scope TEXT NOT NULL,
    account_fp TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    category TEXT NOT NULL,
    interval TEXT NOT NULL,
    action TEXT NOT NULL,
    candle_close_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (env_scope, account_fp, signal_id)
);
CREATE INDEX IF NOT EXISTS idx_processed_signals_symbol_close
    ON processed_signals (env_scope, account_fp, symbol, category, interval, candle_close_ms);
"""


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
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
            finally:
                conn.close()

    def has_processed(self, env_scope: str, account_fp: str, signal_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT 1 FROM processed_signals
                    WHERE env_scope = ? AND account_fp = ? AND signal_id = ?
                    """,
                    (env_scope, account_fp, signal_id),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def mark_processed(
        self,
        *,
        env_scope: str,
        account_fp: str,
        signal: ProcessedSignal,
    ) -> bool:
        """
        Insert signal id. Returns True if newly recorded, False if already present.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        """
                        INSERT INTO processed_signals (
                            env_scope, account_fp, signal_id, symbol, category,
                            interval, action, candle_close_ms, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            env_scope,
                            account_fp,
                            signal.signal_id,
                            signal.symbol,
                            signal.category,
                            signal.interval,
                            signal.action,
                            signal.candle_close_ms,
                            utc_now_iso(),
                        ),
                    )
                    conn.execute("COMMIT")
                    return True
                except sqlite3.IntegrityError:
                    conn.execute("ROLLBACK")
                    return False
            finally:
                conn.close()
