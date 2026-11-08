"""Phase 4D — gated Supabase signal design (no live cloud writes)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState
from agent.multi_agent.signal_history_store import SignalHistoryStore
from agent.multi_agent.types import DecisionAction
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.models import Base
from apps.api.app.signals.cloud_gates import get_signal_cloud_gates
from apps.api.app.signals.cloud_models import SignalHistoryRow  # noqa: F401 — register mapper
from apps.api.app.signals.cloud_repository import (
    SignalCloudWriteDenied,
    SqlAlchemySignalCloudRepository,
)
from apps.api.app.signals.cloud_sync import drain_outbox_once, sync_health
from apps.api.app.signals.service import reset_signal_pipeline_for_tests
from scripts.phase4d_sqlite_import_dry_run import plan_import


def _offline_pg_session() -> Session:
    """SQLite + ATTACH app schema — offline Postgres-compatible shape tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _attach_app(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS app")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_cloud_gates_default_off(monkeypatch) -> None:
    monkeypatch.delenv("SIGNAL_SUPABASE_WRITES_ENABLED", raising=False)
    monkeypatch.delenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", raising=False)
    monkeypatch.delenv("SIGNAL_CLOUD_SYNC_ENABLED", raising=False)
    g = get_signal_cloud_gates()
    assert g.cloud_writes_allowed is False
    assert g.sync_allowed is False


def test_repository_refuses_writes_when_gated(monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "false")
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=True)
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    d = SignalPipeline(risk_state=SignalRiskState()).evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    try:
        repo.upsert_decision(owner_user_id=uuid.uuid4(), decision=d)
        raise AssertionError("expected gate denial")
    except SignalCloudWriteDenied:
        pass


def test_idempotent_cloud_insert_when_gates_bypassed_for_unit_test() -> None:
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=False)
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    d = SignalPipeline(risk_state=SignalRiskState()).evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    owner = uuid.uuid4()
    id1 = repo.upsert_decision(owner_user_id=owner, decision=d)
    session.commit()
    id2 = repo.upsert_decision(owner_user_id=owner, decision=d)
    session.commit()
    assert id1 == id2
    # Cross-owner isolation: other owner query empty.
    other = uuid.uuid4()
    assert repo.list_history(owner_user_id=other) == []
    mine = repo.list_history(owner_user_id=owner, limit=10)
    assert len(mine) == 1
    assert mine[0]["decision_id"] == d.decision_id
    assert mine[0]["persistence"] == "supabase"


def test_cross_user_access_denied_by_owner_filter() -> None:
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=False)
    candles = make_series(bullish_trend_closes())
    d = SignalPipeline(risk_state=SignalRiskState()).evaluate(
        symbol="ETHUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
    )
    owner_a = uuid.uuid4()
    owner_b = uuid.uuid4()
    repo.upsert_decision(owner_user_id=owner_a, decision=d)
    session.commit()
    assert repo.list_history(owner_user_id=owner_b) == []
    assert repo.analytics(owner_user_id=owner_b)["total_signals"] == 0


def test_local_outbox_and_sync_gated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "false")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "false")
    store = SignalHistoryStore(tmp_path / "o.sqlite3")
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(
        history_store=store, persist=True, risk_state=SignalRiskState()
    )
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action in {
        DecisionAction.BUY,
        DecisionAction.SELL,
        DecisionAction.HOLD,
        DecisionAction.BLOCKED,
    }
    stats = store.outbox_stats()
    assert stats["pending"] >= 1
    health = sync_health(store)
    assert health["sync_allowed"] is False
    assert health["outbox"]["pending"] >= 1
    result = drain_outbox_once(
        store=store,
        repo=SqlAlchemySignalCloudRepository(_offline_pg_session(), require_gates=False),
        owner_user_id=uuid.uuid4(),
        now_ms=now,
    )
    assert result["skipped_reason"] == "signal_cloud_sync_gated_off"


def test_sqlite_import_dry_run(tmp_path: Path) -> None:
    db = tmp_path / "imp.sqlite3"
    store = SignalHistoryStore(db)
    candles = make_series(bullish_trend_closes())
    SignalPipeline(history_store=store, persist=True, risk_state=SignalRiskState()).evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
    )
    report = plan_import(db)
    assert report["ok"] is True
    assert report["would_write_supabase"] is False
    assert report["row_counts"]["signal_history"] >= 1
    assert report["idempotency_check"]["pass"] is True


def test_api_sync_status_no_secrets_no_orders(tmp_path: Path) -> None:
    os.environ["PRIVATE_DATA_READS_ENABLED"] = "false"
    os.environ["AGENT_ALLOW_LIVE"] = "false"
    os.environ["SIGNAL_SUPABASE_WRITES_ENABLED"] = "false"
    clear_settings_cache()
    reset_signal_pipeline_for_tests(db_path=tmp_path / "api.sqlite3", persist=True)
    app = create_app(ApiSettings(private_data_reads_enabled=False))
    client = TestClient(app)
    res = client.get("/api/v1/signals/sync/status")
    assert res.status_code == 200
    body = res.json()
    assert body["execution_allowed"] is False
    assert body["trading_enabled"] is False
    assert body["cloud_writes_allowed"] is False
    blob = str(body).lower()
    assert "password" not in blob
    assert "service_role" not in blob
    assert "api_secret" not in blob

    st = client.get("/api/v1/signals/status").json()
    assert st["supabase_writes"] is False
    assert st["supabase_signal_persistence"]["cloud_writes_allowed"] is False


def test_schema_models_have_owner_and_utc() -> None:
    # Structural: decided_at timezone-aware assignment works on model.
    row = SignalHistoryRow(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        decision_id="dec_x",
        idempotent_key="idem_x",
        correlation_id="c",
        timestamp_ms=1,
        decided_at=datetime.now(timezone.utc),
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        strategy_version="4B.1.0",
        config_hash="abc",
        action="HOLD",
        signal_strength=0.0,
        directional_conviction=0.0,
        market_quality=1.0,
        risk_verdict="VETO",
        source_mode="SIMULATED",
        explanation="t",
        reason_codes=[],
        risk_json={},
        levels_json={},
        market_json={},
        indicators_json={},
    )
    assert row.owner_user_id is not None
    assert row.decided_at.tzinfo is not None
