"""LIVE futures intake: analysis → place order → checklist → proposal. No Bybit network."""

from __future__ import annotations

import pytest

from agent.orchestrator.analysis_memory import remember_analysis, reset_analysis_memory_for_tests
from agent.orchestrator.futures_intake import (
    continue_futures_intake,
    get_active_intake,
    reset_futures_intake_for_tests,
    start_futures_intake,
)
from agent.orchestrator.live_trade_proposals import (
    latest_pending_live_proposal,
    reset_live_proposals_for_tests,
)
from agent.orchestrator.service import LocalPlanner, Orchestrator


def _reset() -> None:
    reset_futures_intake_for_tests()
    reset_analysis_memory_for_tests()
    reset_live_proposals_for_tests()


@pytest.fixture(autouse=True)
def _clean_intake_state() -> None:
    _reset()
    yield
    _reset()


def test_place_order_does_not_wipe_active_intake(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    monkeypatch.setenv("BYBIT_DEMO", "false")

    first = start_futures_intake(symbol="HYPEUSDT", message="Sell Market")
    assert first["awaiting_intake"] is True
    assert get_active_intake() is not None
    assert get_active_intake().side == "SELL"
    assert get_active_intake().order_type == "Market"

    # The bug: saying Place order again used to reset the session.
    second = start_futures_intake(symbol="HYPEUSDT", message="Place order")
    assert second["awaiting_intake"] is True
    session = get_active_intake()
    assert session is not None
    assert session.side == "SELL"
    assert session.order_type == "Market"
    assert "Already set" in second["summary"] or "SELL" in second["summary"]


def test_usdt_margin_sizes_qty_from_analysis_price(monkeypatch) -> None:
    _reset()
    monkeypatch.setattr(
        "agent.orchestrator.symbol_rules.fetch_instrument_public",
        lambda *_a, **_k: None,
    )
    remember_analysis(
        {
            "symbol": "HYPEUSDT",
            "analysis_action": "SELL",
            "side": "SELL",
            "last_price": 73.0,
            "stop_loss": 74.0,
            "take_profit": 71.0,
        }
    )
    body = start_futures_intake(
        symbol="HYPEUSDT",
        message="Sell Market leverage 5 use 5 USDT skip sl skip tp",
    )
    # Finalized proposal or still intake — qty must be lot-stepped (0.01).
    session = get_active_intake()
    qty = None
    if session is not None:
        qty = session.qty
        assert session.margin_usdt == 5.0
        assert session.leverage == 5
    else:
        qty = str(body.get("qty") or "")
        assert body.get("ok") is True
    assert qty
    # 5 USDT * 5x / 73 ≈ 0.342 → floored to 0.34
    assert float(qty) == 0.34


def test_account_balance_does_not_set_trade_size() -> None:
    _reset()
    remember_analysis(
        {
            "symbol": "HYPEUSDT",
            "analysis_action": "SELL",
            "side": "SELL",
            "last_price": 73.5,
            "stop_loss": 74.2,
            "take_profit": 72.1,
        }
    )
    body = start_futures_intake(
        symbol="HYPEUSDT",
        message="Ok place the order use my bybit account 5 usdt",
    )
    session = get_active_intake()
    assert session is not None
    assert session.account_usdt == 5.0
    assert session.margin_usdt is None
    assert session.qty is None
    assert "margin_or_qty" in body["missing"]
    assert "How many USDT" in body["summary"]


def test_use_3_usdt_with_leverage_rounds_qty(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    monkeypatch.setattr(
        "apps.api.app.exchange.bybit_live_adapter.live_mutate_allowed",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent.orchestrator.symbol_rules.fetch_instrument_public",
        lambda *_a, **_k: None,
    )
    remember_analysis(
        {
            "symbol": "HYPEUSDT",
            "analysis_action": "SELL",
            "side": "SELL",
            "entry": 73.5,
            "last_price": 73.5,
            "stop_loss": 74.23571428571428,
            "take_profit": 72.11557142857141,
        }
    )
    start_futures_intake(symbol="HYPEUSDT", message="place the order account 5 usdt")
    done = continue_futures_intake("Market leverage 5 use 3 USDT")
    assert done.get("ok") is True
    assert done.get("proposal_id")
    # 3 * 5 / 73.5 ≈ 0.204 → 0.20
    assert done.get("qty") == "0.2"
    assert float(done.get("stop_loss")) == 74.235
    assert float(done.get("take_profit")) == 72.115


def test_local_planner_continues_intake_on_place_order(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    start_futures_intake(symbol="HYPEUSDT", message="Buy Market")
    planned = LocalPlanner().route("Place order", preferred_mode="LIVE")
    assert planned is not None
    assert planned[0].name == "continue_futures_intake"


def test_analysis_before_trade_even_in_live_mode() -> None:
    planned = LocalPlanner().route(
        "I want trade BTC and firstly give me full report",
        preferred_mode="LIVE",
    )
    assert planned is not None
    assert planned[0].name == "run_full_analysis"
    assert planned[0].arguments["symbol"] == "BTCUSDT"


def test_stop_loss_does_not_stop_supervisor() -> None:
    planned = LocalPlanner().route("stop loss 73.5", preferred_mode="LIVE")
    assert planned is not None
    assert planned[0].name != "supervisor_command"


def test_checklist_to_proposal(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    monkeypatch.setenv("BYBIT_DEMO", "false")

    remember_analysis(
        {
            "symbol": "HYPEUSDT",
            "analysis_action": "SELL",
            "side": "SELL",
            "last_price": 73.0,
            "stop_loss": 74.0,
            "take_profit": 71.0,
        }
    )

    def allow() -> bool:
        return True

    monkeypatch.setattr(
        "apps.api.app.exchange.bybit_live_adapter.live_mutate_allowed",
        allow,
    )

    start = start_futures_intake(symbol="HYPEUSDT", message="Place futures order HYPEUSDT")
    assert start.get("awaiting_intake") is True
    assert get_active_intake() is not None
    assert get_active_intake().side == "SELL"

    monkeypatch.setattr(
        "agent.orchestrator.symbol_rules.fetch_instrument_public",
        lambda *_a, **_k: None,
    )
    done = continue_futures_intake("Market qty 0.1 leverage 3 skip sl skip tp")
    assert done.get("ok") is True
    assert done.get("proposal_id")
    assert done.get("awaiting_human_approval") is True
    assert get_active_intake() is None
    pending = latest_pending_live_proposal()
    assert pending is not None
    assert pending.side == "SELL"
    # 0.1 already meets HYPE min notional (~5 USDT) and qtyStep 0.01.
    assert pending.qty == "0.1"
    assert "Approve live trade" in done["summary"]


def test_limit_order_seeds_analysis_entry_and_finalizes(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "false")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    monkeypatch.setattr(
        "apps.api.app.exchange.bybit_live_adapter.live_mutate_allowed",
        lambda: True,
    )
    remember_analysis(
        {
            "symbol": "HYPEUSDT",
            "analysis_action": "SELL",
            "side": "SELL",
            "entry": 73.577,
            "last_price": 73.577,
            "stop_loss": 74.27,
            "take_profit": 72.17,
        }
    )
    monkeypatch.setattr(
        "agent.orchestrator.symbol_rules.fetch_instrument_public",
        lambda *_a, **_k: None,
    )
    start_futures_intake(symbol="HYPEUSDT", message="Sell use 5 USDT")
    done = continue_futures_intake("use limit order and leverage use 5x")
    assert done.get("ok") is True
    assert done.get("proposal_id")
    assert done.get("awaiting_human_approval") is True
    assert done.get("order_type") == "Limit"
    assert float(done.get("limit_price") or 0) == 73.577
    assert "Approve live trade" in done["summary"]


def test_orchestrator_prefers_local_intake_over_openai(monkeypatch) -> None:
    _reset()
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "true")

    class NoisyModel:
        last_openai_called = True
        last_assistant_text = "Could you please clarify what you mean?"
        last_error = None

        def plan(self, message: str, preferred_mode: str = "PAPER"):
            return []

    tools = {
        "start_futures_intake": lambda symbol="HYPEUSDT", category="linear", message="": start_futures_intake(
            symbol=symbol, category=category, message=message
        ),
        "continue_futures_intake": continue_futures_intake,
    }
    orch = Orchestrator(tools, model=NoisyModel())
    first = orch.handle("Place futures order HYPEUSDT", preferred_mode="LIVE")
    assert first["tool_calls"][0]["name"] == "start_futures_intake"
    assert "clarify" not in first["reply"].lower()

    second = orch.handle("Place order", preferred_mode="LIVE")
    assert second["tool_calls"][0]["name"] == "continue_futures_intake"
    assert get_active_intake() is not None
