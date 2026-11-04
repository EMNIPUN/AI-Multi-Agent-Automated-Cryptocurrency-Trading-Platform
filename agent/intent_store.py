"""SQLite persistence for order intents and execution evidence (Phase 1B / 1E)."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from agent.order_intent import (
    BLOCKING_EXPOSURE_STATES,
    NEEDS_RECONCILE_STATES,
    UNRESOLVED_STATES,
    OrderIntent,
    OrderIntentState,
    assert_transition,
    merge_reconcile_state,
    utc_now_iso,
)

_DEFAULT_DB = Path("data") / "order_intents.sqlite3"
_SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS order_intents (
    intent_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL,
    env_scope TEXT NOT NULL,
    account_fp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    category TEXT NOT NULL,
    side TEXT NOT NULL,
    qty TEXT NOT NULL,
    reduce_only INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    time_in_force TEXT NOT NULL,
    take_profit TEXT,
    stop_loss TEXT,
    correlation_id TEXT NOT NULL,
    risk_auth_ref TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    exchange_order_id TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    filled_qty TEXT NOT NULL DEFAULT '',
    submission_attempted INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE (env_scope, account_fp, client_order_id)
);
CREATE INDEX IF NOT EXISTS idx_order_intents_state
    ON order_intents (env_scope, account_fp, state);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_executions (
    env_scope TEXT NOT NULL,
    account_fp TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    exec_id TEXT NOT NULL,
    order_id TEXT NOT NULL DEFAULT '',
    order_link_id TEXT NOT NULL DEFAULT '',
    exec_qty TEXT NOT NULL,
    exec_price TEXT NOT NULL,
    exec_fee TEXT NOT NULL DEFAULT '',
    fee_currency TEXT NOT NULL DEFAULT '',
    exec_time_ms TEXT NOT NULL DEFAULT '',
    is_maker INTEGER,
    leaves_qty TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (env_scope, account_fp, exec_id),
    FOREIGN KEY (intent_id) REFERENCES order_intents(intent_id)
);
CREATE INDEX IF NOT EXISTS idx_order_executions_intent
    ON order_executions (intent_id);
"""

_OPTIONAL_COLUMNS: tuple[tuple[str, str], ...] = (
    ("remaining_qty", "TEXT NOT NULL DEFAULT ''"),
    ("avg_exec_price", "TEXT NOT NULL DEFAULT ''"),
    ("cum_fee", "TEXT NOT NULL DEFAULT ''"),
    ("evidence_status", "TEXT NOT NULL DEFAULT ''"),
)


class IntentStoreError(RuntimeError):
    """Durable store failure — callers must fail closed for new exposure."""


@dataclass(frozen=True)
class ExecutionRow:
    exec_id: str
    order_id: str = ""
    order_link_id: str = ""
    exec_qty: str = "0"
    exec_price: str = "0"
    exec_fee: str = ""
    fee_currency: str = ""
    exec_time_ms: str = ""
    is_maker: bool | None = None
    leaves_qty: str = ""
    category: str = ""


class IntentStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                # executescript auto-commits; migrate under an explicit transaction.
                conn.executescript(_SCHEMA)
                conn.execute("BEGIN IMMEDIATE")
                self._migrate(conn)
                conn.execute("COMMIT")
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise IntentStoreError(f"intent store init failed: {exc}") from exc
            finally:
                conn.close()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cols = {
            str(r["name"])
            for r in conn.execute("PRAGMA table_info(order_intents)").fetchall()
        }
        for name, decl in _OPTIONAL_COLUMNS:
            if name not in cols:
                conn.execute(f"ALTER TABLE order_intents ADD COLUMN {name} {decl}")
        conn.execute(
            """
            INSERT INTO schema_meta(key, value) VALUES ('version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(_SCHEMA_VERSION),),
        )

    def _row_to_intent(self, row: sqlite3.Row) -> OrderIntent:
        keys = set(row.keys())
        return OrderIntent(
            intent_id=row["intent_id"],
            client_order_id=row["client_order_id"],
            env_scope=row["env_scope"],
            account_fp=row["account_fp"],
            symbol=row["symbol"],
            category=row["category"],
            side=row["side"],
            qty=row["qty"],
            reduce_only=bool(row["reduce_only"]),
            order_type=row["order_type"],
            time_in_force=row["time_in_force"],
            take_profit=row["take_profit"],
            stop_loss=row["stop_loss"],
            correlation_id=row["correlation_id"],
            risk_auth_ref=row["risk_auth_ref"],
            state=OrderIntentState(row["state"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            dry_run=bool(row["dry_run"]),
            exchange_order_id=row["exchange_order_id"] or "",
            last_error=row["last_error"] or "",
            filled_qty=row["filled_qty"] or "",
            remaining_qty=(row["remaining_qty"] if "remaining_qty" in keys else "")
            or "",
            avg_exec_price=(row["avg_exec_price"] if "avg_exec_price" in keys else "")
            or "",
            cum_fee=(row["cum_fee"] if "cum_fee" in keys else "") or "",
            evidence_status=(
                row["evidence_status"] if "evidence_status" in keys else ""
            )
            or "",
            submission_attempted=bool(row["submission_attempted"]),
            updated_at=(row["updated_at"] if "updated_at" in keys else "") or "",
        )

    def get_by_client_order_id(
        self, env_scope: str, account_fp: str, client_order_id: str
    ) -> OrderIntent | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM order_intents
                    WHERE env_scope = ? AND account_fp = ? AND client_order_id = ?
                    """,
                    (env_scope, account_fp, client_order_id),
                ).fetchone()
                return self._row_to_intent(row) if row else None
            finally:
                conn.close()

    def get_by_intent_id(self, intent_id: str) -> OrderIntent | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                return self._row_to_intent(row) if row else None
            finally:
                conn.close()

    def insert_created(self, intent: OrderIntent) -> tuple[bool, OrderIntent]:
        """
        Persist a CREATED intent before any network submission.

        Returns (inserted, intent). If unique conflict, returns existing row
        and inserted=False (no second independent submission record).
        """
        if intent.state is not OrderIntentState.CREATED:
            raise ValueError("insert_created requires CREATED state")

        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        """
                        INSERT INTO order_intents (
                            intent_id, client_order_id, env_scope, account_fp,
                            symbol, category, side, qty, reduce_only,
                            order_type, time_in_force, take_profit, stop_loss,
                            correlation_id, risk_auth_ref, state, created_at,
                            expires_at, dry_run, exchange_order_id, last_error,
                            filled_qty, remaining_qty, avg_exec_price, cum_fee,
                            evidence_status, submission_attempted, updated_at
                        ) VALUES (
                            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                        )
                        """,
                        (
                            intent.intent_id,
                            intent.client_order_id,
                            intent.env_scope,
                            intent.account_fp,
                            intent.symbol,
                            intent.category,
                            intent.side,
                            intent.qty,
                            1 if intent.reduce_only else 0,
                            intent.order_type,
                            intent.time_in_force,
                            intent.take_profit,
                            intent.stop_loss,
                            intent.correlation_id,
                            intent.risk_auth_ref,
                            intent.state.value,
                            intent.created_at,
                            intent.expires_at,
                            1 if intent.dry_run else 0,
                            intent.exchange_order_id,
                            intent.last_error,
                            intent.filled_qty,
                            intent.remaining_qty,
                            intent.avg_exec_price,
                            intent.cum_fee,
                            intent.evidence_status,
                            1 if intent.submission_attempted else 0,
                            utc_now_iso(),
                        ),
                    )
                    conn.execute("COMMIT")
                    return True, intent
                except sqlite3.IntegrityError:
                    conn.execute("ROLLBACK")
                    existing = conn.execute(
                        """
                        SELECT * FROM order_intents
                        WHERE env_scope = ? AND account_fp = ? AND client_order_id = ?
                        """,
                        (intent.env_scope, intent.account_fp, intent.client_order_id),
                    ).fetchone()
                    if existing is None:
                        raise IntentStoreError(
                            "unique conflict without existing row"
                        )
                    return False, self._row_to_intent(existing)
            except IntentStoreError:
                raise
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise IntentStoreError(str(exc)) from exc
            finally:
                conn.close()

    def transition(
        self,
        intent_id: str,
        new_state: OrderIntentState,
        *,
        exchange_order_id: str | None = None,
        last_error: str | None = None,
        filled_qty: str | None = None,
        remaining_qty: str | None = None,
        avg_exec_price: str | None = None,
        cum_fee: str | None = None,
        evidence_status: str | None = None,
        submission_attempted: bool | None = None,
    ) -> OrderIntent:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    raise KeyError(f"intent not found: {intent_id}")
                current = OrderIntentState(row["state"])
                # Terminal states: allow metadata refresh on same state only.
                if current in {
                    OrderIntentState.FILLED,
                    OrderIntentState.REJECTED,
                    OrderIntentState.CANCELED,
                }:
                    if new_state is not current:
                        # Soft no-op: refuse regression; keep terminal row.
                        new_state = current
                    else:
                        assert_transition(current, new_state)
                else:
                    assert_transition(current, new_state)
                conn.execute(
                    """
                    UPDATE order_intents SET
                        state = ?,
                        exchange_order_id = COALESCE(?, exchange_order_id),
                        last_error = COALESCE(?, last_error),
                        filled_qty = COALESCE(?, filled_qty),
                        remaining_qty = COALESCE(?, remaining_qty),
                        avg_exec_price = COALESCE(?, avg_exec_price),
                        cum_fee = COALESCE(?, cum_fee),
                        evidence_status = COALESCE(?, evidence_status),
                        submission_attempted = COALESCE(?, submission_attempted),
                        updated_at = ?
                    WHERE intent_id = ?
                    """,
                    (
                        new_state.value,
                        exchange_order_id,
                        last_error,
                        filled_qty,
                        remaining_qty,
                        avg_exec_price,
                        cum_fee,
                        evidence_status,
                        (
                            None
                            if submission_attempted is None
                            else (1 if submission_attempted else 0)
                        ),
                        utc_now_iso(),
                        intent_id,
                    ),
                )
                conn.execute("COMMIT")
                refreshed = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                return self._row_to_intent(refreshed)
            except (KeyError, ValueError):
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise IntentStoreError(str(exc)) from exc
            finally:
                conn.close()

    def apply_reconcile_update(
        self,
        intent_id: str,
        *,
        proposed_state: OrderIntentState,
        executions: list[ExecutionRow],
        exchange_order_id: str | None = None,
        filled_qty: str | None = None,
        remaining_qty: str | None = None,
        avg_exec_price: str | None = None,
        cum_fee: str | None = None,
        evidence_status: str | None = None,
        last_error: str | None = None,
        conflict: bool = False,
    ) -> tuple[OrderIntent, int]:
        """
        Transactionally persist execution evidence and merge intent state.

        Returns (intent, newly_inserted_execution_count).
        Duplicate exec_id within env_scope/account_fp are ignored (idempotent).
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    raise KeyError(f"intent not found: {intent_id}")

                current = OrderIntentState(row["state"])
                env_scope = row["env_scope"]
                account_fp = row["account_fp"]
                inserted = 0
                now = utc_now_iso()

                for ex in executions:
                    if not ex.exec_id:
                        continue
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO order_executions (
                            env_scope, account_fp, intent_id, exec_id, order_id,
                            order_link_id, exec_qty, exec_price, exec_fee,
                            fee_currency, exec_time_ms, is_maker, leaves_qty,
                            category, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            env_scope,
                            account_fp,
                            intent_id,
                            ex.exec_id,
                            ex.order_id,
                            ex.order_link_id,
                            ex.exec_qty,
                            ex.exec_price,
                            ex.exec_fee,
                            ex.fee_currency,
                            ex.exec_time_ms,
                            None if ex.is_maker is None else (1 if ex.is_maker else 0),
                            ex.leaves_qty,
                            ex.category,
                            now,
                        ),
                    )
                    if cur.rowcount == 1:
                        inserted += 1

                if conflict:
                    target = merge_reconcile_state(
                        current, OrderIntentState.UNKNOWN
                    )
                    if target is current and current not in {
                        OrderIntentState.UNKNOWN,
                        OrderIntentState.RECONCILIATION_REQUIRED,
                    }:
                        # Force unresolved when evidence conflicts mid-flight.
                        if current not in {
                            OrderIntentState.FILLED,
                            OrderIntentState.REJECTED,
                            OrderIntentState.CANCELED,
                        }:
                            target = OrderIntentState.UNKNOWN
                else:
                    target = merge_reconcile_state(current, proposed_state)
                    if target is not current and target is not proposed_state:
                        # merge kept current due to terminal / regression
                        pass
                    elif target is not current:
                        assert_transition(current, target)

                conn.execute(
                    """
                    UPDATE order_intents SET
                        state = ?,
                        exchange_order_id = COALESCE(?, exchange_order_id),
                        last_error = COALESCE(?, last_error),
                        filled_qty = COALESCE(?, filled_qty),
                        remaining_qty = COALESCE(?, remaining_qty),
                        avg_exec_price = COALESCE(?, avg_exec_price),
                        cum_fee = COALESCE(?, cum_fee),
                        evidence_status = COALESCE(?, evidence_status),
                        updated_at = ?
                    WHERE intent_id = ?
                    """,
                    (
                        target.value,
                        exchange_order_id,
                        last_error,
                        filled_qty,
                        remaining_qty,
                        avg_exec_price,
                        cum_fee,
                        evidence_status,
                        now,
                        intent_id,
                    ),
                )
                conn.execute("COMMIT")
                refreshed = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                return self._row_to_intent(refreshed), inserted
            except (KeyError, ValueError):
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise IntentStoreError(str(exc)) from exc
            finally:
                conn.close()

    def list_executions(self, intent_id: str) -> list[ExecutionRow]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM order_executions
                    WHERE intent_id = ?
                    ORDER BY exec_time_ms ASC, exec_id ASC
                    """,
                    (intent_id,),
                ).fetchall()
                out: list[ExecutionRow] = []
                for r in rows:
                    maker = r["is_maker"]
                    out.append(
                        ExecutionRow(
                            exec_id=r["exec_id"],
                            order_id=r["order_id"] or "",
                            order_link_id=r["order_link_id"] or "",
                            exec_qty=r["exec_qty"],
                            exec_price=r["exec_price"],
                            exec_fee=r["exec_fee"] or "",
                            fee_currency=r["fee_currency"] or "",
                            exec_time_ms=r["exec_time_ms"] or "",
                            is_maker=None if maker is None else bool(maker),
                            leaves_qty=r["leaves_qty"] or "",
                            category=r["category"] or "",
                        )
                    )
                return out
            finally:
                conn.close()

    def mark_restart_recovery(
        self, env_scope: str, account_fp: str
    ) -> list[OrderIntent]:
        """
        On process start: any in-flight submission becomes RECONCILIATION_REQUIRED.
        Never assumes the order was not accepted by the exchange.
        ACCEPTED / PARTIALLY_FILLED are left as-is for evidence reconcile.
        """
        recovered: list[OrderIntent] = []
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute(
                    """
                    SELECT * FROM order_intents
                    WHERE env_scope = ? AND account_fp = ?
                      AND state IN (?, ?)
                      AND dry_run = 0
                    """,
                    (
                        env_scope,
                        account_fp,
                        OrderIntentState.SUBMISSION_PENDING.value,
                        OrderIntentState.UNKNOWN.value,
                    ),
                ).fetchall()
                for row in rows:
                    current = OrderIntentState(row["state"])
                    target = OrderIntentState.RECONCILIATION_REQUIRED
                    assert_transition(current, target)
                    conn.execute(
                        """
                        UPDATE order_intents
                        SET state = ?, last_error = ?, updated_at = ?
                        WHERE intent_id = ?
                        """,
                        (
                            target.value,
                            "restart recovery: unresolved submission",
                            utc_now_iso(),
                            row["intent_id"],
                        ),
                    )
                    refreshed = conn.execute(
                        "SELECT * FROM order_intents WHERE intent_id = ?",
                        (row["intent_id"],),
                    ).fetchone()
                    recovered.append(self._row_to_intent(refreshed))
                conn.execute("COMMIT")
                return recovered
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise IntentStoreError(str(exc)) from exc
            finally:
                conn.close()

    def list_unresolved(
        self, env_scope: str, account_fp: str, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        return self._list_by_states(
            env_scope, account_fp, UNRESOLVED_STATES, symbol=symbol
        )

    def list_blocking_exposure(
        self, env_scope: str, account_fp: str, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        return self._list_by_states(
            env_scope, account_fp, BLOCKING_EXPOSURE_STATES, symbol=symbol
        )

    def list_needs_reconcile(
        self, env_scope: str, account_fp: str, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        return self._list_by_states(
            env_scope, account_fp, NEEDS_RECONCILE_STATES, symbol=symbol
        )

    def list_recent_for_observation(
        self,
        env_scope: str,
        account_fp: str,
        *,
        limit: int = 200,
    ) -> list[OrderIntent]:
        """
        Read-only projection for telemetry. Includes dry-run rows.
        Does not mutate intents. Newest ``updated_at`` first.
        """
        limit = max(1, min(int(limit), 500))
        sql = """
            SELECT * FROM order_intents
            WHERE env_scope = ? AND account_fp = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
        """
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, (env_scope, account_fp, limit)).fetchall()
                return [self._row_to_intent(r) for r in rows]
            finally:
                conn.close()

    def _list_by_states(
        self,
        env_scope: str,
        account_fp: str,
        states: frozenset[OrderIntentState],
        *,
        symbol: str | None = None,
    ) -> list[OrderIntent]:
        state_vals = tuple(s.value for s in states)
        placeholders = ",".join("?" * len(state_vals))
        sql = f"""
            SELECT * FROM order_intents
            WHERE env_scope = ? AND account_fp = ?
              AND dry_run = 0
              AND state IN ({placeholders})
        """
        params: list[object] = [env_scope, account_fp, *state_vals]
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_intent(r) for r in rows]
            finally:
                conn.close()

    def try_claim_for_submission(self, intent_id: str) -> OrderIntent | None:
        """
        Atomically CREATED -> SUBMISSION_PENDING for live submission.
        Returns None if another worker already claimed / progressed the intent.
        """
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                if row["state"] != OrderIntentState.CREATED.value:
                    conn.execute("ROLLBACK")
                    return None
                if row["dry_run"]:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute(
                    """
                    UPDATE order_intents
                    SET state = ?, submission_attempted = 1, updated_at = ?
                    WHERE intent_id = ? AND state = ?
                    """,
                    (
                        OrderIntentState.SUBMISSION_PENDING.value,
                        utc_now_iso(),
                        intent_id,
                        OrderIntentState.CREATED.value,
                    ),
                )
                if conn.total_changes != 1:
                    conn.execute("ROLLBACK")
                    return None
                conn.execute("COMMIT")
                refreshed = conn.execute(
                    "SELECT * FROM order_intents WHERE intent_id = ?",
                    (intent_id,),
                ).fetchone()
                return self._row_to_intent(refreshed)
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise IntentStoreError(str(exc)) from exc
            finally:
                conn.close()
