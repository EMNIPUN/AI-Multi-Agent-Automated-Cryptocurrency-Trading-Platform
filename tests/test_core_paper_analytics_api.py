"""Prompt 67A — paper analytics API tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from tests.helpers_paper_analytics_seed import seed_mixed_session


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
    return TestClient(create_app(settings))


def test_analytics_disabled_by_default(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=False)
    r = client.get("/api/v1/paper/sessions/ps_x/analytics")
    assert r.status_code == 503


def test_disabled_does_not_create_db(tmp_path: Path) -> None:
    db = tmp_path / "nope.sqlite3"
    clear_settings_cache()
    client = TestClient(
        create_app(
            ApiSettings(
                _env_file=None,
                paper_read_api_enabled=False,
                paper_sqlite_path=str(db),
                api_host="127.0.0.1",
            )
        )
    )
    client.get("/api/v1/paper/sessions/ps_x/analytics")
    assert not db.exists()


def test_valid_session_analytics(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    sid = seed_mixed_session(db)
    size = db.stat().st_size
    client = _client(tmp_path, enabled=True)
    r = client.get(f"/api/v1/paper/sessions/{sid}/analytics")
    assert r.status_code == 200
    body = r.json()
    assert body["data_label"] == "SIMULATED / PAPER ONLY"
    assert body["closed_trades"] >= 5
    assert body["win_rate_pct"]["status"] in {"available", "empty"}
    assert "Infinity" not in r.text
    assert "NaN" not in r.text
    assert isinstance(body["net_realized_pnl"], str)
    assert db.stat().st_size == size

    trades = client.get(f"/api/v1/paper/sessions/{sid}/analytics/trades")
    assert trades.status_code == 200
    assert len(trades.json()["items"]) >= 1

    eq = client.get(
        f"/api/v1/paper/sessions/{sid}/analytics/equity",
        params={"series": "marked"},
    )
    assert eq.status_code == 200

    sym = client.get(f"/api/v1/paper/sessions/{sid}/analytics/symbols")
    assert sym.status_code == 200
    assert isinstance(sym.json()["items"], list)


def test_invalid_and_empty_session(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    seed_mixed_session(db)
    client = _client(tmp_path, enabled=True)
    assert client.get("/api/v1/paper/sessions/ps_missing/analytics").status_code == 404
    assert client.get("/api/v1/paper/sessions/bad id!!/analytics").status_code == 400


def test_symbol_and_date_filters(tmp_path: Path) -> None:
    db = tmp_path / "paper.sqlite3"
    sid = seed_mixed_session(db)
    client = _client(tmp_path, enabled=True)
    r = client.get(
        f"/api/v1/paper/sessions/{sid}/analytics",
        params={"symbol": "BTCUSDT", "exit_from_ms": 0, "exit_to_ms": 9_999_999},
    )
    assert r.status_code == 200
    page = client.get(
        f"/api/v1/paper/sessions/{sid}/analytics/trades",
        params={"limit": 2, "offset": 0},
    )
    assert page.status_code == 200
    assert len(page.json()["items"]) <= 2


def test_empty_db_enabled(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=True, db_name="absent.sqlite3")
    r = client.get("/api/v1/paper/sessions/ps_x/analytics")
    assert r.status_code == 404
    assert not (tmp_path / "absent.sqlite3").exists()
