"""Local PostgreSQL backtest journal parity. Never uses the development database."""

from __future__ import annotations

import socket
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from agent.backtest.config import BacktestConfig, DataSourceKind, RiskMode
from agent.backtest.data import synthetic_trend_candles
from agent.backtest.journal_export import export_sqlite_backtest
from agent.backtest.pg_journal import (
    PostgresBacktestJournal,
    assert_loopback_journal_url,
    install_local_journal_schema,
)
from agent.backtest.runner import run_backtest
from agent.backtest.store import open_isolated_read_store
from apps.api.app.persistence.owner import resolve_sot_owner_user_id

_ADMIN = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/postgres"
_DB = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/cryptonova_75_journal"


def _local_available() -> bool:
    sock = socket.socket()
    try:
        sock.settimeout(0.5)
        sock.connect(("127.0.0.1", 55432))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _journal() -> PostgresBacktestJournal:
    assert_loopback_journal_url(_ADMIN)
    admin = create_engine(_ADMIN, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS cryptonova_75_journal WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE cryptonova_75_journal"))
    admin.dispose()
    engine = create_engine(_DB, future=True)
    install_local_journal_schema(engine)
    return PostgresBacktestJournal(engine)


def _run(tmp_path, name: str):
    candles = synthetic_trend_candles(n=230)
    cfg = BacktestConfig(
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        initial_capital=Decimal("10000"),
        data_source=DataSourceKind.INLINE,
        risk_mode=RiskMode.SIGNAL_ONLY,
        min_confirmed_bars=210,
    )
    return run_backtest(cfg, candles=candles, journal_dir=tmp_path / name), candles


@pytest.mark.skipif(not _local_available(), reason="Disposable local PG on 127.0.0.1:55432 not running")
def test_sqlite_backtest_matches_local_postgres_journal(tmp_path) -> None:
    journal = _journal()
    owner = str(resolve_sot_owner_user_id(required=False))
    first, candles = _run(tmp_path, "a")
    second, _same = _run(tmp_path, "b")
    assert first.result_hash == second.result_hash
    assert first.final_available_balance == second.final_available_balance

    exported = export_sqlite_backtest(journal, first, owner_user_id=owner)
    replay = export_sqlite_backtest(journal, first, owner_user_id=owner)
    assert replay["fills"] == exported["fills"]
    stored = journal.read_fills(first.run_id)
    assert len(stored) == exported["fills"]
    pg_fees = sum((Decimal(str(row["fee"])) for row in stored), Decimal("0"))
    pg_slip = sum((Decimal(str(row["slippage"])) for row in stored), Decimal("0"))
    assert pg_fees == exported["fee_total"]
    assert pg_slip == exported["slippage_total"]
    if "total_fees" in first.analytics:
        # Closed-trade fees exclude entry fees still sitting on open positions.
        assert Decimal(first.analytics["total_fees"]) <= pg_fees
    pairs = [(row["order_id"], int(row["fill_seq"])) for row in stored]
    assert len(pairs) == len(set(pairs))

    other = export_sqlite_backtest(journal, second, owner_user_id=owner)
    assert len(journal.read_fills(first.run_id)) == exported["fills"]
    assert len(journal.read_fills(second.run_id)) == other["fills"]

    restarted = PostgresBacktestJournal(journal._engine)
    assert len(restarted.read_fills(first.run_id)) == exported["fills"]

    def _fail():
        raise SQLAlchemyError("down")

    journal._engine.begin = _fail  # type: ignore[method-assign]
    with pytest.raises(Exception):
        export_sqlite_backtest(journal, first, owner_user_id=owner)
    session = open_isolated_read_store(first.journal_path).get_session(first.session_id)
    assert session is not None
    assert Decimal(session.available_balance) == Decimal(first.final_available_balance)
    del candles
