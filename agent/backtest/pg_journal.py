"""Postgres backtest execution journal. Not used by run_backtest until 0012 is applied.

The active backtest path remains the isolated SQLite journal. This module
fails closed and does not fall back to SQLite.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class BacktestJournalUnavailable(RuntimeError):
    pass


def deterministic_fill_id(run_id: str, order_id: str, fill_seq: int) -> str:
    """Stable id for one partial. Sequence, not timestamp, identifies the fill."""
    seq = int(fill_seq)
    if seq < 1:
        raise BacktestJournalUnavailable("fill_seq_invalid")
    digest = hashlib.sha256(f"{run_id}|{order_id}|{seq}".encode()).hexdigest()
    return digest[:32]


def _decimal_text(value: object) -> str:
    return format(Decimal(str(value)), "f")


def plan_fill_row(fill: Mapping[str, object]) -> dict[str, object]:
    run_id = str(fill["run_id"])
    order_id = str(fill["order_id"])
    fill_seq = int(fill["fill_seq"])
    fill_id = deterministic_fill_id(run_id, order_id, fill_seq)
    supplied = fill.get("fill_id")
    if supplied is not None and str(supplied) != fill_id:
        raise BacktestJournalUnavailable("fill_id_not_deterministic")
    return {
        "fill_id": fill_id,
        "run_id": run_id,
        "owner_user_id": fill["owner_user_id"],
        "order_id": order_id,
        "fill_seq": fill_seq,
        "price": _decimal_text(fill["price"]),
        "quantity": _decimal_text(fill["quantity"]),
        "fee": _decimal_text(fill["fee"]),
        "slippage": _decimal_text(fill.get("slippage", "0")),
        "filled_at_ms": int(fill["filled_at_ms"]),
    }


_INSERT_RUN = text(
    """
    INSERT INTO app.backtest_exec_runs (
        run_id, owner_user_id, symbol, interval, config_json,
        dataset_hash, result_hash, status, created_at_ms
    ) VALUES (
        :run_id, :owner_user_id, :symbol, :interval, CAST(:config_json AS jsonb),
        :dataset_hash, :result_hash, :status, :created_at_ms
    )
    ON CONFLICT (run_id) DO NOTHING
    """
)

_INSERT_ORDER = text(
    """
    INSERT INTO app.backtest_exec_orders (
        order_id, run_id, owner_user_id, symbol, side, quantity, status, idempotency_key
    ) VALUES (
        :order_id, :run_id, :owner_user_id, :symbol, :side, :quantity, :status, :idempotency_key
    )
    ON CONFLICT ON CONSTRAINT uq_backtest_exec_orders_idem DO NOTHING
    """
)

_INSERT_FILL = text(
    """
    INSERT INTO app.backtest_exec_fills (
        fill_id, run_id, owner_user_id, order_id, fill_seq,
        price, quantity, fee, slippage, filled_at_ms
    ) VALUES (
        :fill_id, :run_id, :owner_user_id, :order_id, :fill_seq,
        :price, :quantity, :fee, :slippage, :filled_at_ms
    )
    ON CONFLICT ON CONSTRAINT uq_backtest_exec_fills_seq DO NOTHING
    """
)

_INSERT_EQUITY = text(
    """
    INSERT INTO app.backtest_exec_equity (
        snapshot_id, run_id, owner_user_id, at_ms, equity, cash
    ) VALUES (
        :snapshot_id, :run_id, :owner_user_id, :at_ms, :equity, :cash
    )
    ON CONFLICT (snapshot_id) DO NOTHING
    """
)

_UPSERT_POSITION = text(
    """
    INSERT INTO app.backtest_exec_positions (
        position_id, run_id, owner_user_id, symbol, quantity, avg_price, updated_at_ms
    ) VALUES (
        :position_id, :run_id, :owner_user_id, :symbol, :quantity, :avg_price, :updated_at_ms
    )
    ON CONFLICT ON CONSTRAINT uq_backtest_exec_positions_symbol DO UPDATE SET
        quantity = EXCLUDED.quantity,
        avg_price = EXCLUDED.avg_price,
        updated_at_ms = EXCLUDED.updated_at_ms
    """
)

_UPSERT_RISK = text(
    """
    INSERT INTO app.backtest_exec_risk (
        run_id, owner_user_id, halted, reason, updated_at_ms
    ) VALUES (
        :run_id, :owner_user_id, :halted, :reason, :updated_at_ms
    )
    ON CONFLICT (run_id) DO UPDATE SET
        halted = EXCLUDED.halted,
        reason = EXCLUDED.reason,
        updated_at_ms = EXCLUDED.updated_at_ms
    """
)


class PostgresBacktestJournal:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name == "sqlite":
            raise BacktestJournalUnavailable("sqlite_forbidden")
        self._engine = engine

    def ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(
                    text("SELECT fill_seq, slippage FROM app.backtest_exec_fills LIMIT 1")
                )
            return True
        except SQLAlchemyError:
            return False

    def write_run(
        self,
        *,
        run: Mapping[str, object],
        orders: Sequence[Mapping[str, object]] = (),
        fills: Sequence[Mapping[str, object]] = (),
        equity: Sequence[Mapping[str, object]] = (),
        positions: Sequence[Mapping[str, object]] = (),
        risk: Mapping[str, object] | None = None,
    ) -> None:
        """Write one run and its children in a single transaction.

        The runner does not call this until migration 0012 is applied and
        fill-by-fill parity has passed. Replay of the same fill sequence is
        ignored. A second partial with a new sequence is stored even when
        filled_at_ms matches an earlier partial.
        """
        if not self.ready():
            raise BacktestJournalUnavailable("backtest_journal_not_ready")
        payload = dict(run)
        config = payload.get("config_json", {})
        if not isinstance(config, str):
            payload["config_json"] = json.dumps(config, sort_keys=True, default=str)
        planned = []
        for fill in fills:
            row = dict(fill)
            row.setdefault("run_id", payload["run_id"])
            row.setdefault("owner_user_id", payload["owner_user_id"])
            planned.append(plan_fill_row(row))
        try:
            with self._engine.begin() as conn:
                conn.execute(_INSERT_RUN, payload)
                for order in orders:
                    row = dict(order)
                    row["quantity"] = _decimal_text(row["quantity"])
                    conn.execute(_INSERT_ORDER, row)
                for fill in planned:
                    conn.execute(_INSERT_FILL, fill)
                for position in positions:
                    row = dict(position)
                    row["quantity"] = _decimal_text(row["quantity"])
                    row["avg_price"] = _decimal_text(row["avg_price"])
                    conn.execute(_UPSERT_POSITION, row)
                for snapshot in equity:
                    row = dict(snapshot)
                    row["equity"] = _decimal_text(row["equity"])
                    row["cash"] = _decimal_text(row["cash"])
                    conn.execute(_INSERT_EQUITY, row)
                if risk is not None:
                    conn.execute(_UPSERT_RISK, dict(risk))
        except IntegrityError as exc:
            raise BacktestJournalUnavailable("backtest_journal_constraint_rejected") from exc
        except SQLAlchemyError as exc:
            raise BacktestJournalUnavailable("backtest_journal_write_failed") from exc

    def read_fills(self, run_id: str) -> list[dict[str, object]]:
        if not self.ready():
            raise BacktestJournalUnavailable("backtest_journal_not_ready")
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT order_id, fill_seq, price, quantity, fee, slippage, filled_at_ms
                    FROM app.backtest_exec_fills
                    WHERE run_id = :run_id
                    ORDER BY order_id, fill_seq
                    """
                ),
                {"run_id": run_id},
            ).mappings().all()
        return [dict(row) for row in rows]


def assert_loopback_journal_url(url: str) -> None:
    low = url.lower()
    if "127.0.0.1" not in low and "localhost" not in low:
        raise BacktestJournalUnavailable("local_journal_host_refused")
    if "supabase" in low or "pooler" in low:
        raise BacktestJournalUnavailable("remote_journal_refused")


_LOCAL_DDL = """
CREATE SCHEMA IF NOT EXISTS app;
CREATE TABLE IF NOT EXISTS app.backtest_exec_runs (
    run_id varchar(64) PRIMARY KEY,
    owner_user_id uuid NOT NULL,
    symbol varchar(32) NOT NULL,
    interval varchar(16) NOT NULL,
    config_json jsonb NOT NULL,
    dataset_hash varchar(64) NOT NULL,
    result_hash varchar(64),
    status varchar(32) NOT NULL,
    created_at_ms bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS app.backtest_exec_orders (
    order_id varchar(64) PRIMARY KEY,
    run_id varchar(64) NOT NULL REFERENCES app.backtest_exec_runs(run_id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL,
    symbol varchar(32) NOT NULL,
    side varchar(8) NOT NULL,
    quantity numeric(28, 12) NOT NULL,
    status varchar(32) NOT NULL,
    idempotency_key varchar(128) NOT NULL,
    CONSTRAINT uq_backtest_exec_orders_idem UNIQUE (run_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS app.backtest_exec_fills (
    fill_id varchar(64) PRIMARY KEY,
    run_id varchar(64) NOT NULL REFERENCES app.backtest_exec_runs(run_id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL,
    order_id varchar(64) NOT NULL REFERENCES app.backtest_exec_orders(order_id) ON DELETE CASCADE,
    fill_seq integer NOT NULL CHECK (fill_seq >= 1),
    price numeric(28, 12) NOT NULL,
    quantity numeric(28, 12) NOT NULL,
    fee numeric(28, 12) NOT NULL,
    slippage numeric(28, 12) NOT NULL,
    filled_at_ms bigint NOT NULL,
    CONSTRAINT uq_backtest_exec_fills_seq UNIQUE (run_id, order_id, fill_seq)
);
CREATE TABLE IF NOT EXISTS app.backtest_exec_positions (
    position_id varchar(64) PRIMARY KEY,
    run_id varchar(64) NOT NULL REFERENCES app.backtest_exec_runs(run_id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL,
    symbol varchar(32) NOT NULL,
    quantity numeric(28, 12) NOT NULL,
    avg_price numeric(28, 12) NOT NULL,
    updated_at_ms bigint NOT NULL,
    CONSTRAINT uq_backtest_exec_positions_symbol UNIQUE (run_id, symbol)
);
CREATE TABLE IF NOT EXISTS app.backtest_exec_equity (
    snapshot_id varchar(64) PRIMARY KEY,
    run_id varchar(64) NOT NULL REFERENCES app.backtest_exec_runs(run_id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL,
    at_ms bigint NOT NULL,
    equity numeric(28, 12) NOT NULL,
    cash numeric(28, 12) NOT NULL
);
CREATE TABLE IF NOT EXISTS app.backtest_exec_risk (
    run_id varchar(64) PRIMARY KEY REFERENCES app.backtest_exec_runs(run_id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL,
    halted boolean NOT NULL,
    reason text NOT NULL,
    updated_at_ms bigint NOT NULL
);
"""


def install_local_journal_schema(engine: Engine) -> None:
    """Create the journal on a loopback PostgreSQL database only."""
    assert_loopback_journal_url(str(engine.url))
    with engine.begin() as conn:
        for statement in _LOCAL_DDL.split(";"):
            sql = statement.strip()
            if sql:
                conn.execute(text(sql))
