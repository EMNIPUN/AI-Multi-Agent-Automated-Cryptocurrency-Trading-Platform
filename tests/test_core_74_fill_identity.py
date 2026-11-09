"""Prompt 74 — partial-fill identity. No database migration is applied."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from agent.backtest.pg_journal import (
    BacktestJournalUnavailable,
    deterministic_fill_id,
    plan_fill_row,
)
from agent.multi_agent.signal_history_store import (
    SignalHistoryStore,
    SignalHistoryStoreError,
)


def _fill(*, seq: int, quantity: str) -> dict[str, object]:
    return {
        "run_id": "run-a",
        "owner_user_id": "00000000-0000-0000-0000-000000000001",
        "order_id": "order-1",
        "fill_seq": seq,
        "price": "100.5",
        "quantity": quantity,
        "fee": "0.01",
        "filled_at_ms": 1_700_000_000_000,
    }


def test_same_millisecond_partials_keep_distinct_sequences() -> None:
    first = plan_fill_row(_fill(seq=1, quantity="0.25"))
    second = plan_fill_row(_fill(seq=2, quantity="0.75"))
    assert first["filled_at_ms"] == second["filled_at_ms"]
    assert first["fill_id"] != second["fill_id"]
    assert first["fill_seq"] == 1
    assert second["fill_seq"] == 2
    assert Decimal(str(first["quantity"])) + Decimal(str(second["quantity"])) == Decimal("1.00")
    assert plan_fill_row(_fill(seq=1, quantity="0.25"))["fill_id"] == first["fill_id"]


def test_replay_uses_the_same_id_and_a_forged_id_is_rejected() -> None:
    row = plan_fill_row(_fill(seq=1, quantity="0.25"))
    again = dict(_fill(seq=1, quantity="0.25"))
    again["fill_id"] = row["fill_id"]
    assert plan_fill_row(again)["fill_id"] == row["fill_id"]
    forged = dict(_fill(seq=1, quantity="0.25"))
    forged["fill_id"] = "not-the-deterministic-id"
    with pytest.raises(BacktestJournalUnavailable, match="fill_id_not_deterministic"):
        plan_fill_row(forged)
    with pytest.raises(BacktestJournalUnavailable, match="fill_seq_invalid"):
        deterministic_fill_id("run-a", "order-1", 0)


def test_sqlite_constraint_keeps_two_partials_and_ignores_replay() -> None:
    engine = create_engine("sqlite://")
    insert = text(
        """
        INSERT INTO fills (
            fill_id, run_id, order_id, fill_seq, price, quantity, fee, filled_at_ms
        ) VALUES (
            :fill_id, :run_id, :order_id, :fill_seq, :price, :quantity, :fee, :filled_at_ms
        )
        ON CONFLICT (run_id, order_id, fill_seq) DO NOTHING
        """
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE fills (
                    fill_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    fill_seq INTEGER NOT NULL CHECK (fill_seq >= 1),
                    price TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    fee TEXT NOT NULL,
                    filled_at_ms INTEGER NOT NULL,
                    UNIQUE (run_id, order_id, fill_seq)
                )
                """
            )
        )
        first = plan_fill_row(_fill(seq=1, quantity="0.25"))
        second = plan_fill_row(_fill(seq=2, quantity="0.75"))
        conn.execute(insert, first)
        conn.execute(insert, second)
        conn.execute(insert, first)
        stored = conn.execute(
            text("SELECT fill_seq, quantity FROM fills ORDER BY fill_seq")
        ).all()
    assert [(row[0], row[1]) for row in stored] == [(1, "0.25"), (2, "0.75")]


def test_local_postgres_keeps_same_millisecond_partials() -> None:
    """Disposable localhost cluster only. Never uses the development database."""
    import socket
    import uuid

    sock = socket.socket()
    try:
        sock.settimeout(0.5)
        sock.connect(("127.0.0.1", 55432))
    except OSError:
        pytest.skip("Disposable local PG on 127.0.0.1:55432 not running")
    finally:
        sock.close()

    url = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/postgres"
    if "supabase" in url or "pooler" in url:
        raise AssertionError("local journal test refused a remote URL")
    engine = create_engine(url)
    schema = "app_74_fill_" + uuid.uuid4().hex[:8]
    insert = text(
        f"""
        INSERT INTO "{schema}".fills (
            fill_id, run_id, order_id, fill_seq, price, quantity, fee, filled_at_ms
        ) VALUES (
            :fill_id, :run_id, :order_id, :fill_seq, :price, :quantity, :fee, :filled_at_ms
        )
        ON CONFLICT (run_id, order_id, fill_seq) DO NOTHING
        """
    )
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE "{schema}".fills (
                        fill_id text PRIMARY KEY,
                        run_id text NOT NULL,
                        order_id text NOT NULL,
                        fill_seq integer NOT NULL CHECK (fill_seq >= 1),
                        price numeric(28, 12) NOT NULL,
                        quantity numeric(28, 12) NOT NULL,
                        fee numeric(28, 12) NOT NULL,
                        filled_at_ms bigint NOT NULL,
                        UNIQUE (run_id, order_id, fill_seq)
                    )
                    """
                )
            )
            first = plan_fill_row(_fill(seq=1, quantity="0.25"))
            second = plan_fill_row(_fill(seq=2, quantity="0.75"))
            other_run = plan_fill_row(
                {**_fill(seq=1, quantity="0.25"), "run_id": "run-b"}
            )
            conn.execute(insert, first)
            conn.execute(insert, second)
            conn.execute(insert, first)
            conn.execute(insert, other_run)
            rows = conn.execute(
                text(
                    f'SELECT run_id, fill_seq, quantity FROM "{schema}".fills '
                    "ORDER BY run_id, fill_seq"
                )
            ).all()
        assert [(row[0], row[1], Decimal(row[2])) for row in rows] == [
            ("run-a", 1, Decimal("0.25")),
            ("run-a", 2, Decimal("0.75")),
            ("run-b", 1, Decimal("0.25")),
        ]
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_postgres_outbox_methods_fail_closed() -> None:
    store = SignalHistoryStore.__new__(SignalHistoryStore)
    store._engine = type("Engine", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()})()
    assert store.outbox_backend() == "not_applicable"
    with pytest.raises(
        SignalHistoryStoreError,
        match="outbox_not_applicable_signal_history_is_authoritative",
    ):
        store.enqueue_cloud_outbox(
            event_id="signal:1",
            event_type="signal_decision",
            payload={},
            now_ms=1,
        )
    with pytest.raises(SignalHistoryStoreError, match="outbox_not_applicable"):
        store.claim_outbox_batch(now_ms=1)
