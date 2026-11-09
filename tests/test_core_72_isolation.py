"""Prompt 72 — backtest isolation and signal owner error. No live orders."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from agent.backtest.pg_journal import BacktestJournalUnavailable, PostgresBacktestJournal
from apps.api.app.database_url import redact_connection_strings
from agent.backtest.store import open_isolated_paper_store
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.persistence.sqlite_guard import supabase_sot_enabled
from apps.api.app.signals import service as signal_service


def test_log_redaction_removes_embedded_database_url() -> None:
    raw = "connect failed postgresql+psycopg://postgres.example:super-secret-value@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
    cleaned = redact_connection_strings(raw)
    assert "super-secret-value" not in cleaned
    assert ":***@" in cleaned


def test_backtest_journal_does_not_change_process_sot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_SOT_ENABLED", "true")
    clear_settings_cache()
    path = tmp_path / "bt68a_isolation.sqlite3"
    store = open_isolated_paper_store(path)
    assert os.environ["SUPABASE_SOT_ENABLED"] == "true"
    assert supabase_sot_enabled() is True
    assert store._engine.dialect.name == "sqlite"
    assert path.is_file()
    monkeypatch.setenv("SUPABASE_SOT_ENABLED", "false")
    clear_settings_cache()


def test_signal_status_without_owner_is_conflict(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_SOT_ENABLED", "true")
    monkeypatch.delenv("SIGNAL_CLOUD_OWNER_USER_ID", raising=False)
    monkeypatch.delenv("CRYPTONOVA_TEST_OWNER_USER_ID", raising=False)
    clear_settings_cache()
    signal_service._store = None
    settings = ApiSettings(_env_file=None, supabase_sot_enabled=True)
    client = TestClient(create_app(settings))
    response = client.get("/api/v1/signals/status")
    assert response.status_code == 409
    body = response.json()["detail"]
    assert body["code"] == "signal_owner_unconfigured"
    assert body["execution_allowed"] is False
    signal_service._store = None
    clear_settings_cache()


def test_postgres_journal_fails_closed_before_migration() -> None:
    from sqlalchemy.exc import SQLAlchemyError

    class _Down:
        class dialect:
            name = "postgresql"

        def connect(self) -> None:
            raise SQLAlchemyError("down")

    journal = PostgresBacktestJournal(_Down())  # type: ignore[arg-type]
    assert journal.ready() is False
    try:
        journal.write_run(run={"run_id": "r"})
        raise AssertionError("unavailable journal must fail closed")
    except BacktestJournalUnavailable as exc:
        assert "backtest_journal_not_ready" in str(exc)


def test_postgres_journal_write_is_one_transaction_and_idempotent() -> None:
    statements: list[str] = []

    class _Result:
        def scalar(self) -> int:
            return 1

    class _Conn:
        def execute(self, statement: object, params: object = None) -> _Result:
            del params
            statements.append(str(statement))
            return _Result()

        def __enter__(self) -> _Conn:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    class _Engine:
        class dialect:
            name = "postgresql"

        def __init__(self) -> None:
            self.conn = _Conn()

        def connect(self) -> _Conn:
            return self.conn

        def begin(self) -> _Conn:
            statements.append("BEGIN")
            return self.conn

    journal = PostgresBacktestJournal(_Engine())  # type: ignore[arg-type]
    journal.write_run(
        run={
            "run_id": "run-1",
            "owner_user_id": "00000000-0000-0000-0000-000000000001",
            "symbol": "BTCUSDT",
            "interval": "1",
            "config_json": {"fee": "0.001"},
            "dataset_hash": "abc",
            "result_hash": None,
            "status": "RUNNING",
            "created_at_ms": 1,
        },
        orders=[
            {
                "order_id": "o1",
                "run_id": "run-1",
                "owner_user_id": "00000000-0000-0000-0000-000000000001",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "quantity": "1",
                "status": "FILLED",
                "idempotency_key": "k1",
            }
        ],
        fills=[
            {
                "order_id": "o1",
                "fill_seq": 1,
                "price": "100",
                "quantity": "0.5",
                "fee": "0.01",
                "filled_at_ms": 1,
            }
        ],
        equity=[{"snapshot_id": "e1", "equity": "100", "cash": "50"}],
    )
    joined = "\n".join(statements)
    assert "BEGIN" in statements
    assert statements.index("BEGIN") < next(
        index for index, item in enumerate(statements) if "INSERT INTO" in item
    )
    assert "backtest_exec_runs" in joined
    assert "uq_backtest_exec_orders_idem" in joined
    assert "uq_backtest_exec_fills_seq" in joined
    assert "ON CONFLICT (snapshot_id) DO NOTHING" in joined
    assert joined.count("INSERT INTO") == 4


def test_postgres_backtest_journal_rejects_sqlite_and_is_not_applied() -> None:
    try:
        PostgresBacktestJournal(create_engine("sqlite://"))
        raise AssertionError("sqlite journal must be refused")
    except BacktestJournalUnavailable as exc:
        assert "sqlite_forbidden" in str(exc)
    text = Path("apps/api/alembic/versions/20261108_0012_backtest_exec_journal_72.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision: Union[str, None] = "20261108_0011"' in text
    assert "backtest_exec_fills" in text
    runner = Path("agent/backtest/runner.py").read_text(encoding="utf-8")
    assert "PostgresBacktestJournal" not in runner
    migration = Path(
        "apps/api/alembic/versions/20261108_0012_backtest_exec_journal_72.py"
    ).read_text(encoding="utf-8")
    assert "owner_user_id = auth.uid()" in migration
    assert "nullable=False" in migration
    assert "backtest_exec_risk" in migration
    assert "uq_backtest_exec_fills_seq" in migration
    assert 'UniqueConstraint("run_id", "order_id", "filled_at_ms"' not in migration
