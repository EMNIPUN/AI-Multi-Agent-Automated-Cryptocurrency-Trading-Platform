"""Offline regression scenarios for autonomous position management."""

from dataclasses import replace
from decimal import Decimal

import pytest

from agent.multi_agent.types import DecisionAction, RiskVerdict
from agent.supervisor.machine import PaperSupervisor
from agent.supervisor.worker import PaperSupervisorWorker
from tests.test_core_supervisor import _candle, _config, _decision, _scripted, _supervisor


def cycle(supervisor, start, close=101, *, history=None):
    return supervisor.run_cycle(
        history or [_candle(start, close)], symbol="BTCUSDT", category="spot", interval="15", now_ms=start,
    )


def open_long(tmp_path):
    supervisor = _supervisor(tmp_path, _scripted(
        (DecisionAction.BUY, RiskVerdict.APPROVED), (DecisionAction.HOLD, RiskVerdict.APPROVED),
    ))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 1000)
    assert cycle(supervisor, 2000)["open_positions"] == 1
    return supervisor


@pytest.mark.parametrize("command", ["pause", "halt", "stop"])
def test_blocking_entries_withdraws_already_pending_buy(tmp_path, command):
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.BUY, RiskVerdict.APPROVED)))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 1000)
    assert len(supervisor.report()["pending_orders"]) == 1
    supervisor.command(command, now_ms=1100)
    cycle(supervisor, 2000)
    report = supervisor.report()
    assert report["positions"] == []
    assert report["pending_orders"] == []
    assert any(event["event_type"] == "ENTRY_WITHDRAWN" for event in report["recent_events"])


@pytest.mark.parametrize("command", ["pause", "halt"])
def test_protective_stop_closes_while_entries_are_blocked(tmp_path, command):
    supervisor = open_long(tmp_path)
    supervisor.command(command, now_ms=2100)
    stopped = cycle(supervisor, 3000, close=94)
    assert stopped["open_positions"] == 0
    assert "CLOSED_STOP_LOSS" in stopped["fill_reasons"]
    report = supervisor.report()
    assert report["closed_trades"] == 1
    assert report["recent_trades"][0]["exit_reason"] == "STOP_LOSS"
    assert report["protective_monitoring"] is True


def test_stop_drains_position_at_next_eligible_candle(tmp_path):
    supervisor = open_long(tmp_path)
    stopping = supervisor.command("stop", now_ms=2100)
    assert stopping["state"] == "STOPPING"
    assert supervisor.report()["pending_orders"][0]["side"] == "SELL"
    stopped = cycle(supervisor, 3000, close=103)
    assert stopped["state"] == "STOPPED"
    assert stopped["open_positions"] == 0
    assert supervisor.report()["recent_trades"][0]["exit_reason"] == "SIGNAL_SELL"


def test_expiry_keeps_monitoring_until_positions_close(tmp_path):
    supervisor = _supervisor(tmp_path, _scripted(
        (DecisionAction.BUY, RiskVerdict.APPROVED), (DecisionAction.HOLD, RiskVerdict.APPROVED),
    ))
    supervisor.command("start", now_ms=1000, authorization={"expires_at_ms": 2500, "symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 1000)
    cycle(supervisor, 2000)
    expiring = cycle(supervisor, 3000)
    assert expiring["state"] == "STOPPING"
    assert expiring["open_positions"] == 1
    assert expiring["block_new_exposure"] is True
    assert cycle(supervisor, 4000)["state"] == "STOPPED"


def test_missed_candles_replay_stop_before_rebound(tmp_path):
    supervisor = open_long(tmp_path)
    supervisor.command("pause", now_ms=2100)
    result = cycle(supervisor, 4000, history=[_candle(2000), _candle(3000, 94), _candle(4000, 105)])
    assert result["open_positions"] == 0
    trade = supervisor.report()["recent_trades"][0]
    assert trade["closed_ms"] == 3000
    assert trade["exit_reason"] == "STOP_LOSS"


def test_worker_recovers_transient_data_failure_and_protects_paused_position(tmp_path, monkeypatch):
    supervisor = open_long(tmp_path)
    supervisor.command("pause", now_ms=2100)
    results = iter([RuntimeError("unavailable"), [_candle(3000, 94)]])
    def fetch(**kwargs):
        value = next(results)
        if isinstance(value, Exception):
            raise value
        return value
    # Fixture sessions intentionally use a different market than production defaults.
    original = supervisor._load()
    original["authorization"].update(symbol="BTCUSDT", category="spot")
    supervisor._save(original)
    monkeypatch.setattr("agent.supervisor.worker.time.time", lambda: 3)
    worker = PaperSupervisorWorker(supervisor, fetch_candles=fetch)
    assert worker.tick_once()["state"] == "ERROR"
    recovered = worker.tick_once()
    assert recovered["state"] == "PAUSED"
    assert recovered["open_positions"] == 0
    assert recovered["exchange_order_sent"] is False


def test_risk_sizing_uses_authorized_budget_and_includes_costs(tmp_path):
    def evaluate(**kwargs):
        decision = _decision(DecisionAction.BUY, RiskVerdict.APPROVED, decision_id="large", ts=1000)
        return replace(decision, risk=replace(decision.risk, position_notional=100000))
    supervisor = _supervisor(tmp_path, evaluate)
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 1000)
    order = supervisor._trader_open().store.list_pending_orders(supervisor.status()["session_id"])[0]
    # 1% of 1000 / (5% stop + 0.3% round-trip modeled costs).
    assert order.quantity * Decimal("100") <= Decimal("10") / Decimal("0.053") + Decimal("0.000001")


def test_daily_loss_halts_new_entries(tmp_path):
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 1000)
    trader = supervisor._trader_open()
    with trader.store.transaction() as connection:
        trader.store.update_session_balances(
            connection, session_id=trader.session.session_id, available=Decimal("960"),
            reserved=Decimal("0"), realized=Decimal("-40"), fees_paid=Decimal("0"), updated_ms=2000,
        )
    assert cycle(supervisor, 2000)["state"] == "HALTED"
    assert supervisor.status()["last_error"] == "DAILY_LOSS_LIMIT"


def test_repeated_start_preserves_authorization_and_latest_candle(tmp_path):
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)))
    first = supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 1000)
    repeated = supervisor.command("start", now_ms=1500, authorization={"capital_usdt": "5"})
    assert repeated["error"] == "session_already_active"
    assert repeated["authorization"] == first["authorization"]
    assert repeated["last_candle_start"] == 1000


def test_restart_replays_once_and_rejects_second_active_worker(tmp_path):
    first = open_long(tmp_path)
    second = PaperSupervisor(first.journal_path, _config(), worker_token="worker-b")
    with pytest.raises(RuntimeError, match="supervisor_worker_busy"):
        cycle(second, 2500)
    first.command("pause", now_ms=2600)
    cycle(second, 40000, close=94)
    assert second.report()["closed_trades"] == 1
    assert cycle(second, 40000)["reason"] == "duplicate_candle"


def test_out_of_order_does_not_submit_a_decision(tmp_path):
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    cycle(supervisor, 2000)
    assert cycle(supervisor, 1000)["reason"] == "out_of_order_candle"


def test_report_includes_marked_equity_and_decision_audit(tmp_path):
    supervisor = open_long(tmp_path)
    report = supervisor.report()
    assert report["positions"][0]["mark_price"] is not None
    assert Decimal(report["equity"]) == Decimal(report["available_balance"]) + Decimal(report["reserved_capital"]) + Decimal(report["unrealized_pnl"])
    assert report["latest_decision"]["action"] == "HOLD"
    assert report["recent_events"]


def test_missing_session_marker_fails_closed_without_new_session(tmp_path):
    first = open_long(tmp_path)
    first.journal_path.with_suffix(".sqlite3.session").unlink()
    second = PaperSupervisor(first.journal_path, _config(), worker_token="worker-a")
    assert cycle(second, 3000)["last_error"] == "unknown_position_state"
    assert not first.journal_path.with_suffix(".sqlite3.session").exists()


def test_report_before_start_does_not_create_journal(tmp_path):
    supervisor = _supervisor(tmp_path, _scripted())
    assert supervisor.report()["available"] is False
    assert not supervisor.journal_path.exists()
