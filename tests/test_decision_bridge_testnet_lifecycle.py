"""Decision bridge + gated TESTNET lifecycle (mock adapter)."""

from __future__ import annotations

import os
from unittest import mock

from agent.automation.decision_bridge import decision_to_execution_request, route_decision
from agent.automation.execution_gateway import ExecutionLane, ExecutionPermissionGateway
from agent.automation.pipeline import AutomatedExecutionPipeline
from agent.automation.reconcile import emergency_halt_policy, reconcile_intent
from agent.automation.testnet_adapter import MockBybitTestnetAdapter
from agent.multi_agent.config import STRATEGY_VERSION
from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.types import DecisionAction


def _decision_public() -> dict:
    candles = make_series(bullish_trend_closes(220))
    d = SignalPipeline().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
        data_path="public_fixture",
    )
    public = d.to_public_dict()
    # Force actionable levels for bridge mapping tests when market is HOLD.
    if public["action"] not in {"BUY", "SELL"}:
        public = {
            **public,
            "action": "BUY",
            "levels": {
                "entry": float(public["market"]["last_price"]),
                "stop_loss": float(public["market"]["last_price"]) * 0.99,
                "take_profit": float(public["market"]["last_price"]) * 1.02,
                "note": "test",
            },
        }
    return public


def test_decision_to_execution_request_maps_levels() -> None:
    public = _decision_public()
    req = decision_to_execution_request(public, intended_notional=50.0)
    assert req is not None
    assert req.symbol == "BTCUSDT"
    assert req.side in {"Buy", "Sell"}
    assert req.entry_price > 0
    assert req.strategy_version == public.get("strategy_version") or STRATEGY_VERSION


def test_decision_to_execution_request_hold_returns_none() -> None:
    assert decision_to_execution_request({"action": "HOLD", "levels": {}}) is None


def test_gateway_testnet_armed_allows_lane(monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.setenv("PERPETUAL_AUTO_EXECUTION_ENABLED", "true")
    gate = ExecutionPermissionGateway().resolve_lane("TESTNET_TRADING")
    assert gate.lane is ExecutionLane.TESTNET
    assert gate.allowed is True
    assert gate.live_orders is False


def test_route_decision_testnet_mock_pipeline(monkeypatch) -> None:
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("BYBIT_DEMO", "false")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    monkeypatch.setenv("PERPETUAL_AUTO_EXECUTION_ENABLED", "true")
    public = _decision_public()
    adapter = MockBybitTestnetAdapter()
    # Ensure linear instrument exists for BTC
    pipeline = AutomatedExecutionPipeline(adapter=adapter, simulate_fills=True)
    result = route_decision(
        public,
        requested_mode="TESTNET_TRADING",
        testnet_pipeline=pipeline,
        intended_notional=100.0,
    )
    assert result.lane == "TESTNET"
    assert result.to_dict()["live_orders"] is False
    assert result.testnet is not None


def test_reconcile_unknown_ack_no_blind_resubmit(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    from agent.automation.exec_store import AutomationExecStore, ExecutionIntentRow

    store = AutomationExecStore(tmp_path / "exec.sqlite3")
    adapter = MockBybitTestnetAdapter()
    row = ExecutionIntentRow(
        intent_id="ei_test",
        client_order_id="link_missing",
        decision_id="dec",
        symbol="BTCUSDT",
        category="linear",
        side="Buy",
        qty="0.01",
        state="SUBMITTING",
        exchange_order_id=None,
        stop_loss="90",
        take_profit="110",
        protection_state="PENDING",
        payload={},
    )
    store.insert_intent(row, now_ms=1)
    out = reconcile_intent(store=store, adapter=adapter, intent_id="ei_test")
    assert out.state == "UNKNOWN_ACK"
    assert "no_blind_resubmit" in out.detail
    assert adapter.place_calls == 0


def test_emergency_halt_policy() -> None:
    policy = emergency_halt_policy()
    assert policy["block_new_entries"] is True
    assert policy["allow_protective_exits"] is True
    assert policy["live_orders"] is False


def test_mock_lifecycle_place_fill_protect(monkeypatch) -> None:
    monkeypatch.setenv("TESTNET_ORDER_SUBMISSION_APPROVED", "true")
    monkeypatch.setenv("CRYPTONOVA_TRADING_MODE", "TESTNET_TRADING")
    monkeypatch.setenv("TESTNET_TRADING_ENABLED", "true")
    monkeypatch.setenv("TESTNET_TRADING_OPERATOR_APPROVED", "true")
    monkeypatch.setenv("BYBIT_TESTNET", "true")
    monkeypatch.setenv("MAINNET_TRADING_ENABLED", "false")
    adapter = MockBybitTestnetAdapter()
    ack = adapter.place_order(
        category="linear",
        symbol="BTCUSDT",
        side="Buy",
        qty="0.01",
        orderLinkId="lifecycle_1",
    )
    assert ack.exchange_order_id
    fill = adapter.simulate_full_fill(client_order_id="lifecycle_1", price=100.0)
    assert fill.qty == 0.01
    stop = adapter.set_trading_stop(
        __import__("agent.automation.testnet_adapter", fromlist=["ProtectiveOrderSpec"]).ProtectiveOrderSpec(
            symbol="BTCUSDT",
            category="linear",
            stop_loss="95",
            take_profit="110",
        )
    )
    assert stop["retCode"] == 0
    pos = adapter.get_position(category="linear", symbol="BTCUSDT")
    assert pos.stop_loss == "95"
    cancel = adapter.cancel_order(orderLinkId="lifecycle_1", category="linear", symbol="BTCUSDT")
    assert cancel.status == "Cancelled"
