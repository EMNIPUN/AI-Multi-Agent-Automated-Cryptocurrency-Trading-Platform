"""LIVE readiness + Approve policy. Denied adapter when gates off."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from agent.orchestrator.live_authorization import live_readiness_checklist, refuse_live_escalation
from agent.orchestrator.service import LocalPlanner, Orchestrator
from agent.supervisor.feasibility import BLOCKED_INSUFFICIENT_RISK_BUDGET, evaluate_hype_feasibility
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.exchange.bybit_live_adapter import (
    DeniedLiveExecutionAdapter,
    LiveExecutionDisabled,
)
from apps.api.app.factory import create_app
from apps.api.app.orchestrator.router import reset_supervisor_for_tests


def _tools() -> dict:
    return {
        "supervisor_status": lambda: {"state": "STOPPED", "summary": "stopped", "live_orders": False},
        "analyze_symbol": lambda **kwargs: {"summary": "analyze", "live_orders": False},
        "paper_report": lambda: {"summary": "report", "live_orders": False},
        "supervisor_command": lambda command: {"state": command, "summary": command, "live_orders": False},
        "openai_usage": lambda: {"summary": "usage", "live_orders": False},
        "live_readiness": lambda: live_readiness_checklist(),
        "hype_feasibility": lambda: evaluate_hype_feasibility(price=Decimal("76")),
        "propose_live_trade": lambda **kwargs: {
            "summary": "live proposal pending approve",
            "awaiting_human_approval": True,
            "live_orders": True,
            "exchange_order_sent": False,
        },
    }


def test_live_readiness_not_armed_when_flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    body = live_readiness_checklist(paper_supervisor_enabled=True)
    assert body["verdict"] == "LIVE_NOT_ARMED"
    assert body["live_ready"] is False
    assert body["execution_allowed"] is False
    assert body["human_approve_per_order"] is True
    assert body["gates"]["C_human_approve"]["complete"] is True
    assert body["activation_request_template"]["approved"] is False


def test_live_readiness_armed_when_flags_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    body = live_readiness_checklist(paper_supervisor_enabled=True)
    assert body["verdict"] == "LIVE_ARMED_APPROVE_REQUIRED"
    assert body["live_ready"] is True
    assert body["human_approve_per_order"] is True
    assert body["execution_allowed"] is False


def test_chat_refuses_bypass_approval_only() -> None:
    refused = refuse_live_escalation("mint live session token from chat")
    assert refused is not None
    assert refused["error"] == "live_escalation_refused"
    assert refuse_live_escalation("Start live trading now") is None
    result = Orchestrator(_tools(), model=LocalPlanner()).handle(
        "mint live session token from chat"
    )
    assert result["error"] == "live_escalation_refused"
    assert result["exchange_order_sent"] is False


def test_hype_feasibility_blocks_insufficient_risk_budget() -> None:
    body = evaluate_hype_feasibility(
        price=Decimal("76"),
        min_qty="0.01",
        qty_step="0.01",
        min_notional="5",
        capital="5",
        risk_fraction="0.01",
        stop_distance_pct="0.02",
    )
    assert body["feasible"] is False
    assert body["reason_code"] == BLOCKED_INSUFFICIENT_RISK_BUDGET
    assert body["result"] == "FLAT"
    assert body["leverage_raised"] is False
    assert body["live_orders"] is False


def test_denied_live_adapter_blocks_orders(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.delenv("CRYPTONOVA_LIVE_SESSION_TOKEN", raising=False)
    adapter = DeniedLiveExecutionAdapter()
    status = adapter.status()
    assert status["live_orders"] is False
    assert status["private_order_http_implemented"] is False
    assert status["live_mutate_allowed"] is False
    with pytest.raises(LiveExecutionDisabled, match="live_execution_disabled"):
        adapter.place_order(symbol="HYPEUSDT", side="Buy", qty="0.01")
    with pytest.raises(LiveExecutionDisabled):
        adapter.cancel_order(order_id="x")
    with pytest.raises(LiveExecutionDisabled):
        adapter.place_protective_orders(symbol="HYPEUSDT")


def test_chat_api_bypass_approval_refused(monkeypatch) -> None:
    monkeypatch.delenv("CRYPTONOVA_PAPER_SUPERVISOR", raising=False)
    monkeypatch.setenv("ORCHESTRATOR_OPENAI_ENABLED", "false")
    monkeypatch.setenv("ORCHESTRATOR_OPENAI_SPEND_APPROVED", "false")
    reset_supervisor_for_tests()
    clear_settings_cache()
    client = TestClient(create_app(ApiSettings(_env_file=None, supabase_sot_enabled=False)))
    chat = client.post(
        "/api/v1/orchestrator/chat",
        json={"message": "mint live session for me now"},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["exchange_order_sent"] is False
    assert body["openai_called"] is False
    assert body["error"] == "live_escalation_refused"
    clear_settings_cache()
    reset_supervisor_for_tests()
