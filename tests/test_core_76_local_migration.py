"""Phase 76 — local migration 0012 only. Never uses the development database."""

from __future__ import annotations

import hashlib
import importlib.util
import socket
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "apps/api/alembic/versions/20261108_0012_backtest_exec_journal_72.py"
EXPECTED_SHA256 = "79d1197e675da8dd8dc057670af762a23e385ddcb1bcaf26db6b66c0a4cb11d5"
_ADMIN = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/postgres"
_DB = "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/cryptonova_76_migrate"


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


def _load_migration():
    spec = importlib.util.spec_from_file_location("cryptonova_0012", MIGRATION)
    if spec is None or spec.loader is None:
        raise RuntimeError("migration_module_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0012_checksum_is_unchanged() -> None:
    digest = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256


def test_postgres_journal_mode_fails_closed_without_sqlite_fallback(tmp_path: Path) -> None:
    from agent.backtest.runner import run_backtest

    with pytest.raises(RuntimeError, match="backtest_postgres_runtime_not_enabled"):
        run_backtest(journal_dir=tmp_path, journal_mode="postgres")
    assert list(tmp_path.glob("*.sqlite3")) == []


@pytest.mark.skipif(not _local_available(), reason="Disposable local PG on 127.0.0.1:55432 not running")
def test_migration_0012_upgrade_and_downgrade_on_localhost() -> None:
    if "supabase" in _ADMIN or "pooler" in _ADMIN:
        raise AssertionError("local migration test refused a remote URL")
    module = _load_migration()
    admin = create_engine(_ADMIN, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS cryptonova_76_migrate WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE cryptonova_76_migrate"))
    admin.dispose()
    engine = create_engine(_DB, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
            conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION auth.uid()
                    RETURNS uuid LANGUAGE sql STABLE AS $$
                      SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
                    $$
                    """
                )
            )
            conn.execute(
                text(
                    """
                    DO $$ BEGIN
                      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                        CREATE ROLE authenticated NOLOGIN;
                      END IF;
                    END $$
                    """
                )
            )
            ctx = MigrationContext.configure(connection=conn)
            with Operations.context(ctx):
                module.upgrade()
            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'app' AND table_name LIKE 'backtest_exec_%'"
                    )
                )
            }
            assert tables == {
                "backtest_exec_runs",
                "backtest_exec_orders",
                "backtest_exec_fills",
                "backtest_exec_positions",
                "backtest_exec_equity",
                "backtest_exec_risk",
            }
            forced = conn.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'app' AND c.relname = 'backtest_exec_fills'
                    """
                )
            ).one()
            assert forced[1] is True
            assert forced[2] is True
            slippage = conn.execute(
                text(
                    """
                    SELECT data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns
                    WHERE table_schema = 'app' AND table_name = 'backtest_exec_fills'
                      AND column_name = 'slippage'
                    """
                )
            ).one()
            assert slippage[0] == "numeric"
            assert int(slippage[1]) == 28
            assert int(slippage[2]) == 12
        from agent.backtest.pg_journal import PostgresBacktestJournal

        journal = PostgresBacktestJournal(engine)
        owner = "00000000-0000-0000-0000-000000000001"
        fills = [
            {
                "order_id": "order-1",
                "fill_seq": seq,
                "price": "100.5",
                "quantity": qty,
                "fee": fee,
                "slippage": slip,
                "filled_at_ms": 1_700_000_000_000,
            }
            for seq, qty, fee, slip in (
                (1, "0.25", "0.010000000000", "0.020000000000"),
                (2, "0.75", "0.030000000000", "0.040000000000"),
            )
        ]
        payload = {
            "run": {
                "run_id": "run-ms",
                "owner_user_id": owner,
                "symbol": "ETHUSDT",
                "interval": "5",
                "config_json": {"symbol": "ETHUSDT"},
                "dataset_hash": "a" * 64,
                "result_hash": "b" * 64,
                "status": "COMPLETED",
                "created_at_ms": 1,
            },
            "orders": [
                {
                    "order_id": "order-1",
                    "run_id": "run-ms",
                    "owner_user_id": owner,
                    "symbol": "ETHUSDT",
                    "side": "BUY",
                    "quantity": "1",
                    "status": "FILLED",
                    "idempotency_key": "sig-1:BUY",
                }
            ],
            "fills": fills,
            "equity": [
                {
                    "snapshot_id": "eq-1",
                    "run_id": "run-ms",
                    "owner_user_id": owner,
                    "at_ms": 1,
                    "equity": "10000",
                    "cash": "9900",
                }
            ],
            "risk": {
                "run_id": "run-ms",
                "owner_user_id": owner,
                "halted": False,
                "reason": "",
                "updated_at_ms": 1,
            },
        }
        journal.write_run(**payload)
        journal.write_run(**payload)
        stored = journal.read_fills("run-ms")
        assert len(stored) == 2
        assert int(stored[0]["filled_at_ms"]) == int(stored[1]["filled_at_ms"])
        assert [int(row["fill_seq"]) for row in stored] == [1, 2]
        assert sum(Decimal(str(row["fee"])) for row in stored) == Decimal("0.04")
        assert sum(Decimal(str(row["slippage"])) for row in stored) == Decimal("0.06")
        with engine.begin() as conn:
            ctx = MigrationContext.configure(connection=conn)
            with Operations.context(ctx):
                module.downgrade()
            left = conn.execute(text("SELECT to_regclass('app.backtest_exec_runs')")).scalar()
            assert left is None
    finally:
        engine.dispose()
        admin = create_engine(_ADMIN, isolation_level="AUTOCOMMIT", future=True)
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS cryptonova_76_migrate WITH (FORCE)"))
        admin.dispose()


def _parity_engine():
    if "supabase" in _ADMIN or "pooler" in _ADMIN:
        raise AssertionError("local parity test refused a remote URL")
    admin = create_engine(_ADMIN, isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS cryptonova_76_parity WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE cryptonova_76_parity"))
    admin.dispose()
    engine = create_engine(
        "postgresql+psycopg://cryptonova_test@127.0.0.1:55432/cryptonova_76_parity",
        future=True,
    )
    from agent.backtest.pg_journal import install_local_journal_schema

    install_local_journal_schema(engine)
    return engine


def _money_key(price, quantity, fee, slippage) -> tuple:
    return (
        Decimal(str(price)),
        Decimal(str(quantity)),
        Decimal(str(fee)),
        Decimal(str(slippage)),
    )


@pytest.mark.skipif(not _local_available(), reason="Disposable local PG on 127.0.0.1:55432 not running")
def test_eth_and_second_timeframe_sqlite_matches_local_postgres(tmp_path: Path) -> None:
    from agent.backtest.config import BacktestConfig, DataSourceKind, RiskMode
    from agent.backtest.data import synthetic_trend_candles
    from agent.backtest.journal_export import export_sqlite_backtest
    from agent.backtest.pg_journal import PostgresBacktestJournal
    from agent.backtest.runner import run_backtest
    from agent.backtest.store import open_isolated_read_store
    from apps.api.app.persistence.owner import resolve_sot_owner_user_id

    engine = _parity_engine()
    journal = PostgresBacktestJournal(engine)
    owner = str(resolve_sot_owner_user_id(required=False))
    candles = synthetic_trend_candles(n=230)
    cases = (
        ("ETHUSDT", "5", "eth"),
        ("BTCUSDT", "60", "btc60"),
    )
    try:
        for symbol, interval, name in cases:
            cfg = BacktestConfig(
                symbol=symbol,
                market_type="spot",
                interval=interval,
                initial_capital=Decimal("10000"),
                data_source=DataSourceKind.INLINE,
                risk_mode=RiskMode.SIGNAL_ONLY,
                min_confirmed_bars=210,
            )
            result = run_backtest(cfg, candles=candles, journal_dir=tmp_path / name)
            exported = export_sqlite_backtest(journal, result, owner_user_id=owner)
            replay = export_sqlite_backtest(journal, result, owner_user_id=owner)
            assert replay["fills"] == exported["fills"]
            stored = journal.read_fills(result.run_id)
            reader = open_isolated_read_store(result.journal_path)
            sqlite_fills = reader.list_fills(result.session_id, limit=200)
            assert len(stored) == len(sqlite_fills) == exported["fills"]
            pg_keys = sorted(
                _money_key(row["price"], row["quantity"], row["fee"], row["slippage"]) for row in stored
            )
            sqlite_keys = sorted(
                _money_key(fill.price, fill.quantity, fill.fee, fill.slippage) for fill in sqlite_fills
            )
            assert pg_keys == sqlite_keys
            assert sum(item[2] for item in pg_keys) == exported["fee_total"]
            assert sum(item[3] for item in pg_keys) == exported["slippage_total"]
            if result.analytics and "total_fees" in result.analytics:
                assert Decimal(str(result.analytics["total_fees"])) <= exported["fee_total"]
            with engine.connect() as conn:
                position = conn.execute(
                    text(
                        "SELECT quantity FROM app.backtest_exec_positions "
                        "WHERE run_id = :run_id AND symbol = :symbol"
                    ),
                    {"run_id": result.run_id, "symbol": symbol},
                ).scalar()
                equity = conn.execute(
                    text("SELECT count(*) FROM app.backtest_exec_equity WHERE run_id = :run_id"),
                    {"run_id": result.run_id},
                ).scalar()
            if position is not None:
                assert Decimal(str(position)) >= 0
            assert int(equity or 0) == exported["equity"]
            assert result.final_available_balance is not None
    finally:
        engine.dispose()
        admin = create_engine(_ADMIN, isolation_level="AUTOCOMMIT", future=True)
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS cryptonova_76_parity WITH (FORCE)"))
        admin.dispose()


def test_postgres_export_failure_is_not_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.backtest.config import BacktestConfig, DataSourceKind
    from agent.backtest.data import synthetic_trend_candles
    from agent.backtest.runner import run_backtest

    def _boom(*_args, **_kwargs):
        raise RuntimeError("postgresql://user:secret@db.example/postgres")

    monkeypatch.setattr("agent.backtest.journal_export.export_sqlite_backtest", _boom)
    monkeypatch.setenv("SIGNAL_CLOUD_OWNER_USER_ID", "00000000-0000-0000-0000-000000000001")
    result = run_backtest(
        BacktestConfig(
            symbol="BTCUSDT",
            market_type="spot",
            interval="15",
            data_source=DataSourceKind.INLINE,
            min_confirmed_bars=210,
        ),
        candles=synthetic_trend_candles(n=50),
        journal_dir=tmp_path,
        journal_mode="postgres",
        pg_journal=object(),
    )
    assert result.status.value == "failed"
    assert result.error is not None
    assert "://" not in result.error
    assert "secret" not in result.error


def test_postgres_export_success_keeps_completed_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.backtest.config import BacktestConfig, DataSourceKind
    from agent.backtest.data import synthetic_trend_candles
    from agent.backtest.runner import run_backtest

    seen: dict[str, str] = {}

    def _ok(_journal, result, *, owner_user_id: str):
        seen["owner"] = owner_user_id
        seen["run_id"] = result.run_id
        return {"fills": 0}

    monkeypatch.setattr("agent.backtest.journal_export.export_sqlite_backtest", _ok)
    monkeypatch.setenv("SIGNAL_CLOUD_OWNER_USER_ID", "00000000-0000-0000-0000-000000000001")
    result = run_backtest(
        BacktestConfig(
            symbol="BTCUSDT",
            market_type="spot",
            interval="15",
            data_source=DataSourceKind.INLINE,
            min_confirmed_bars=210,
        ),
        candles=synthetic_trend_candles(n=50),
        journal_dir=tmp_path,
        journal_mode="postgres",
        pg_journal=object(),
    )
    assert result.status.value == "completed"
    assert seen["run_id"] == result.run_id
    assert seen["owner"] == "00000000-0000-0000-0000-000000000001"
