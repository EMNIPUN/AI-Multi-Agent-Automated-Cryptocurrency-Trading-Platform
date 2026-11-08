"""Gate C1 — offline security validation (no cloud writes, no exchange orders)."""

from __future__ import annotations

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
    validate_decision_sync_payload,
)
from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState
from agent.multi_agent.signal_history_store import SignalHistoryStore
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


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _attach(dbapi_conn, _rec):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("ATTACH DATABASE ':memory:' AS app")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _decision():
    candles = make_series(bullish_trend_closes())
    return SignalPipeline(risk_state=SignalRiskState()).evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
    )


@pytest.mark.parametrize(
    "writes,approved,sync,expect_writes,expect_sync",
    [
        (False, False, False, False, False),
        (True, False, False, False, False),
        (False, True, False, False, False),
        (True, True, False, True, False),
        (True, True, True, True, True),
    ],
)
def test_cloud_gate_matrix(
    monkeypatch, writes, approved, sync, expect_writes, expect_sync
) -> None:
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true" if writes else "false")
    monkeypatch.setenv(
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "true" if approved else "false"
    )
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "true" if sync else "false")
    g = get_signal_cloud_gates()
    assert g.cloud_writes_allowed is expect_writes
    assert g.sync_allowed is expect_sync


def test_dual_gate_denies_repository_write(monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "false")
    repo = SqlAlchemySignalCloudRepository(_session(), require_gates=True)
    with pytest.raises(SignalCloudWriteDenied):
        repo.upsert_decision(owner_user_id=uuid.uuid4(), decision=_decision())


def test_owner_nested_isolation_and_get() -> None:
    session = _session()
    repo = SqlAlchemySignalCloudRepository(session, require_gates=False)
    owner_a = uuid.uuid4()
    owner_b = uuid.uuid4()
    d = _decision()
    repo.upsert_decision(owner_user_id=owner_a, decision=d)
    session.commit()
    assert repo.get_decision(owner_user_id=owner_b, decision_id=d.decision_id) is None
    assert repo.list_contributions(owner_user_id=owner_b, decision_id=d.decision_id) == []
    assert (
        repo.list_risk_events(owner_user_id=owner_b, decision_id=d.decision_id) == []
    )
    mine = repo.get_decision(owner_user_id=owner_a, decision_id=d.decision_id)
    assert mine is not None
    assert mine["decision_id"] == d.decision_id
    contribs = repo.list_contributions(owner_user_id=owner_a, decision_id=d.decision_id)
    assert len(contribs) >= 1
    assert mine["execution_allowed"] is False
    assert mine["not_an_order"] is True


def test_payload_contract_and_execution_invariants() -> None:
    d = _decision()
    payload = build_decision_sync_payload(d)
    assert payload["payload_schema_version"] == PAYLOAD_SCHEMA_VERSION
    assert payload["execution_allowed"] is False
    assert payload["not_an_order"] is True
    assert d.execution_allowed is False
    ok, reason = validate_decision_sync_payload(payload)
    assert ok and reason == "ok"
    bad = dict(payload)
    bad["decision"] = dict(payload["decision"])
    bad["decision"]["execution_allowed"] = True
    ok2, reason2 = validate_decision_sync_payload(bad)
    assert ok2 is False
    assert "execution_allowed" in reason2


def test_sync_requires_owner_even_when_gates_forced(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "true")
    monkeypatch.delenv("SIGNAL_CLOUD_OWNER_USER_ID", raising=False)
    store = SignalHistoryStore(tmp_path / "c1.sqlite3")
    candles = make_series(bullish_trend_closes())
    SignalPipeline(
        history_store=store, persist=True, risk_state=SignalRiskState()
    ).evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
    )
    result = drain_outbox_once(
        store=store,
        repo=SqlAlchemySignalCloudRepository(_session(), require_gates=False),
        now_ms=1,
    )
    assert result["synced"] == 0
    assert result["skipped_reason"] == "signal_cloud_owner_user_id_unset"
    assert resolve_sync_owner_binding().sync_owner_ready is False


def test_cloud_api_rejects_unauth_and_blocks_private_reads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PRIVATE_DATA_READS_ENABLED", "false")
    clear_settings_cache()
    reset_signal_pipeline_for_tests(db_path=tmp_path / "c1api.sqlite3", persist=True)
    app = create_app(ApiSettings(_env_file=None, private_data_reads_enabled=False, database_url=None))
    app.state.token_verifier = StaticMappingVerifier(
        {
            "good": AuthenticatedPrincipal(
                user_id=str(uuid.uuid4()), role="authenticated"
            ),
            "bad": AuthError("invalid_token"),
        }
    )
    client = TestClient(app)
    assert client.get("/api/v1/signals/cloud/history").status_code == 401
    assert (
        client.get(
            "/api/v1/signals/cloud/history",
            headers={"Authorization": "Bearer bad"},
        ).status_code
        == 401
    )
    # Auth OK but private reads kill-switch still closed
    res = client.get(
        "/api/v1/signals/cloud/history",
        headers={"Authorization": "Bearer good"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "ownership_schema_required"


def test_sqlite_survives_gated_cloud_outage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SIGNAL_CLOUD_SYNC_ENABLED", "false")
    store = SignalHistoryStore(tmp_path / "surv.sqlite3")
    candles = make_series(bullish_trend_closes())
    d = SignalPipeline(
        history_store=store, persist=True, risk_state=SignalRiskState()
    ).evaluate(
        symbol="ETHUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
    )
    assert store.get_decision(d.decision_id) is not None
    assert store.outbox_stats()["pending"] >= 1
    # Drain gated off — local durability unchanged
    r = drain_outbox_once(
        store=store,
        repo=SqlAlchemySignalCloudRepository(_session(), require_gates=False),
        now_ms=1,
    )
    assert r["skipped_reason"] == "signal_cloud_sync_gated_off"
    assert store.get_decision(d.decision_id) is not None
