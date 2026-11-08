"""Prompt 68C — controlled backtest run API (gated POST, lifecycle, safety)."""

from __future__ import annotations

import os
import time
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["SUPABASE_SOT_ENABLED"] = "false"

from agent.backtest.dataset_cache import save_dataset_cache
from agent.backtest.data import synthetic_trend_candles
from apps.api.app.backtests.run_service import reset_run_service_for_tests
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app


def _client(tmp_path: Path, *, run_enabled: bool, read_enabled: bool = True) -> TestClient:
    reset_run_service_for_tests()
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        backtest_read_api_enabled=read_enabled,
        backtest_run_api_enabled=run_enabled,
        backtest_results_dir=str(tmp_path / "results"),
        backtest_max_candles_per_run=5000,
        backtest_max_simultaneous_runs=1,
        backtest_max_queued_runs=2,
        backtest_max_runtime_seconds=120,
        paper_read_api_enabled=False,
        api_host="127.0.0.1",
    )
    return TestClient(create_app(settings))


def _seed_cache(tmp_path: Path) -> str:
    candles = synthetic_trend_candles(n=240)
    datasets = tmp_path / "results" / "datasets"
    saved = save_dataset_cache(
        candles,
        meta={
            "symbol": "BTCUSDT",
            "interval": "15",
            "market_type": "spot",
            "provenance": "OFFLINE HISTORICAL FIXTURE",
            "label": "OFFLINE HISTORICAL FIXTURE",
            "source_kind": "fixture_file",
        },
        datasets_dir=datasets,
    )
    return saved.content_hash


def _valid_body(dataset_hash: str, **over) -> dict:
    start = 1_700_000_000_000
    end = start + 15 * 60_000 * 239
    body = {
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "interval": "15",
        "start_ms": start,
        "end_ms": end,
        "initial_capital": "1000",
        "fee_rate": "0.001",
        "slippage_bps": "5",
        "risk_mode": "signal_only",
        "data_source": "offline_fixture",
        "dataset_hash": dataset_hash,
        "idempotency_key": "test-key-1",
    }
    body.update(over)
    return body


def test_run_api_disabled_by_default(tmp_path: Path) -> None:
    client = _client(tmp_path, run_enabled=False)
    caps = client.get("/api/v1/backtests/run-capabilities")
    assert caps.status_code == 200
    assert caps.json()["run_api_enabled"] is False

    r = client.post("/api/v1/backtests/runs", json=_valid_body("a" * 64))
    assert r.status_code == 503
    assert r.json()["detail"]["detail"] == "backtest_run_api_disabled"


def test_get_never_starts_execution(tmp_path: Path) -> None:
    client = _client(tmp_path, run_enabled=True)
    # GET list / status must not create jobs
    before = list((tmp_path / "results" / "jobs").glob("*.json")) if (tmp_path / "results" / "jobs").exists() else []
    client.get("/api/v1/backtests/runs")
    client.get("/api/v1/backtests/status")
    after_dir = tmp_path / "results" / "jobs"
    after = list(after_dir.glob("*.json")) if after_dir.exists() else []
    assert before == after


def test_post_starts_one_offline_fixture_run(tmp_path: Path) -> None:
    dataset_hash = _seed_cache(tmp_path)
    client = _client(tmp_path, run_enabled=True)
    body = _valid_body(dataset_hash)
    r = client.post("/api/v1/backtests/runs", json=body)
    assert r.status_code == 200, r.text
    accepted = r.json()
    assert accepted["status"] == "QUEUED"
    job_id = accepted["job_id"]
    assert job_id.startswith("btj_")

    # Poll until complete
    terminal = None
    for _ in range(80):
        st = client.get(f"/api/v1/backtests/jobs/{job_id}")
        assert st.status_code == 200
        terminal = st.json()
        if terminal["status"] in {"COMPLETED", "FAILED", "INTERRUPTED"}:
            break
        time.sleep(0.1)
    assert terminal is not None
    assert terminal["status"] == "COMPLETED", terminal
    assert terminal["run_id"]
    assert terminal["run_id"].startswith("bt_")

    detail = client.get(f"/api/v1/backtests/runs/{terminal['run_id']}")
    assert detail.status_code == 200
    assert "HISTORICAL SIMULATION" in detail.json()["performance_label"]


def test_idempotent_duplicate_submission(tmp_path: Path) -> None:
    dataset_hash = _seed_cache(tmp_path)
    client = _client(tmp_path, run_enabled=True)
    body = _valid_body(dataset_hash, idempotency_key="same-key")
    r1 = client.post("/api/v1/backtests/runs", json=body)
    r2 = client.post("/api/v1/backtests/runs", json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["job_id"] == r2.json()["job_id"]
    assert r2.json()["idempotent_replay"] is True


def test_forbidden_fields_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path, run_enabled=True)
    r = client.post(
        "/api/v1/backtests/runs",
        json={
            "symbol": "BTCUSDT",
            "market_type": "spot",
            "interval": "15",
            "start_ms": 1_700_000_000_000,
            "end_ms": 1_700_100_000_000,
            "dataset_path": "/etc/passwd",
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "forbidden_fields"


def test_invalid_request_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path, run_enabled=True)
    r = client.post(
        "/api/v1/backtests/runs",
        json={
            "symbol": "DOGEUSDT",
            "market_type": "spot",
            "interval": "15",
            "start_ms": 1_700_000_000_000,
            "end_ms": 1_700_100_000_000,
            "data_source": "bybit_public",
        },
    )
    assert r.status_code in {400, 422}


def test_status_reports_run_api_flag(tmp_path: Path) -> None:
    client = _client(tmp_path, run_enabled=True, read_enabled=True)
    st = client.get("/api/v1/backtests/status").json()
    assert st["run_api_enabled"] is True
    assert st["runs_backtests"] is False
    assert st["mutations"] is False


def test_content_type_required(tmp_path: Path) -> None:
    client = _client(tmp_path, run_enabled=True)
    r = client.post(
        "/api/v1/backtests/runs",
        content=b"{}",
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 415
