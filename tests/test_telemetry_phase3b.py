"""Phase 3B worker telemetry ledger — durable, sanitized, fail-closed reads."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from agent.telemetry_ledger import TelemetryLedger, make_event
from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.observability.types import ExecutionMode, ObservabilityEventType, PipelineStep


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
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _client(settings: ApiSettings, verifier=None) -> TestClient:
    clear_settings_cache()
    app = create_app(settings)
    if verifier is not None:
        app.state.token_verifier = verifier
    return TestClient(app)


def _heartbeat(ledger: TelemetryLedger, *, when: datetime, event_id: str = "hb-1") -> None:
    event = make_event(
        event_type=ObservabilityEventType.AGENT_HEARTBEAT,
        event_id=event_id,
        message="Worker tick started",
        symbol="HYPEUSDT",
        interval="15",
        env_scope="test",
        execution_mode=ExecutionMode.DRY_RUN,
        pipeline_step=PipelineStep.MARKET_DATA,
        payload={"dry_run": True, "api_key": "should-not-store"},
    )
    event = event.model_copy(update={"occurred_at": when})
    assert ledger.record(event) is True


def test_duplicate_event_id_is_ignored(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    event = make_event(
        event_type=ObservabilityEventType.AGENT_STARTED,
        event_id="same-id",
        message="started",
    )
    assert ledger.record(event) is True
    assert ledger.record(event) is False
    assert ledger.count() == 1


def test_payload_secrets_are_redacted(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    _heartbeat(ledger, when=datetime.now(timezone.utc))
    snap = ledger.snapshot()
    blob = snap.model_dump_json().lower()
    assert "should-not-store" not in blob
    assert "[redacted]" in blob


def test_missing_heartbeat_is_unknown(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.SIGNAL_GENERATED,
            event_id="sig-1",
            message="no cross",
            symbol="HYPEUSDT",
            payload={"action": "HOLD"},
        )
    )
    snap = ledger.snapshot()
    assert snap.agent_status.value == "UNKNOWN"
    assert snap.heartbeat_at is None
    assert snap.signal_action == "HOLD"
    assert snap.data_mode.value == "live"


def test_stale_heartbeat_is_offline(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    old = datetime.now(timezone.utc) - timedelta(seconds=600)
    _heartbeat(ledger, when=old)
    snap = ledger.snapshot(stale_after_seconds=120)
    assert snap.agent_status.value == "OFFLINE"
    assert snap.heartbeat_stale is True


def test_fresh_heartbeat_running_hold_does_not_demote(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")
    now = datetime.now(timezone.utc)
    _heartbeat(ledger, when=now)
    ledger.record(
        make_event(
            event_type=ObservabilityEventType.SIGNAL_GENERATED,
            event_id="hold-1",
            message="no cross",
            symbol="HYPEUSDT",
            payload={"action": "HOLD"},
        )
    )
    snap = ledger.snapshot(stale_after_seconds=120)
    assert snap.agent_status.value == "RUNNING"
    assert snap.signal_action == "HOLD"


def test_cursor_returns_only_newer_rows(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite", max_rows=3)
    for i in range(5):
        ledger.record(
            make_event(
                event_type=ObservabilityEventType.AGENT_HEARTBEAT,
                event_id=f"hb-{i}",
                message=f"tick {i}",
            )
        )
    assert ledger.count() == 3
    first = ledger.since(None, limit=1)[0]
    # cursor is seq; fetch after the oldest remaining row
    cursor = "1"
    # seq values may start above 1 after trim; use latest-2 via since(None)
    rows = ledger.since(None, limit=10)
    assert [e.event_id for e in rows] == ["hb-2", "hb-3", "hb-4"]
    newer = ledger.since(str(int(ledger.latest_cursor() or "0") - 1))
    assert newer[-1].event_id == "hb-4"
    assert first.event_id == "hb-2"
    _ = cursor


def test_safe_record_swallows_write_failure(tmp_path: Path) -> None:
    ledger = TelemetryLedger(tmp_path / "obs.sqlite")

    def _boom(_event) -> bool:
        raise RuntimeError("disk")

    ledger.record = _boom  # type: ignore[method-assign]
    event = make_event(
        event_type=ObservabilityEventType.AGENT_ERROR,
        event_id="err",
        message="disk",
    )
    assert ledger.safe_record(event) is False


def test_worker_snapshot_denied_with_user_token(tmp_path: Path) -> None:
    ledger = tmp_path / "obs.sqlite"
    TelemetryLedger(ledger)
    settings = _settings(observability_ledger_path=str(ledger))
    principal = AuthenticatedPrincipal(
        user_id="11111111-1111-1111-1111-111111111111",
        role="authenticated",
    )
    client = _client(settings, verifier=StaticMappingVerifier({"good": principal}))
    resp = client.get(
        "/api/v1/observability/worker-snapshot",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
    # JWT path requires ownership binding + PRIVATE_DATA_READS (still off).
    assert resp.json()["detail"] == "ownership_schema_required"


def test_worker_snapshot_unavailable_without_ledger() -> None:
    client = _client(_settings(observability_ledger_path=None))
    resp = client.get("/api/v1/observability/worker-snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_mode"] == "unavailable"
    assert body["agent_status"] == "UNKNOWN"
    assert body["events"] == []
    assert body["sample_label"] is None


def test_public_fixture_snapshot_unchanged() -> None:
    resp = _client(_settings()).get("/api/v1/observability/snapshot")
    assert resp.status_code == 200
    assert resp.json()["data_mode"] == "fixture"


def test_authenticated_sse_still_forbidden() -> None:
    principal = AuthenticatedPrincipal(
        user_id="22222222-2222-2222-2222-222222222222",
        role="authenticated",
    )
    client = _client(_settings(), verifier=StaticMappingVerifier({"good": principal}))
    resp = client.get(
        "/api/v1/observability/stream",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
