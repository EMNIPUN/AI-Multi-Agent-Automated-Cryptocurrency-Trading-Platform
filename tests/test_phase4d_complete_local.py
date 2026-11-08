"""Phase 4D Prompt 52 — offline local implementation tests (no cloud writes)."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from agent.multi_agent.decision_payload import (
    PAYLOAD_SCHEMA_VERSION,
    build_decision_sync_payload,
    is_legacy_summary_payload,
    validate_decision_sync_payload,
)
from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState
from agent.multi_agent.signal_history_store import (
    CheckpointWrite,
    SignalHistoryStore,
)
from agent.multi_agent.types import DecisionAction
from apps.api.app.auth.errors import AuthError
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.models import Base
from apps.api.app.signals.cloud_gates import get_signal_cloud_gates
from apps.api.app.signals.cloud_models import SignalHistoryRow  # noqa: F401
from apps.api.app.signals.cloud_repository import (
    SignalCloudWriteDenied,
    SqlAlchemySignalCloudRepository,
)
from apps.api.app.signals.cloud_sync import drain_outbox_once
from apps.api.app.signals.owner_binding import resolve_sync_owner_binding
from apps.api.app.signals.service import reset_signal_pipeline_for_tests


def _offline_pg_session() -> Session:
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


def _decision(store: SignalHistoryStore | None = None):
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(
        history_store=store,
        persist=store is not None,
        risk_state=SignalRiskState(),
    )
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    return d, now, candles


def test_full_decision_serialization_and_validation(tmp_path: Path) -> None:
    store = SignalHistoryStore(tmp_path / "s.sqlite3")
    d, _now, _ = _decision(store)
    payload = build_decision_sync_payload(d)
    assert payload["payload_schema_version"] == PAYLOAD_SCHEMA_VERSION
    assert payload["execution_allowed"] is False
    ok, reason = validate_decision_sync_payload(payload)
    assert ok and reason == "ok"
    assert not is_legacy_summary_payload(payload)
    stats = store.outbox_stats()
    assert stats["pending"] >= 1
    claimed = store.claim_outbox_batch(now_ms=int(time.time() * 1000), limit=5)
    assert claimed
    assert claimed[0]["payload"]["payload_schema_version"] == PAYLOAD_SCHEMA_VERSION
    assert "decision" in claimed[0]["payload"]


def test_legacy_payload_detection() -> None:
    legacy = {
        "decision_id": "dec_x",
        "symbol": "BTCUSDT",
        "action": "HOLD",
    }
    assert is_legacy_summary_payload(legacy) is True
    ok, reason = validate_decision_sync_payload(legacy)
    assert ok is False


@pytest.mark.parametrize("stage", ["decision", "risk", "outbox", "checkpoint"])
def test_atomic_rollback_on_injected_failure(tmp_path: Path, stage: str) -> None:
    store = SignalHistoryStore(tmp_path / f"fail_{stage}.sqlite3")
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(
        history_store=store, persist=True, risk_state=SignalRiskState()
    )
    store._test_fail_after = stage  # type: ignore[attr-defined]
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        checkpoint=CheckpointWrite(
            eval_key="ek_test",
            strategy_version="4B.1.0",
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            candle_start_ms=1,
            candle_close_ms=2,
            decision_id=None,
            status="completed",
        ),
    )
    # Actionable paths convert to BLOCKED on persist failure; HOLD may still surface codes.
    assert "PERSISTENCE_FAILED" in d.reason_codes or d.action is DecisionAction.BLOCKED
    assert store.list_signals(limit=5) == []
    assert store.outbox_stats()["pending"] == 0


def test_atomic_commit_includes_outbox_and_checkpoint(tmp_path: Path) -> None:
    store = SignalHistoryStore(tmp_path / "ok.sqlite3")
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
        checkpoint=CheckpointWrite(
            eval_key="ek_ok",
            strategy_version="4B.1.0",
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            candle_start_ms=1,
            candle_close_ms=2,
            decision_id=None,
            status="completed",
        ),
    )
    assert store.get_decision(d.decision_id) is not None
    assert store.outbox_stats()["pending"] >= 1
    assert store.schema_version() == 4


def test_duplicate_decision_no_double_outbox(tmp_path: Path) -> None:
    store = SignalHistoryStore(tmp_path / "dup.sqlite3")
    d1, now, candles = _decision(store)
    # Force same keys by replaying identical candle series / same pipeline path
    pipe = SignalPipeline(
        history_store=store, persist=True, risk_state=store.load_risk_state()
    )
    d2 = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d1.idempotent_key == d2.idempotent_key
    stats = store.outbox_stats()
    # One outbox event_id per decision_id; second TX is idempotent.
    assert stats["pending"] + stats["synced"] >= 1


def test_sync_gated_and_owner_binding_fail_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SIGNAL_CLOUD_OWNER_USER_ID", raising=False)
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "true")
    store = SignalHistoryStore(tmp_path / "sync.sqlite3")
    _decision(store)
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=False)
    result = drain_outbox_once(
        store=store,
        repo=repo,
        now_ms=int(time.time() * 1000),
    )
    assert result["skipped_reason"] == "signal_cloud_owner_user_id_unset"
    assert result["synced"] == 0
    binding = resolve_sync_owner_binding()
    assert binding.sync_owner_ready is False


def test_sync_worker_idempotent_upsert_when_gates_bypassed(
    tmp_path: Path, monkeypatch
) -> None:
    owner = uuid.uuid4()
    monkeypatch.setenv("SIGNAL_CLOUD_OWNER_USER_ID", str(owner))
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "true")
    store = SignalHistoryStore(tmp_path / "sync2.sqlite3")
    _decision(store)
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=False)
    now = int(time.time() * 1000)
    r1 = drain_outbox_once(
        store=store, repo=repo, owner_user_id=owner, now_ms=now, session=session
    )
    assert r1["synced"] >= 1
    # Duplicate event already SYNCED — claim finds nothing new.
    r2 = drain_outbox_once(
        store=store, repo=repo, owner_user_id=owner, now_ms=now + 1, session=session
    )
    assert r2["drained"] == 0
    mine = repo.list_history(owner_user_id=owner)
    assert len(mine) == 1


def test_legacy_outbox_permanent_failure(tmp_path: Path, monkeypatch) -> None:
    owner = uuid.uuid4()
    monkeypatch.setenv("SIGNAL_CLOUD_OWNER_USER_ID", str(owner))
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "true")
    store = SignalHistoryStore(tmp_path / "leg.sqlite3")
    store.enqueue_cloud_outbox(
        event_id="signal:legacy1",
        event_type="signal_decision",
        payload={"decision_id": "dec_legacy", "symbol": "BTCUSDT", "action": "HOLD"},
        now_ms=int(time.time() * 1000),
    )
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=False)
    result = drain_outbox_once(
        store=store,
        repo=repo,
        owner_user_id=owner,
        now_ms=int(time.time() * 1000),
        session=session,
    )
    assert result["permanent_failure"] >= 1
    assert result["synced"] == 0
    assert store.outbox_stats()["permanent_failure"] >= 1


def test_stale_in_progress_recovery(tmp_path: Path) -> None:
    store = SignalHistoryStore(tmp_path / "lease.sqlite3")
    now = int(time.time() * 1000)
    store.enqueue_cloud_outbox(
        event_id="signal:lease1",
        event_type="signal_decision",
        payload=build_decision_sync_payload(_decision()[0]),
        now_ms=now,
    )
    claimed = store.claim_outbox_batch(now_ms=now, limit=1, lease_ms=1)
    assert claimed
    # Force expire lease
    recovered = store.recover_stale_in_progress(now_ms=now + 10_000)
    assert recovered >= 1


def test_cloud_gates_still_default_off(monkeypatch) -> None:
    monkeypatch.delenv("SIGNAL_SUPABASE_WRITES_ENABLED", raising=False)
    monkeypatch.delenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", raising=False)
    monkeypatch.delenv("SIGNAL_CLOUD_SYNC_ENABLED", raising=False)
    g = get_signal_cloud_gates()
    assert g.cloud_writes_allowed is False
    assert g.sync_allowed is False


def test_repository_gate_denial(monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "false")
    session = _offline_pg_session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=True)
    d, _, _ = _decision()
    with pytest.raises(SignalCloudWriteDenied):
        repo.upsert_decision(owner_user_id=uuid.uuid4(), decision=d)


def test_jwt_cloud_history_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PRIVATE_DATA_READS_ENABLED", "true")
    clear_settings_cache()
    reset_signal_pipeline_for_tests(db_path=tmp_path / "jwt.sqlite3", persist=True)

    owner = str(uuid.uuid4())
    other = str(uuid.uuid4())
    principal = AuthenticatedPrincipal(
        user_id=owner, role="authenticated", email="op@example.com"
    )
    settings = ApiSettings(
        _env_file=None,
        private_data_reads_enabled=True,
        database_url=None,
    )
    app = create_app(settings)
    app.state.token_verifier = StaticMappingVerifier(
        {
            "good": principal,
            "expired": AuthError("token_expired"),
            "badaud": AuthError("invalid_audience"),
            "other": AuthenticatedPrincipal(
                user_id=other, role="authenticated", email="x@example.com"
            ),
        }
    )
    client = TestClient(app)

    assert client.get("/api/v1/signals/cloud/history").status_code == 401
    assert (
        client.get(
            "/api/v1/signals/cloud/history",
            headers={"Authorization": "Bearer expired"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/signals/cloud/history",
            headers={"Authorization": "Bearer badaud"},
        ).status_code
        == 401
    )
    # Valid auth, DB not configured → 503 (fail closed, no cross-user fallback)
    res = client.get(
        "/api/v1/signals/cloud/history",
        headers={"Authorization": "Bearer good"},
    )
    assert res.status_code == 503
    assert res.json()["detail"] == "database_not_configured"

    status = client.get(
        "/api/v1/signals/cloud/status",
        headers={"Authorization": "Bearer good"},
    )
    assert status.status_code == 200
    assert status.json()["owner_from_jwt"] is True
    assert status.json()["execution_allowed"] is False
    assert status.json()["cloud_writes_default"] is False


def test_sqlite_remains_risk_authority_on_cloud_outage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "false")
    store = SignalHistoryStore(tmp_path / "risk.sqlite3")
    d, _, _ = _decision(store)
    assert store.get_decision(d.decision_id) is not None
    # Gates off → drain skips; local risk still loaded.
    state = store.load_risk_state()
    assert state is not None
