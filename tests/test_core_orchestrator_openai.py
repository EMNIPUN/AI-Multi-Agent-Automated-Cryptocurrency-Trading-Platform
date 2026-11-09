"""OpenAI orchestrator adapter. Mock transport only. No paid network call."""

from __future__ import annotations

from pathlib import Path

from agent.orchestrator.openai_adapter import (
    FakeResponsesTransport,
    OpenAiOrchestratorPlanner,
    OrchestratorOpenAiConfig,
    estimate_cost_usd,
)
from agent.orchestrator.service import LocalPlanner, Orchestrator, PlannedCall
from agent.orchestrator.usage_ledger import UsageLedger


def _tools() -> dict:
    return {
        "supervisor_status": lambda: {"state": "STOPPED", "summary": "Supervisor STOPPED.", "live_orders": False},
        "analyze_symbol": lambda symbol, category="linear", interval="15": {
            "analysis_action": "HOLD",
            "symbol": symbol,
            "summary": f"{symbol} HOLD",
            "live_orders": False,
        },
        "paper_report": lambda: {"summary": "Paper equity report", "live_orders": False},
        "supervisor_command": lambda command: {"state": "RUNNING", "summary": f"cmd {command}", "live_orders": False},
        "openai_usage": lambda: {"summary": "usage gated", "gates_open": False, "live_orders": False},
        "live_readiness": lambda: {"summary": "LIVE BLOCKED", "verdict": "LIVE_BLOCKED", "live_orders": False},
        "hype_feasibility": lambda: {
            "summary": "FLAT",
            "reason_code": "BLOCKED_INSUFFICIENT_RISK_BUDGET",
            "live_orders": False,
        },
        "get_market_price": lambda symbol, category="linear": {
            "summary": f"{symbol} last price quote",
            "live_orders": False,
        },
        "run_full_analysis": lambda symbol, category="linear", interval="15": {
            "summary": f"{symbol} full analysis",
            "live_orders": False,
        },
        "agent_status": lambda: {"summary": "agents registered", "live_orders": False},
    }


def test_spend_gates_closed_falls_back_to_local_planner(tmp_path: Path) -> None:
    config = OrchestratorOpenAiConfig(
        enabled=True,
        spend_approved=False,
        api_key="sk-test",
        model="gpt-test",
        ledger_path=str(tmp_path / "usage.sqlite3"),
    )
    transport = FakeResponsesTransport([PlannedCall("analyze_symbol", {"symbol": "HYPEUSDT"})])
    planner = OpenAiOrchestratorPlanner(config, transport=transport, ledger=UsageLedger(tmp_path / "usage.sqlite3"))
    planned = planner.plan("Analyze HYPEUSDT futures.")
    assert planner.last_openai_called is False
    assert planner.last_error == "openai_spend_gate_closed"
    assert planned[0].name in {"analyze_symbol", "run_full_analysis", "supervisor_status"}
    assert transport.calls == []


def test_fake_responses_parses_allowlisted_tools(tmp_path: Path) -> None:
    config = OrchestratorOpenAiConfig(
        enabled=True,
        spend_approved=True,
        api_key="sk-test",
        model="gpt-test",
        ledger_path=str(tmp_path / "usage.sqlite3"),
    )
    transport = FakeResponsesTransport(
        [
            PlannedCall("supervisor_status", {}),
            PlannedCall("place_live_order", {"leverage": "20"}),
        ]
    )
    planner = OpenAiOrchestratorPlanner(config, transport=transport, ledger=UsageLedger(tmp_path / "usage.sqlite3"))
    # Vague prompt avoids LocalPlanner.route short-circuit so FakeResponses is exercised.
    planned = planner.plan("Give me a plain-language overview of the paper session.")
    assert planner.last_openai_called is True
    assert [call.name for call in planned] == ["supervisor_status"]
    assert estimate_cost_usd(
        prompt_tokens=10,
        completion_tokens=5,
        input_usd_per_million=5.0,
        output_usd_per_million=15.0,
    ) > 0


def test_openai_planner_defers_to_local_route_for_market_workflow(tmp_path: Path) -> None:
    config = OrchestratorOpenAiConfig(
        enabled=True,
        spend_approved=True,
        api_key="sk-test",
        model="gpt-test",
        ledger_path=str(tmp_path / "usage.sqlite3"),
    )
    transport = FakeResponsesTransport([PlannedCall("agent_status", {})])
    planner = OpenAiOrchestratorPlanner(config, transport=transport, ledger=UsageLedger(tmp_path / "usage.sqlite3"))
    planned = planner.plan("what is current price of BNB")
    assert planner.last_openai_called is False
    assert planned[0].name == "get_market_price"
    assert planned[0].arguments["symbol"] == "BNBUSDT"
    assert transport.calls == []


def test_daily_budget_blocks_paid_call(tmp_path: Path) -> None:
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    ledger.record(prompt_tokens=1_000_000, completion_tokens=0, cost_usd=2.0, model="gpt-test")
    config = OrchestratorOpenAiConfig(
        enabled=True,
        spend_approved=True,
        api_key="sk-test",
        model="gpt-test",
        daily_budget_usd=1.0,
        ledger_path=str(tmp_path / "usage.sqlite3"),
    )
    transport = FakeResponsesTransport([PlannedCall("openai_usage", {})])
    planner = OpenAiOrchestratorPlanner(config, transport=transport, ledger=ledger)
    planned = planner.plan("Show OpenAI API usage.")
    assert planner.last_openai_called is False
    assert planner.last_error == "daily_budget_exceeded"
    assert isinstance(LocalPlanner().plan("usage")[0].name, str)
    assert planned[0].name == "openai_usage"


def test_orchestrator_reports_openai_called_false_when_gated() -> None:
    result = Orchestrator(_tools(), model=LocalPlanner()).handle("Show OpenAI API usage.")
    assert result["openai_called"] is False
    assert result["live_orders"] is False
    assert result["execution_allowed"] is False
    assert result["llm_changed_decision"] is False
    assert "usage" in result["reply"].lower() or "gated" in result["reply"].lower()


def test_greeting_uses_openai_assistant_prose(tmp_path: Path) -> None:
    config = OrchestratorOpenAiConfig(
        enabled=True,
        spend_approved=True,
        api_key="sk-test",
        model="gpt-test",
        ledger_path=str(tmp_path / "usage.sqlite3"),
    )
    transport = FakeResponsesTransport(
        [],
        output_text="Hi there! I'm CryptoNova's PAPER orchestrator. How can I help today?",
    )
    planner = OpenAiOrchestratorPlanner(
        config, transport=transport, ledger=UsageLedger(tmp_path / "usage.sqlite3")
    )
    result = Orchestrator(_tools(), model=planner).handle("Hiii")
    assert result["openai_called"] is True
    assert result["tool_calls"] == []
    assert "Hi there!" in result["reply"]
    assert "Agents mirroring" not in result["reply"]
    assert result["live_orders"] is False
    assert transport.calls
    assert "tools" not in transport.calls[0]
