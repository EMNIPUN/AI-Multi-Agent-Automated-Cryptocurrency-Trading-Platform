"""Prompt 68B — backtest artifact read API (GET-only, gated, loopback)."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["SUPABASE_SOT_ENABLED"] = "false"

from agent.backtest.artifacts import persist_run_artifact
from agent.backtest.config import BacktestConfig, DataSourceKind
from agent.backtest.data import synthetic_trend_candles
from agent.backtest.runner import run_backtest
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app


def _seed_run(tmp_path: Path) -> str:
    candles = synthetic_trend_candles(n=220)
    result = run_backtest(
        BacktestConfig(
            symbol="BTCUSDT",
            market_type="spot",
            interval="15",
            initial_capital=Decimal("10000"),
            data_source=DataSourceKind.INLINE,
            min_confirmed_bars=210,
        ),
        candles=candles,
        journal_dir=tmp_path / "journals",
    )
    persist_run_artifact(result, results_dir=tmp_path / "results")
    return result.run_id


def _client(tmp_path: Path, *, enabled: bool) -> TestClient:
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        backtest_read_api_enabled=enabled,
        backtest_run_api_enabled=False,
        backtest_results_dir=str(tmp_path / "results"),
        paper_read_api_enabled=False,
        api_host="127.0.0.1",
    )
    app = create_app(settings)
    return TestClient(app)


def test_feature_gate_disabled_by_default(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=False)
    r = client.get("/api/v1/backtests/status")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["runs_backtests"] is False
    assert body["mutations"] is False

    r2 = client.get("/api/v1/backtests/runs")
    assert r2.status_code == 503
    assert r2.json()["detail"]["detail"] == "backtest_read_api_disabled"


def test_list_and_detail_happy_path(tmp_path: Path) -> None:
    run_id = _seed_run(tmp_path)
    client = _client(tmp_path, enabled=True)
    status = client.get("/api/v1/backtests/status").json()
    assert status["enabled"] is True
    assert status["run_count"] >= 1

    listed = client.get("/api/v1/backtests/runs")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(i["run_id"] == run_id for i in items)

    detail = client.get(f"/api/v1/backtests/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["run_id"] == run_id
    assert "HISTORICAL SIMULATION" in body["performance_label"]
    assert body["dataset_label"]
    assert isinstance(body["assumptions"], list) and body["assumptions"]

    metrics = client.get(f"/api/v1/backtests/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    trades = client.get(f"/api/v1/backtests/runs/{run_id}/trades?limit=10&offset=0")
    assert trades.status_code == 200
    equity = client.get(f"/api/v1/backtests/runs/{run_id}/equity")
    assert equity.status_code == 200
    assert "marked_equity" in equity.json()
    decisions = client.get(f"/api/v1/backtests/runs/{run_id}/decisions?limit=5")
    assert decisions.status_code == 200
    orders = client.get(f"/api/v1/backtests/runs/{run_id}/orders?limit=20")
    assert orders.status_code == 200
    assert "rejection_breakdown" in orders.json()


def test_invalid_run_id_and_path_traversal(tmp_path: Path) -> None:
    client = _client(tmp_path, enabled=True)
    bad = client.get("/api/v1/backtests/runs/../etc/passwd")
    assert bad.status_code in {400, 404}
    bad2 = client.get("/api/v1/backtests/runs/not_a_valid_id")
    assert bad2.status_code == 400
    missing = client.get("/api/v1/backtests/runs/bt_deadbeefdeadbeef")
    assert missing.status_code == 404


def test_corrupt_json_handled(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir(parents=True)
    (results / "bt_0123456789abcdef_report.json").write_text("{not-json", encoding="utf-8")
    client = _client(tmp_path, enabled=True)
    r = client.get("/api/v1/backtests/runs/bt_0123456789abcdef")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "corrupt_json"


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir(parents=True)
    secret = tmp_path / "secret.env"
    secret.write_text("API_KEY=should-not-leak\n", encoding="utf-8")
    link = results / "bt_0123456789abcdef_report.json"
    try:
        link.symlink_to(secret)
    except OSError:
        # Windows without symlink privilege — skip.
        return
    client = _client(tmp_path, enabled=True)
    r = client.get("/api/v1/backtests/runs/bt_0123456789abcdef")
    assert r.status_code in {400, 404, 422}


def test_get_does_not_create_results_dir(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_results"
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        backtest_read_api_enabled=True,
        backtest_results_dir=str(missing),
        api_host="127.0.0.1",
    )
    client = TestClient(create_app(settings))
    r = client.get("/api/v1/backtests/runs")
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert not missing.exists()


def test_post_requires_separate_run_gate(tmp_path: Path) -> None:
    """68B read gate alone must not execute; 68C run gate stays OFF here."""
    client = _client(tmp_path, enabled=True)
    r = client.post("/api/v1/backtests/runs", json={})
    # Run API disabled by default → 503 (route exists but gated).
    assert r.status_code == 503
    assert r.json()["detail"]["detail"] == "backtest_run_api_disabled"


def test_reconciliation_counts_consistent(tmp_path: Path) -> None:
    run_id = _seed_run(tmp_path)
    client = _client(tmp_path, enabled=True)
    detail = client.get(f"/api/v1/backtests/runs/{run_id}").json()
    orders = client.get(f"/api/v1/backtests/runs/{run_id}/orders?limit=100").json()
    counters = detail["counters"]
    # Submitted simulated orders should match submit records when all are listed.
    assert orders["total"] == counters.get("submitted_simulated_orders")
    rejected = sum(orders["rejection_breakdown"].values())
    assert rejected == counters.get("rejected_orders")
