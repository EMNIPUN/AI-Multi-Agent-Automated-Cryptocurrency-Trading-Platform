"""Phase 6A — mocked Testnet automation foundation (no live orders)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.automation.execution_risk import (
    ExecutionCandidate,
    ExecutionRiskLimits,
    ExecutionRiskState,
    ExecutionRiskVerdict,
    evaluate_execution_risk,
    trigger_emergency_halt,
)
from agent.automation.exec_store import AutomationExecStore
from agent.automation.modes import TradingMode, get_automation_gates
from agent.automation.pipeline import AutomatedExecutionPipeline, SignalExecutionRequest
from agent.automation.protective import apply_and_verify_protection, emergency_risk_procedure
from agent.automation.testnet_adapter import MockBybitTestnetAdapter
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app


def _req(**kwargs) -> SignalExecutionRequest:
    base = dict(
        decision_id="dec_test_1",
        symbol="BTCUSDT",
        category="spot",
        side="Buy",
        entry_price=50_000.0,
        stop_loss=49_000.0,
        take_profit=52_000.0,
        strategy_version="4B.1.0",
        data_age_ms=1_000,
        spread_bps=5.0,
        intended_notional=100.0,
    )
    base.update(kwargs)
    return SignalExecutionRequest(**base)


def test_default_mode_signals_only(monkeypatch) -> None:
    monkeypatch.delenv("CRYPTONOVA_TRADING_MODE", raising=False)
    monkeypatch.delenv("TESTNET_ORDER_SUBMISSION_APPROVED", raising=False)
    g = get_automation_gates()
    assert g.mode is TradingMode.SIGNALS_ONLY
    assert g.order_submission_allowed is False
    assert g.mainnet_execution_path_exists is False


def test_signals_only_pipeline_skips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "SIGNALS_ONLY")
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "e.sqlite3"),
        adapter=MockBybitTestnetAdapter(),
    )
    r = pipe.process(_req())
    assert r.submitted is False
    assert r.state == "SIGNALS_ONLY"
    assert r.execution_allowed is False


def test_duplicate_order_prevention(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "PAPER_TRADING")
    store = AutomationExecStore(tmp_path / "dup.sqlite3")
    pipe = AutomatedExecutionPipeline(store=store, adapter=MockBybitTestnetAdapter())
    a = pipe.process(_req())
    b = pipe.process(_req())
    assert a.state == "PAPER_SIMULATED"
    assert b.risk["reason_codes"] == ["DUPLICATE_INTENT"]


def test_daily_loss_halt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "PAPER_TRADING")
    state = ExecutionRiskState(realized_day_pnl=-500.0)
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "halt.sqlite3"),
        adapter=MockBybitTestnetAdapter(),
        risk_state=state,
        limits=ExecutionRiskLimits(max_daily_loss_fraction=0.02),
    )
    # equity 10k → 5% loss > 2%
    r = pipe.process(_req(decision_id="dec_halt"))
    assert r.state == "RISK_BLOCKED"
    assert "DAILY_LOSS_HALT" in r.risk["reason_codes"]


def test_insufficient_balance_and_min_qty(monkeypatch) -> None:
    cand = ExecutionCandidate(
        symbol="BTCUSDT",
        category="spot",
        side="Buy",
        entry_price=50_000,
        stop_loss=49_000,
        take_profit=52_000,
        equity=10_000,
        available_balance=10.0,
        spread_bps=1,
        data_age_ms=1,
        client_order_id="x",
        intended_notional=100,
        now_ms=1,
    )
    a = evaluate_execution_risk(cand, ExecutionRiskState())
    assert a.verdict is ExecutionRiskVerdict.VETO
    assert "INSUFFICIENT_BALANCE" in a.reason_codes


def test_stale_market_and_spread(monkeypatch) -> None:
    cand = ExecutionCandidate(
        symbol="BTCUSDT",
        category="spot",
        side="Buy",
        entry_price=50_000,
        stop_loss=49_000,
        take_profit=52_000,
        equity=10_000,
        available_balance=1_000,
        spread_bps=50,
        data_age_ms=999_999,
        client_order_id="y",
        intended_notional=100,
        now_ms=1,
    )
    a = evaluate_execution_risk(cand, ExecutionRiskState())
    assert "STALE_MARKET_DATA" in a.reason_codes
    assert "SPREAD_TOO_WIDE" in a.reason_codes


def test_stop_loss_required() -> None:
    cand = ExecutionCandidate(
        symbol="BTCUSDT",
        category="spot",
        side="Buy",
        entry_price=50_000,
        stop_loss=None,
        take_profit=52_000,
        equity=10_000,
        available_balance=1_000,
        spread_bps=1,
        data_age_ms=1,
        client_order_id="z",
        intended_notional=100,
        now_ms=1,
    )
    a = evaluate_execution_risk(cand, ExecutionRiskState())
    assert "STOP_LOSS_REQUIRED" in a.reason_codes


def test_spot_futures_isolation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "PAPER_TRADING")
    monkeypatch.setenv("PERPETUAL_AUTO_EXECUTION_ENABLED", "false")
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "lin.sqlite3"),
        adapter=MockBybitTestnetAdapter(),
    )
    r = pipe.process(_req(category="linear", decision_id="dec_lin"))
    assert r.state == "LINEAR_DISABLED"


def test_mainnet_endpoint_rejection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "MAINNET_TRADING")
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "mn.sqlite3"),
        adapter=MockBybitTestnetAdapter(),
    )
    r = pipe.process(_req(decision_id="dec_mn"))
    assert r.state == "MAINNET_LOCKED"
    assert r.submitted is False


def test_ambiguous_timeout_reconcile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    adapter = MockBybitTestnetAdapter()
    adapter.ambiguous_next_place = True
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "to.sqlite3"),
        adapter=adapter,
    )
    r = pipe.process(_req(decision_id="dec_to"))
    assert r.state == "RECONCILIATION_REQUIRED"
    assert r.submitted is False


def test_gate_blocks_submission_even_in_testnet_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "false")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "gate.sqlite3"),
        adapter=MockBybitTestnetAdapter(),
    )
    r = pipe.process(_req(decision_id="dec_gate"))
    assert r.state == "BLOCKED_BY_GATE"
    assert r.submitted is False


def test_partial_fill_protection_reject_halts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    adapter = MockBybitTestnetAdapter()
    adapter.reject_next_stop = True
    risk = ExecutionRiskState()
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "prot.sqlite3"),
        adapter=adapter,
        risk_state=risk,
        simulate_fills=True,
    )
    r = pipe.process(_req(decision_id="dec_prot"))
    assert r.filled is True
    assert r.protection_state == "REJECTED"
    assert risk.emergency_halt is True
    assert r.emergency is not None


def test_protection_verified_on_mock_fill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    adapter = MockBybitTestnetAdapter()
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(tmp_path / "ok.sqlite3"),
        adapter=adapter,
        simulate_fills=True,
    )
    r = pipe.process(_req(decision_id="dec_ok"))
    assert r.submitted is True
    assert r.filled is True
    assert r.protection_state == "VERIFIED"
    # Duplicate client id prevented on second call
    r2 = pipe.process(_req(decision_id="dec_ok"))
    assert "DUPLICATE_INTENT" in r2.risk["reason_codes"]


def test_restart_recovery_intent_survives(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "PAPER_TRADING")
    db = tmp_path / "rec.sqlite3"
    pipe = AutomatedExecutionPipeline(
        store=AutomationExecStore(db), adapter=MockBybitTestnetAdapter()
    )
    r = pipe.process(_req(decision_id="dec_rec"))
    pipe2 = AutomatedExecutionPipeline(
        store=AutomationExecStore(db), adapter=MockBybitTestnetAdapter()
    )
    r2 = pipe2.process(_req(decision_id="dec_rec"))
    assert r.intent_id is not None
    assert r2.risk["reason_codes"] == ["DUPLICATE_INTENT"]


def test_api_status_no_secrets_no_orders(monkeypatch) -> None:
    os.environ["AGENT_ALLOW_LIVE"] = "false"
    os.environ["CRYPTONOVA_TRADING_MODE"] = "SIGNALS_ONLY"
    clear_settings_cache()
    app = create_app(ApiSettings())
    client = TestClient(app)
    res = client.get("/api/v1/automation/status")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "SIGNALS_ONLY"
    assert body["order_submission_allowed"] is False
    assert body["mainnet_execution_path_exists"] is False
    assert body["execution_allowed"] is False
    blob = str(body).lower()
    assert "api_secret" not in blob
    assert "password" not in blob

    arm = client.post("/api/v1/automation/arm-testnet")
    assert arm.status_code == 403


def test_agent_allow_live_not_a_shortcut(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "SIGNALS_ONLY")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "false")
    g = get_automation_gates()
    assert g.order_submission_allowed is False


def test_emergency_procedure_never_assumes_cancel() -> None:
    proc = emergency_risk_procedure("unit")
    assert proc["assume_nothing_cancelled"] == "true"
    assert proc["require_exchange_confirmation"] == "true"


def test_supabase_outage_does_not_bypass_local_safety(tmp_path: Path, monkeypatch) -> None:
    # Local intent durability works without Supabase.
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "PAPER_TRADING")
    store = AutomationExecStore(tmp_path / "sb.sqlite3")
    pipe = AutomatedExecutionPipeline(store=store, adapter=MockBybitTestnetAdapter())
    r = pipe.process(_req(decision_id="dec_sb"))
    assert r.state == "PAPER_SIMULATED"
    assert store.get_by_client_order_id(r.client_order_id or "") is not None
