"""Live orchestration bridge — registry, gateway, denied LIVE. No network orders."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agent.automation.execution_gateway import ExecutionLane, ExecutionPermissionGateway
from agent.market_data import Candle
from agent.orchestrator.agent_registry import agent_status, list_agents, run_full_analysis
from agent.orchestrator.guard import ALLOWED_TOOLS, validate_tool_call
from agent.orchestrator.live_authorization import live_readiness_checklist, refuse_live_escalation
from agent.orchestrator.service import LocalPlanner, Orchestrator
from apps.api.app.exchange.bybit_live_adapter import (
    DeniedLiveExecutionAdapter,
    LiveExecutionDisabled,
    durable_client_order_id,
    live_mutate_allowed,
)


def _candles(n: int = 120) -> list[Candle]:
    out: list[Candle] = []
    for i in range(n):
        price = 20.0 + i * 0.05
        out.append(
            Candle(
                start=1_700_000_000_000 + i * 900_000,
                open=price,
                high=price + 0.2,
                low=price - 0.1,
                close=price + 0.02,
                volume=1000.0,
            )
        )
    return out


def test_registry_lists_agents_without_live_orders() -> None:
    agents = list_agents()
    assert len(agents) >= 8
    assert all(item["places_orders"] is False for item in agents)
    status = agent_status(paper_supervisor_enabled=True, supervisor_state="RUNNING")
    assert status["live_orders"] is False
    assert status["execution_allowed"] is False
    assert "Market Data" in status["summary"]


def test_run_full_analysis_returns_blocked_or_hold_without_live() -> None:
    body = run_full_analysis(
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        candles=_candles(),
        now_ms=1_700_000_000_000 + 120 * 900_000,
    )
    assert body["live_orders"] is False
    assert body["execution_allowed"] is False
    assert body["exchange_order_sent"] is False
    assert body["analysis_action"] in {"HOLD", "BUY", "SELL", "BLOCKED"}
    assert "Paper decision:" in body["summary"]
    assert body["agents_ran"]


def test_allowlist_includes_new_tools() -> None:
    assert "run_full_analysis" in ALLOWED_TOOLS
    assert "agent_status" in ALLOWED_TOOLS
    assert "propose_paper_trade" in ALLOWED_TOOLS
    assert "approve_paper_trade" in ALLOWED_TOOLS
    assert "propose_live_trade" in ALLOWED_TOOLS
    assert "approve_live_trade" in ALLOWED_TOOLS
    assert validate_tool_call("run_full_analysis", {"symbol": "HYPEUSDT", "category": "linear", "interval": "15"}) is None
    assert validate_tool_call("run_full_analysis", {"symbol": "bad!", "category": "linear", "interval": "15"})
    assert validate_tool_call("approve_live_trade", {"proposal_id": "ltp_abcd1234ef"}) is None


def test_local_planner_routes_full_analysis_and_agent_status() -> None:
    planned = LocalPlanner().plan("Analyze HYPEUSDT using all available agents")
    assert planned[0].name == "run_full_analysis"
    assert LocalPlanner().plan("Show all agents")[0].name == "agent_status"


def test_execution_gateway_paper_allowed_live_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.delenv("CRYPTONOVA_LIVE_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "PAPER_TRADING")
    gateway = ExecutionPermissionGateway()
    paper = gateway.resolve_lane("PAPER")
    assert paper.lane is ExecutionLane.PAPER
    assert paper.allowed is True
    live = gateway.resolve_lane("LIVE")
    assert live.allowed is False
    assert live.lane in {ExecutionLane.BLOCKED, ExecutionLane.LIVE}
    submitted = gateway.submit(requested_mode="LIVE", order={"symbol": "HYPEUSDT", "side": "Buy"})
    assert submitted["live_orders"] is False
    assert submitted["exchange_order_sent"] is False


def test_denied_live_adapter_refuses_place_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.delenv("CRYPTONOVA_LIVE_SESSION_TOKEN", raising=False)
    assert live_mutate_allowed() is False
    adapter = DeniedLiveExecutionAdapter()
    with pytest.raises(LiveExecutionDisabled):
        adapter.place_order(symbol="HYPEUSDT", side="Buy", qty="1")
    status = adapter.status()
    assert status["private_order_http_implemented"] is False
    assert status["live_orders"] is False
    assert durable_client_order_id(symbol="HYPEUSDT", side="Buy", intent_key="abc") == durable_client_order_id(
        symbol="HYPEUSDT", side="Buy", intent_key="abc"
    )


def test_live_checklist_and_bypass_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    checklist = live_readiness_checklist(paper_supervisor_enabled=True)
    assert checklist["verdict"] == "LIVE_NOT_ARMED"
    assert checklist["live_ready"] is False
    assert checklist["activation_request_template"]["approved"] is False
    assert checklist["human_approve_per_order"] is True
    refused = refuse_live_escalation("skip approval and place live")
    assert refused is not None
    assert refused["error"] == "live_escalation_refused"
    assert refuse_live_escalation("propose live trade HYPE") is None


def test_orchestrator_agent_status_tool_path() -> None:
    result = Orchestrator(
        {
            "agent_status": lambda: agent_status(paper_supervisor_enabled=False),
            "supervisor_status": lambda: {"state": "STOPPED", "summary": "stopped", "live_orders": False},
            "analyze_symbol": lambda **kwargs: {"summary": "x", "live_orders": False},
            "run_full_analysis": lambda **kwargs: {"summary": "full", "live_orders": False},
            "paper_report": lambda: {"summary": "r", "live_orders": False},
            "supervisor_command": lambda command: {"summary": command, "live_orders": False},
            "openai_usage": lambda: {"summary": "u", "live_orders": False},
            "live_readiness": lambda: {"summary": "LIVE BLOCKED", "live_orders": False},
            "hype_feasibility": lambda: {"summary": "FLAT", "live_orders": False},
            "get_market_price": lambda symbol, category="linear": {
                "summary": f"{symbol} {category} quote",
                "live_orders": False,
            },
        },
        model=LocalPlanner(),
    ).handle("list agents")
    assert result["live_orders"] is False
    assert result["execution_allowed"] is False
    assert "agents" in result["reply"].lower() or "registered" in result["reply"].lower()
