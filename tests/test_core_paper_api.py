"""Prompt 65B — paper read API tests (local, no exchange / cloud / mutations)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.integration import PAPER_BROKER_AUTO_ATTACH
from agent.paper.models import PaperCandle
from agent.paper.store import PaperStore
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app


def _seed_db(path: Path) -> str:
    store = PaperStore(path)
    broker = PaperBroker(
        store,
        PaperBrokerConfig(
            initial_balance=Decimal("1000"),
            fee_rate=Decimal("0.001"),
            slippage_bps=Decimal("5"),
        ),
    )
    sess = broker.create_session(now_ms=1_000, session_id="ps_test_65b")
    broker.submit_signal(
        session_id=sess.session_id,
        signal=PaperSignalInput(
            signal_id="sig_api_1",
            symbol="BTCUSDT",
            category="spot",
            action="BUY",
            risk_verdict="APPROVED",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit=Decimal("110"),
            position_notional=Decimal("100"),
            signal_candle_start_ms=1000,
            created_ms=1000,
        ),
    )
    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=2000,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=3000,
            open=Decimal("108"),
            high=Decimal("111"),
            low=Decimal("107"),
            close=Decimal("110"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    return sess.session_id


def _client(tmp_path: Path, *, enabled: bool, db_name: str = "paper.sqlite3") -> TestClient:
    clear_settings_cache()
    db = tmp_path / db_name
    settings = ApiSettings(
        _env_file=None,
        paper_read_api_enabled=enabled,
        paper_sqlite_path=str(db),
        api_host="127.0.0.1",
        api_debug=True,
        private_data_reads_enabled=False,
        database_url=None,
        cors_origins=[],
    )
    app = create_app(settings)
    return TestClient(app)


def test_feature_gate_disabled_by_default(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=False)
    r = client.get("/api/v1/paper/status")
    assert r.status_code == 200
    body = r.json()
    assert body["paper_read_api_enabled"] is False
    assert body["broker_auto_attach"] is False
    assert body["execution_allowed"] is False


def test_disabled_blocks_data_routes_no_db_create(tmp_path: Path) -> None:
    db = tmp_path / "should_not_exist.sqlite3"
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        paper_read_api_enabled=False,
        paper_sqlite_path=str(db),
        api_host="127.0.0.1",
    )
    client = TestClient(create_app(settings))
    r = client.get("/api/v1/paper/sessions")
    assert r.status_code == 503
    assert not db.exists()
    assert PAPER_BROKER_AUTO_ATTACH is False


def test_empty_db_lists_sessions(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=True, db_name="missing.sqlite3")
    r = client.get("/api/v1/paper/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["data_label"] == "SIMULATED / PAPER ONLY"


def test_session_account_positions_orders_fills(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    sid = _seed_db(db)
    mtime_before = db.stat().st_mtime_ns
    size_before = db.stat().st_size

    client = _client(tmp_path, enabled=True)
    st = client.get("/api/v1/paper/status")
    assert st.status_code == 200
    assert st.json()["paper_read_api_enabled"] is True
    assert st.json()["session_count"] == 1

    sessions = client.get("/api/v1/paper/sessions")
    assert sessions.status_code == 200
    assert sessions.json()["total"] == 1
    assert sessions.json()["items"][0]["session_id"] == sid

    acct = client.get(f"/api/v1/paper/sessions/{sid}/account")
    assert acct.status_code == 200
    a = acct.json()
    assert Decimal(a["initial_balance"]) == Decimal("1000")
    assert a["available_balance"]  # decimal string
    assert Decimal(a["available_balance"]) != Decimal("NaN")
    assert Decimal(a["reserved_capital"]) == Decimal("0")
    assert a["data_label"] == "SIMULATED / PAPER ONLY"
    # After TP close, open count 0
    assert a["open_position_count"] == 0

    closed = client.get(
        f"/api/v1/paper/sessions/{sid}/positions",
        params={"status": "CLOSED"},
    )
    assert closed.status_code == 200
    items = closed.json()["items"]
    assert len(items) == 1
    assert items[0]["symbol"] == "BTCUSDT"
    assert items[0]["exit_reason"] == "TAKE_PROFIT"
    assert items[0]["realized_pnl"]  # string decimal

    orders = client.get(f"/api/v1/paper/sessions/{sid}/orders")
    assert orders.status_code == 200
    assert len(orders.json()["items"]) >= 1

    fills = client.get(f"/api/v1/paper/sessions/{sid}/fills")
    assert fills.status_code == 200
    assert len(fills.json()["items"]) >= 2

    events = client.get(f"/api/v1/paper/sessions/{sid}/events")
    assert events.status_code == 200
    assert len(events.json()["items"]) >= 1

    # Read-only: file not mutated
    assert db.stat().st_size == size_before
    assert db.stat().st_mtime_ns == mtime_before


def test_missing_and_invalid_session(tmp_path: Path) -> None:
    _seed_db(tmp_path / "paper.sqlite3")
    client = _client(tmp_path, enabled=True)
    assert client.get("/api/v1/paper/sessions/ps_does_not_exist").status_code == 404
    assert client.get("/api/v1/paper/sessions/bad id!!").status_code == 400


def test_symbol_filter_and_pagination(tmp_path: Path) -> None:
    _seed_db(tmp_path / "paper.sqlite3")
    client = _client(tmp_path, enabled=True)
    sid = "ps_test_65b"
    eth = client.get(
        f"/api/v1/paper/sessions/{sid}/positions",
        params={"symbol": "ETHUSDT", "status": "CLOSED"},
    )
    assert eth.status_code == 200
    assert eth.json()["items"] == []

    btc = client.get(
        f"/api/v1/paper/sessions/{sid}/orders",
        params={"symbol": "BTCUSDT", "limit": 1, "offset": 0},
    )
    assert btc.status_code == 200
    assert len(btc.json()["items"]) <= 1

    bad = client.get(
        f"/api/v1/paper/sessions/{sid}/orders",
        params={"symbol": "bad symbol"},
    )
    assert bad.status_code == 400


def test_signal_link_lookup(tmp_path: Path) -> None:
    _seed_db(tmp_path / "paper.sqlite3")
    client = _client(tmp_path, enabled=True)
    linked = client.get("/api/v1/paper/orders/by-signal/sig_api_1")
    assert linked.status_code == 200
    body = linked.json()
    assert body["linked"] is True
    assert len(body["orders"]) >= 1

    missing = client.get("/api/v1/paper/orders/by-signal/sig_none")
    assert missing.status_code == 200
    assert missing.json()["linked"] is False
    assert missing.json()["message"] == "No paper trade linked to this signal"


def test_malformed_database(tmp_path: Path) -> None:
    bad = tmp_path / "paper.sqlite3"
    bad.write_text("not a sqlite database", encoding="utf-8")
    client = _client(tmp_path, enabled=True)
    # status may report unreadable; data routes 500
    r = client.get("/api/v1/paper/sessions")
    assert r.status_code in {500, 503}


def test_no_implicit_session_creation(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=True, db_name="absent.sqlite3")
    client.get("/api/v1/paper/sessions")
    client.get("/api/v1/paper/status")
    assert not (tmp_path / "absent.sqlite3").exists()


def test_root_advertises_paper_gate() -> None:
    clear_settings_cache()
    app = create_app(
        ApiSettings(_env_file=None, paper_read_api_enabled=False, api_host="127.0.0.1")
    )
    r = TestClient(app).get("/")
    assert r.json()["paper_read_api_enabled"] is False
    assert r.json()["trading_endpoints"] is False


def test_no_mutation_methods_registered() -> None:
    clear_settings_cache()
    app = create_app(
        ApiSettings(_env_file=None, paper_read_api_enabled=True, api_host="127.0.0.1")
    )
    paths = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if path.startswith("/api/v1/paper"):
            paths.append((path, methods))
            assert not (methods & {"POST", "PUT", "PATCH", "DELETE"})


def test_module_safety_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "apps" / "api" / "app" / "paper"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "supabase" not in text
        assert "openai" not in text
        assert "place_order" not in text
        assert "bybit_private" not in text
