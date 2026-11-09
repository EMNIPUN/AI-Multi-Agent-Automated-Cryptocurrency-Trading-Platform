"""Phase 2A offline tests — FastAPI foundation + schema metadata (no Supabase/Bybit)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.schema import CreateTable

from apps.api.app.config import (
    ApiSettings,
    clear_settings_cache,
    get_api_settings,
)
from apps.api.app.factory import create_app
from apps.api.app.models import AgentDecision, Base, StrategyConfig, SystemEvent


@pytest.fixture(autouse=True)
def _clear_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AGENT_DRY_RUN", "true")
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    settings = ApiSettings(
        _env_file=None,
        api_host="127.0.0.1",
        api_debug=False,
        cors_origins=[],
        database_url=None,
        database_ssl_require=True,
        app_env="test",
    )
    app = create_app(settings)
    return TestClient(app)


def test_health_liveness(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
    text = resp.text.lower()
    assert "api_key" not in text
    assert "secret" not in text
    assert "password" not in text


def test_system_status_safe_contract(client: TestClient) -> None:
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["read_only_api"] is True
    assert body["trading_http_endpoints_enabled"] is False
    assert body["private_data_routes_enabled"] is False
    assert body["authentication_required_for_private_data"] is True
    assert body["database_configured"] is False
    assert body["agent_dry_run_default"] is True
    assert body["agent_allow_live_default"] is False
    assert body["bybit_env"] == "testnet"
    assert body["api_bind_host"] == "127.0.0.1"
    assert body["cors_origins_configured"] == 0
    assert "sqlite" in body["execution_source_of_truth"].lower()
    # No secrets / URLs with credentials
    dumped = resp.text.lower()
    assert "bybit_api" not in dumped
    assert "postgresql://" not in dumped
    assert "password" not in dumped


def test_private_stub_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/private/disabled")
    assert resp.status_code == 401


def test_root_points_to_safe_routes(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["read_only"] is True
    assert body["trading_endpoints"] is False
    assert body["health"] == "/health"


def test_cors_wildcard_rejected() -> None:
    settings = ApiSettings(_env_file=None, cors_origins=["*"])
    assert settings.cors_origins == []
    settings2 = ApiSettings(_env_file=None, cors_origins="*")  # type: ignore[arg-type]
    assert settings2.cors_origins == []


def test_api_host_rejects_all_interfaces() -> None:
    settings = ApiSettings(_env_file=None, api_host="0.0.0.0")
    assert settings.api_host == "127.0.0.1"


def test_remote_ssl_connect_args() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@db.example.supabase.co:5432/postgres",
        database_ssl_require=True,
    )
    assert settings.remote_database_requires_ssl() is True
    assert settings.engine_connect_args().get("sslmode") == "require"


def test_localhost_db_skips_forced_ssl() -> None:
    settings = ApiSettings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@127.0.0.1:5432/postgres",
        database_ssl_require=True,
    )
    assert settings.remote_database_requires_ssl() is False
    assert settings.engine_connect_args() == {}


def test_model_metadata_schema_and_tables() -> None:
    tables = Base.metadata.tables
    assert "app.agent_decisions" in tables
    assert "app.system_events" in tables
    assert "app.strategy_configs" in tables

    decisions = tables["app.agent_decisions"]
    cols = {c.name for c in decisions.columns}
    assert {"id", "created_at", "env_scope", "symbol", "action", "signal_id"} <= cols

    events = tables["app.system_events"]
    assert "event_type" in {c.name for c in events.columns}

    configs = tables["app.strategy_configs"]
    assert "enabled" in {c.name for c in configs.columns}

    # Compile CREATE for Postgres dialect offline (no network).
    from sqlalchemy.dialects import postgresql

    ddl = str(CreateTable(AgentDecision.__table__).compile(dialect=postgresql.dialect()))
    assert "agent_decisions" in ddl
    assert "JSONB" in ddl.upper() or "JSON" in ddl.upper()


def test_models_are_not_execution_ledger() -> None:
    # Phase 2A catalog rows stay observational. Fills live in the owner-scoped
    # intent tables added when the execution ledger moved into the ORM.
    names = {t.name for t in Base.metadata.sorted_tables}
    assert "order_intents" in names
    assert "order_executions" in names
    intent_cols = {c.name for c in Base.metadata.tables["app.order_intents"].columns}
    assert "owner_user_id" in intent_cols
    assert "filled_qty" in intent_cols
    decision_cols = {c.name for c in AgentDecision.__table__.columns}
    assert "filled_qty" not in decision_cols
    assert AgentDecision.__tablename__ == "agent_decisions"
    assert SystemEvent.__tablename__ == "system_events"
    assert StrategyConfig.__tablename__ == "strategy_configs"


def test_alembic_revision_upgrade_and_downgrade_present() -> None:
    root = Path(__file__).resolve().parents[1]
    rev = (
        root
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20261104_0001_initial_app_schema.py"
    )
    assert rev.is_file()
    text = rev.read_text(encoding="utf-8")
    assert "def upgrade()" in text
    assert "def downgrade()" in text
    assert "CREATE SCHEMA IF NOT EXISTS app" in text
    assert "agent_decisions" in text
    assert "system_events" in text
    assert "strategy_configs" in text
    assert "drop_table(\"agent_decisions\"" in text or "drop_table('agent_decisions'" in text
    assert "NOT an authoritative" in text or "observational" in text.lower()


def test_app_imports_without_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    clear_settings_cache()
    from apps.api.main import app

    assert app.title
    # Ignore local .env so developer DATABASE_URL does not fail this offline case.
    settings = ApiSettings(_env_file=None, database_url=None)
    assert settings.database_configured is False


def test_no_trading_route_paths_registered(client: TestClient) -> None:
    paths = {getattr(r, "path", None) for r in client.app.routes}
    forbidden = {
        "/orders",
        "/api/v1/orders",
        "/api/v1/orders/create",
        "/api/v1/orders/cancel",
        "/api/v1/leverage",
        "/api/v1/agent/live",
        "/api/v1/emergency/reset",
    }
    assert paths.isdisjoint(forbidden)


def test_startup_prints_db_not_configured(capsys: pytest.CaptureFixture[str]) -> None:
    from apps.api.app.factory import _print_database_status

    settings = ApiSettings(_env_file=None, database_url=None)
    _print_database_status(settings)
    out = capsys.readouterr().out
    assert "not_configured" in out
    assert "password" not in out.lower()
