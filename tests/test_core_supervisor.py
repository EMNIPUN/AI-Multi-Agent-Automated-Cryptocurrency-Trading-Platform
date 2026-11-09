"""Paper supervisor safety. No exchange order is sent."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from agent.market_data import Candle
from agent.multi_agent.types import (
    CoordinatorDecision,
    DecisionAction,
    HypotheticalLevels,
    MarketCategoryKind,
    MarketSnapshot,
    RiskAssessment,
    RiskVerdict,
)
from agent.paper.config import PaperBrokerConfig
from agent.supervisor.machine import PaperSupervisor
from agent.supervisor.reports import journal_report


def _config() -> PaperBrokerConfig:
    return PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000"))


def _decision(action: DecisionAction, verdict: RiskVerdict, *, decision_id: str, ts: int) -> CoordinatorDecision:
    bar = Candle(start=ts, open=100.0, high=102.0, low=99.0, close=101.0, volume=10.0)
    market = MarketSnapshot(
        symbol="BTCUSDT",
        category=MarketCategoryKind.SPOT,
        interval="15",
        candles=(bar,),
        closes=(101.0,),
        volumes=(10.0,),
        newest_close_ms=ts,
        as_of_ms=ts,
        data_fresh=True,
        data_path="fixture",
    )
    return CoordinatorDecision(
        action=action,
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        timestamp_ms=ts,
        strategy_version="test",
        correlation_id="c1",
        decision_id=decision_id,
        signal_strength=0.8,
        signal_strength_note="test",
        contributions=(),
        risk=RiskAssessment(
            verdict=verdict,
            reason_codes=("ok",),
            explanation="test",
            paper_balance=1000.0,
            risk_fraction=0.01,
            position_notional=100.0,
            stop_distance_pct=0.05,
            reward_distance_pct=0.10,
            risk_reward=2.0,
        ),
        reason_codes=("test",),
        explanation="test",
        levels=HypotheticalLevels(entry=100.0, stop_loss=95.0, take_profit=110.0),
        market=market,
        idempotent_key=decision_id,
    )


def _scripted(*steps: tuple[DecisionAction, RiskVerdict]):
    queue = list(steps)

    def evaluate(**kwargs):
        action, verdict = queue.pop(0)
        ts = int(kwargs["now_ms"])
        return _decision(action, verdict, decision_id=f"{action.value}-{ts}", ts=ts)

    return evaluate


def _candle(start: int, close: float = 101.0) -> Candle:
    return Candle(
        start=start,
        open=close,
        high=max(close + 1.0, close),
        low=min(close - 1.0, close),
        close=close,
        volume=10.0,
    )


def _supervisor(tmp_path: Path, evaluate) -> PaperSupervisor:
    return PaperSupervisor(tmp_path / "supervisor.sqlite3", _config(), evaluate=evaluate, worker_token="worker-a")


def test_postgres_journal_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="supervisor_postgres_runtime_not_enabled"):
        PaperSupervisor("postgresql://localhost/cryptonova")


def test_buy_opens_on_next_candle_and_sell_closes(tmp_path: Path) -> None:
    supervisor = _supervisor(
        tmp_path,
        _scripted(
            (DecisionAction.BUY, RiskVerdict.APPROVED),
            (DecisionAction.HOLD, RiskVerdict.APPROVED),
            (DecisionAction.SELL, RiskVerdict.APPROVED),
            (DecisionAction.HOLD, RiskVerdict.APPROVED),
        ),
    )
    started = supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    assert started["state"] == "RUNNING"
    assert started["live_orders"] is False
    first = supervisor.run_cycle([_candle(1000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1000)
    assert first["open_positions"] == 0
    opened = supervisor.run_cycle([_candle(2000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=2000)
    assert opened["open_positions"] == 1
    supervisor.run_cycle([_candle(3000, 103)], symbol="BTCUSDT", category="spot", interval="15", now_ms=3000)
    closed = supervisor.run_cycle([_candle(4000, 104)], symbol="BTCUSDT", category="spot", interval="15", now_ms=4000)
    assert closed["open_positions"] == 0
    assert closed["exchange_order_sent"] is False


def test_veto_and_duplicate_candle_do_not_open(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.BUY, RiskVerdict.VETO)))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    veto = supervisor.run_cycle([_candle(1000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1000)
    again = supervisor.run_cycle([_candle(1000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1000)
    assert veto["open_positions"] == 0
    assert again["reason"] == "duplicate_candle"


def test_halt_blocks_a_new_entry(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.BUY, RiskVerdict.APPROVED)))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    supervisor.command("halt", now_ms=1100)
    halted = supervisor.run_cycle([_candle(1000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1200)
    assert halted["reason"] == "HALTED_BLOCKED_ENTRY"
    assert halted["open_positions"] == 0
    assert supervisor.status()["block_new_exposure"] is True


def test_missing_market_data_stops_new_exposure(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _scripted())
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    result = supervisor.run_cycle([], symbol="BTCUSDT", category="spot", interval="15", now_ms=1000)
    assert result["state"] == "ERROR"
    assert result["block_new_exposure"] is True
    assert result["live_orders"] is False


def test_restart_keeps_the_same_session(tmp_path: Path) -> None:
    path = tmp_path / "supervisor.sqlite3"
    first = PaperSupervisor(path, _config(), evaluate=_scripted(), worker_token="worker-a")
    started = first.command("start", now_ms=1000)
    second = PaperSupervisor(path, _config(), evaluate=_scripted(), worker_token="worker-a")
    assert second.status()["session_id"] == started["session_id"]
    assert second.status()["state"] == "RUNNING"


def test_second_worker_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "supervisor.sqlite3"
    first = PaperSupervisor(path, _config(), worker_token="worker-a")
    first.command("start", now_ms=1000)
    second = PaperSupervisor(path, _config(), worker_token="worker-b")
    with pytest.raises(RuntimeError, match="supervisor_worker_busy"):
        second.command("start", now_ms=1001)


def test_journal_write_failure_blocks_exposure(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)))
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})

    def fail(*_args, **_kwargs):
        raise RuntimeError("disk")

    supervisor._trader_open().apply_decision = fail  # type: ignore[method-assign]
    result = supervisor.run_cycle([_candle(1000)], symbol="BTCUSDT", category="spot", interval="15", now_ms=1000)
    assert result["state"] == "ERROR"
    assert result["reason"] == "journal_write_failed"


def test_report_uses_paper_equity_only(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _scripted())
    supervisor.command("start", now_ms=1000, authorization={"symbol": "BTCUSDT", "category": "spot"})
    report = journal_report(supervisor._trader_open())
    assert report["equity_source"] == "paper_journal"
    assert report["exchange_equity_included"] is False
    assert report["live_orders"] is False
    assert Decimal(report["equity"]) == Decimal("1000")


def test_start_authorizes_autonomous_paper_session(tmp_path: Path) -> None:
    supervisor = PaperSupervisor(
        tmp_path / "supervisor.sqlite3",
        evaluate=_scripted(),
        worker_token="worker-a",
    )
    started = supervisor.command("start", now_ms=1_000)
    assert started["state"] == "RUNNING"
    assert started["autonomous"] is True
    assert started["per_trade_approval"] is False
    assert started["live_orders"] is False
    auth = started["authorization"]
    assert auth["symbol"] == "HYPEUSDT"
    assert auth["mode"] == "PAPER"
    assert auth["capital_usdt"] == "5"
    assert auth["per_trade_approval"] is False


def test_session_expiry_stops_new_cycles(tmp_path: Path) -> None:
    supervisor = _supervisor(tmp_path, _scripted((DecisionAction.BUY, RiskVerdict.APPROVED)))
    supervisor.command(
        "start",
        now_ms=1_000,
        authorization={"duration_hours": 1, "started_at_ms": 1_000, "expires_at_ms": 2_000},
    )
    expired = supervisor.run_cycle(
        [_candle(3_000)],
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        now_ms=3_000,
    )
    assert expired["reason"] == "session_expired"
    assert expired["state"] == "STOPPED"
    assert expired["block_new_exposure"] is True


def test_worker_ticks_while_running_without_exchange_orders(tmp_path: Path) -> None:
    from agent.supervisor.worker import PaperSupervisorWorker

    supervisor = _supervisor(
        tmp_path,
        _scripted((DecisionAction.HOLD, RiskVerdict.APPROVED)),
    )
    supervisor.command("start", now_ms=1_000)

    def fetch_candles(**_kwargs):
        return [_candle(1_000)]

    worker = PaperSupervisorWorker(supervisor, fetch_candles=fetch_candles, poll_seconds=5)
    result = worker.tick_once()
    assert result["live_orders"] is False
    assert result["exchange_order_sent"] is False
    assert result.get("analysis_action") in {"HOLD", "BUY", "SELL", "BLOCKED", None} or result.get("skipped")


def test_infeasible_budget_stays_flat(tmp_path: Path) -> None:
    supervisor = PaperSupervisor(
        tmp_path / "supervisor.sqlite3",
        evaluate=_scripted((DecisionAction.BUY, RiskVerdict.APPROVED)),
        worker_token="worker-a",
    )
    supervisor.command(
        "start",
        now_ms=1_000,
        authorization={"capital_usdt": "5", "risk_fraction": "0.01"},
    )
    # Price high enough that 1% of 5 USDT cannot buy the 5 USDT minimum notional safely.
    result = supervisor.run_cycle(
        [_candle(1_000, close=76.0)],
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        now_ms=1_000,
    )
    assert result["analysis_action"] == "HOLD"
    assert result["reason"] == "FLAT_BUDGET"
    assert result["open_positions"] == 0
    assert result["live_orders"] is False
