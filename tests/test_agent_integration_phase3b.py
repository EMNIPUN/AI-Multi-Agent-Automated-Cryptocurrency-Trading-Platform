"""Phase 3B Part 3 — offline end-to-end telemetry integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agent.confirmed_candles import ConfirmedCandleSeries
from agent.market_data import Candle, PositionSnapshot, PositionStatus
from agent.runner import AgentRunner
from agent.strategies.base import Signal, SignalAction
from agent.strategies.evidence import evidence_payload
from agent.telemetry_ledger import TelemetryLedger, make_event
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.observability.types import (
    ExecutionMode,
    ObservabilityEventType,
    PipelineStep,
)
from tests.conftest import make_settings


def _bars(n: int = 40) -> list[Candle]:
    base = 1_700_000_000_000
    out: list[Candle] = []
    for i in range(n):
        price = 10.0 + i * 0.05
        out.append(
            Candle(
                start=base + i * 900_000,
                open=price,
                high=price + 0.2,
                low=price - 0.2,
                close=price + 0.1,
                volume=1.0,
            )
        )
    return out


def _series(candles: list[Candle]) -> ConfirmedCandleSeries:
    return ConfirmedCandleSeries(
        candles=candles,
        interval="15",
        newest_close_ms=candles[-1].start + 900_000,
        skipped_forming=1,
    )


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        private_data_reads_enabled=False,
        observability_fixture_mode=True,
        observability_live_stream_enabled=False,
        observability_ledger_path=None,
        exchange_wallet_reads_enabled=True,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def test_runner_to_ledger_to_api_hold_path(tmp_path: Path) -> None:
    ledger_path = tmp_path / "obs.sqlite"
    ledger = TelemetryLedger(ledger_path)
    settings = make_settings(dry_run=True)
    session = MagicMock()
    runner = AgentRunner(
        session,
        settings,
        signal_db_path=tmp_path / "sig.sqlite3",
        telemetry=ledger,
    )
    runner.journal = runner.journal.__class__(log_dir=tmp_path)
    flat = PositionSnapshot(status=PositionStatus.FLAT, reason="flat")
    hold = Signal(
        action=SignalAction.HOLD,
        reason="No cross",
        price=12.0,
        ema_fast=11.0,
        ema_slow=11.5,
        rsi=48.0,
        candle_start_ms=1_700_000_000_000 + 39 * 900_000,
        candle_close_ms=1_700_000_000_000 + 40 * 900_000,
        explanation_code="HOLD_NO_CROSS",
        strategy_id="ema_rsi",
        strategy_version="1",
        conditions=(("ema_cross_up", "FAIL"), ("ema_cross_down", "FAIL")),
    )
    candles = _bars()
    series = _series(candles)

    with (
        patch("agent.runner.get_equity", return_value=1000.0),
        patch("agent.runner.get_position", return_value=flat),
        patch("agent.runner.fetch_candles", return_value=candles),
        patch("agent.runner.filter_confirmed_candles", return_value=series),
        patch.object(runner.strategy, "evaluate", return_value=hold),
        patch.object(runner.executor, "execute") as execute,
        patch.object(runner.risk, "plan_trade") as plan_trade,
    ):
        assert runner.tick() is True
        execute.assert_not_called()
        plan_trade.assert_not_called()

    types = {e.event_type for e in ledger._newest(50)}
    assert ObservabilityEventType.AGENT_HEARTBEAT in types
    assert ObservabilityEventType.MARKET_CANDLE_CONFIRMED in types
    assert ObservabilityEventType.ANALYSIS_COMPLETED in types
    assert ObservabilityEventType.SIGNAL_GENERATED in types
    signal_ev = next(
        e for e in ledger._newest(50) if e.event_type is ObservabilityEventType.SIGNAL_GENERATED
    )
    assert signal_ev.payload["action"] == "HOLD"
    assert signal_ev.payload["explanation_code"] == "HOLD_NO_CROSS"
    assert "conditions" in signal_ev.payload

    clear_settings_cache()
    app = create_app(_settings(observability_ledger_path=str(ledger_path)))
    client = TestClient(app)
    resp = client.get("/api/v1/observability/worker-snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_mode"] == "live"
    assert body["signal_action"] == "HOLD"
    assert body["agent_status"] == "RUNNING"
    assert body["candles"], "confirmed recent_bars should project into candles"
    assert any(e["event_type"] == "signal.generated" for e in body["events"])
    assert any(m["action"] == "HOLD" for m in body["markers"])


def test_risk_blocked_unknown_position(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    settings = make_settings()
    runner = AgentRunner(
        MagicMock(),
        settings,
        signal_db_path=tmp_path / "sig.sqlite3",
        telemetry=ledger,
    )
    runner.journal = runner.journal.__class__(log_dir=tmp_path)
    unknown = PositionSnapshot(status=PositionStatus.UNKNOWN, reason="timeout")
    buy = Signal(
        action=SignalAction.BUY,
        reason="cross",
        price=12.0,
        ema_fast=12.0,
        ema_slow=11.0,
        rsi=40.0,
        candle_close_ms=2,
        signal_id="sig_buy",
        explanation_code="BUY_EMA_CROSS_UP_RSI_OK",
    )
    series = _series(_bars())
    with (
        patch("agent.runner.get_equity", return_value=1000.0),
        patch("agent.runner.get_position", return_value=unknown),
        patch("agent.runner.fetch_candles", return_value=series.candles),
        patch("agent.runner.filter_confirmed_candles", return_value=series),
        patch.object(runner.strategy, "evaluate", return_value=buy),
        patch.object(runner.risk, "plan_trade") as plan_trade,
        patch.object(runner.executor, "execute") as execute,
    ):
        assert runner.tick() is True
        plan_trade.assert_not_called()
        execute.assert_not_called()
    assert any(
        e.event_type is ObservabilityEventType.RISK_BLOCKED for e in ledger._newest(40)
    )


def test_stale_and_missing_heartbeat_projection(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    assert ledger.count() == 0

    clear_settings_cache()
    empty = TestClient(create_app(_settings(observability_ledger_path=str(ledger.path)))).get(
        "/api/v1/observability/worker-snapshot"
    )
    assert empty.status_code == 200
    assert empty.json()["data_mode"] == "unavailable"
    assert empty.json()["agent_status"] == "UNKNOWN"

    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    event = make_event(
        event_type=ObservabilityEventType.AGENT_HEARTBEAT,
        event_id="old-hb",
        message="old",
        execution_mode=ExecutionMode.DRY_RUN,
        pipeline_step=PipelineStep.MARKET_DATA,
    )
    ledger.record(event.model_copy(update={"occurred_at": old}))
    snap = ledger.snapshot(stale_after_seconds=60)
    assert snap.agent_status.value == "OFFLINE"
    assert snap.heartbeat_stale is True


def test_worker_and_wallet_reject_authenticated_browser(tmp_path: Path) -> None:
    ledger = tmp_path / "obs.sqlite"
    TelemetryLedger(ledger)
    clear_settings_cache()
    app = create_app(_settings(observability_ledger_path=str(ledger)))
    principal = AuthenticatedPrincipal(
        user_id="11111111-1111-1111-1111-111111111111",
        role="authenticated",
    )
    app.state.token_verifier = StaticMappingVerifier({"good": principal})
    client = TestClient(app)
    headers = {"Authorization": "Bearer good"}
    snap = client.get("/api/v1/observability/worker-snapshot", headers=headers)
    wallet = client.get("/api/v1/exchange/wallet", headers=headers)
    proxied = client.get(
        "/api/v1/observability/worker-snapshot",
        headers={"X-Forwarded-For": "1.2.3.4"},
    )
    assert snap.status_code == 403
    assert snap.json()["detail"] == "ownership_schema_required"
    assert wallet.status_code == 403
    assert wallet.json()["detail"] == "ownership_schema_required"
    assert proxied.status_code == 403
    assert proxied.json()["detail"] == "operator_diagnostic_proxy_forward_rejected"


def test_evidence_payload_hold_codes() -> None:
    settings = make_settings()
    signal = Signal(
        action=SignalAction.HOLD,
        reason="No cross",
        price=1.0,
        ema_fast=1.0,
        ema_slow=1.1,
        rsi=50.0,
        explanation_code="HOLD_NO_CROSS",
        conditions=(("ema_cross_up", "FAIL"),),
    )
    payload = evidence_payload(signal, settings)
    assert payload["explanation_code"] == "HOLD_NO_CROSS"
    assert payload["conditions"][0]["result"] == "FAIL"
    assert payload["rsi_overbought"] == settings.rsi_overbought


def test_telemetry_write_failure_does_not_break_tick(tmp_path: Path) -> None:
    settings = make_settings()
    runner = AgentRunner(
        MagicMock(),
        settings,
        signal_db_path=tmp_path / "sig.sqlite3",
        telemetry=MagicMock(safe_record=MagicMock(side_effect=RuntimeError("disk"))),
    )
    runner.journal = runner.journal.__class__(log_dir=tmp_path)
    flat = PositionSnapshot(status=PositionStatus.FLAT, reason="flat")
    series = _series(_bars())
    hold = Signal(action=SignalAction.HOLD, reason="x", price=1.0)
    with (
        patch("agent.runner.get_equity", return_value=1000.0),
        patch("agent.runner.get_position", return_value=flat),
        patch("agent.runner.fetch_candles", return_value=series.candles),
        patch("agent.runner.filter_confirmed_candles", return_value=series),
        patch.object(runner.strategy, "evaluate", return_value=hold),
    ):
        assert runner.tick() is True


def test_marker_requires_verified_candle_time(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.MARKET_CANDLE_CONFIRMED,
            event_id="c1",
            message="bar",
            payload={
                "recent_bars": [
                    {
                        "time": 1_700_000_000,
                        "open": 1,
                        "high": 2,
                        "low": 0.5,
                        "close": 1.5,
                        "volume": 1,
                    }
                ]
            },
        )
    )
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.SIGNAL_GENERATED,
            event_id="s1",
            message="aligned",
            payload={
                "action": "BUY",
                "price": 1.5,
                "candle_start_ms": 1_700_000_000_000,
                "explanation_code": "BUY_EMA_CROSS_UP_RSI_OK",
            },
        )
    )
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.SIGNAL_GENERATED,
            event_id="s2",
            message="orphan",
            payload={
                "action": "SELL",
                "price": 9.0,
                "candle_start_ms": 9_999_999_000_000,
                "explanation_code": "SELL_EMA_CROSS_DOWN_RSI_OK",
            },
        )
    )
    snap = ledger.snapshot()
    assert len(snap.markers) == 1
    assert snap.markers[0].action == "BUY"
    assert snap.markers[0].time == 1_700_000_000
