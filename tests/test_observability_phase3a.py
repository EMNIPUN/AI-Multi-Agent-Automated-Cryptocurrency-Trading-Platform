"""Phase 3A observability contracts — offline fixtures + auth negatives."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.app.auth.jwt_verifier import StaticMappingVerifier
from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.observability.fixtures import build_agent_fixture_snapshot
from apps.api.app.observability.store import ObservabilityEventBuffer
from apps.api.app.observability.types import ObservabilityEventType


def _settings(**kwargs) -> ApiSettings:
    base = dict(
        _env_file=None,
        api_host="127.0.0.1",
        cors_origins=[],
        database_url=None,
        private_data_reads_enabled=False,
        observability_fixture_mode=True,
        observability_live_stream_enabled=False,
        supabase_url="https://example.supabase.co",
        auth_jwt_mode="hs256",
        supabase_jwt_secret="test-only-hs256-secret-not-for-production-32b+",
        supabase_jwt_audience="authenticated",
        supabase_jwt_issuer="https://example.supabase.co/auth/v1",
    )
    base.update(kwargs)
    return ApiSettings(**base)


def _client(settings: ApiSettings | None = None, verifier=None) -> TestClient:
    clear_settings_cache()
    app = create_app(settings or _settings())
    if verifier is not None:
        app.state.token_verifier = verifier
    return TestClient(app)


def test_fixture_snapshot_labeled_sample() -> None:
    client = _client()
    resp = client.get("/api/v1/observability/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_mode"] == "fixture"
    assert body["sample_label"] == "SAMPLE"
    assert body["agent_status"] in {"IDLE", "OFFLINE", "UNKNOWN", "HALTED", "RUNNING"}
    assert body["execution_mode"] == "DRY_RUN"
    assert "SAMPLE" in " ".join(body.get("notes") or []) or body["sample_label"] == "SAMPLE"
    # No credential-looking keys in serialized payload
    blob = resp.text.lower()
    assert "api_key" not in blob
    assert "service_role" not in blob
    assert "jwt" not in blob or "schema_version" in blob


def test_paper_snapshot_submit_disabled() -> None:
    body = _client().get("/api/v1/observability/paper/snapshot").json()
    assert body["data_mode"] == "fixture"
    assert body["submit_controls_enabled"] is False
    assert body["broker_implemented"] is False


def test_live_stream_disabled_without_auth() -> None:
    client = _client()
    assert client.get("/api/v1/observability/stream").status_code == 401


def test_live_stream_forbidden_when_authenticated_but_flag_off() -> None:
    p = AuthenticatedPrincipal(
        user_id="11111111-1111-1111-1111-111111111111",
        role="authenticated",
    )
    client = _client(verifier=StaticMappingVerifier({"good": p}))
    resp = client.get(
        "/api/v1/observability/stream",
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "observability_live_stream_disabled"


def test_status_reports_fixture_mode() -> None:
    body = _client().get("/api/v1/observability/status").json()
    assert body["fixture_mode"] is True
    assert body["live_stream_enabled"] is False
    assert body["private_data_reads_enabled"] is False


def test_private_reads_remain_false_default() -> None:
    settings = _settings()
    assert settings.private_data_reads_enabled is False


def test_event_buffer_dedup_and_cursor() -> None:
    snap = build_agent_fixture_snapshot()
    buf = ObservabilityEventBuffer()
    n = buf.extend(snap.events)
    assert n == len(snap.events)
    assert buf.extend(snap.events) == 0  # idempotent
    mid = snap.events[2].event_id
    tail = buf.since(mid)
    assert all(e.event_id != mid for e in tail)
    assert len(tail) == len(snap.events) - 3


def test_fixture_contains_required_event_types() -> None:
    types = {e.event_type for e in build_agent_fixture_snapshot().events}
    assert ObservabilityEventType.AGENT_HEARTBEAT in types
    assert ObservabilityEventType.SIGNAL_GENERATED in types
    assert ObservabilityEventType.RISK_BLOCKED in types


def test_fixture_mode_off_without_private_reads_fail_closed() -> None:
    client = _client(
        _settings(
            observability_fixture_mode=False,
            private_data_reads_enabled=False,
        )
    )
    assert client.get("/api/v1/observability/snapshot").status_code == 503


def test_no_trading_routes_on_observability() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "apps" / "api" / "app" / "observability" / "router.py"
    text = src.read_text(encoding="utf-8")
    assert "@router.post" not in text
    assert "place_order" not in text
    assert "set_leverage" not in text
