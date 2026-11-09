"""Automatic paper buy/sell after analysis. No exchange orders."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

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
from agent.paper.auto_trade import AutomaticPaperTrader
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import PaperCandle


def _candle(start: int, close: str = "101") -> PaperCandle:
    price = Decimal(close)
    return PaperCandle(
        start_ms=start,
        open=Decimal("100"),
        high=max(Decimal("102"), price),
        low=min(Decimal("99"), price),
        close=price,
        volume=Decimal("10"),
        symbol="BTCUSDT",
        interval="15",
    )


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


def _trader(tmp_path: Path) -> AutomaticPaperTrader:
    return AutomaticPaperTrader(
        tmp_path / "auto_paper.sqlite3",
        PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000")),
    )


def test_buy_opens_position_and_sell_closes_it(tmp_path: Path) -> None:
    trader = _trader(tmp_path)
    first = trader.apply_decision(
        _decision(DecisionAction.BUY, RiskVerdict.APPROVED, decision_id="buy-1", ts=1000),
        _candle(1000),
    )
    assert first["live_orders"] is False
    assert first["execution_allowed"] is False
    assert first["exchange_order_sent"] is False
    assert first["open_positions"] == 0
    assert "AWAITING_NEXT_CANDLE" in first["fill_reasons"]

    opened = trader.apply_decision(
        _decision(DecisionAction.HOLD, RiskVerdict.APPROVED, decision_id="hold-1", ts=2000),
        _candle(2000, "101"),
    )
    assert opened["reason"] == "NOT_ACTIONABLE"
    assert opened["open_positions"] == 1
    assert Decimal(opened["position_qty"]) > 0

    sell = trader.apply_decision(
        _decision(DecisionAction.SELL, RiskVerdict.APPROVED, decision_id="sell-1", ts=3000),
        _candle(3000, "103"),
    )
    assert sell["reason"] == "EXIT_ORDER_PENDING", sell
    closed = trader.apply_decision(
        _decision(DecisionAction.HOLD, RiskVerdict.APPROVED, decision_id="hold-2", ts=4000),
        _candle(4000, "104"),
    )
    assert closed["open_positions"] == 0
    assert any("SIGNAL_SELL" in reason or reason == "FILLED_EXIT" for reason in closed["fill_reasons"])
    assert closed["exchange_order_sent"] is False


def test_veto_and_blocked_do_not_open_a_position(tmp_path: Path) -> None:
    trader = _trader(tmp_path)
    blocked = trader.apply_decision(
        _decision(DecisionAction.BLOCKED, RiskVerdict.APPROVED, decision_id="b1", ts=1000),
        _candle(1000),
    )
    veto = trader.apply_decision(
        _decision(DecisionAction.BUY, RiskVerdict.VETO, decision_id="v1", ts=2000),
        _candle(2000),
    )
    assert blocked["open_positions"] == 0
    assert veto["open_positions"] == 0
    assert veto["order_id"] is None


def test_reopen_continues_the_same_paper_session(tmp_path: Path) -> None:
    path = tmp_path / "auto_paper.sqlite3"
    config = PaperBrokerConfig(initial_balance=Decimal("1000"), max_total_exposure=Decimal("1000"))
    first = AutomaticPaperTrader(path, config)
    first.apply_decision(
        _decision(DecisionAction.BUY, RiskVerdict.APPROVED, decision_id="buy-r", ts=1000),
        _candle(1000),
    )
    second = AutomaticPaperTrader(path, config)
    assert second.session.session_id == first.session.session_id
    opened = second.apply_decision(
        _decision(DecisionAction.HOLD, RiskVerdict.APPROVED, decision_id="hold-r", ts=2000),
        _candle(2000),
    )
    assert opened["open_positions"] == 1
    assert opened["live_orders"] is False


def test_refuses_the_primary_paper_journal(tmp_path: Path) -> None:
    try:
        AutomaticPaperTrader(tmp_path / "cryptonova_paper.sqlite3")
    except RuntimeError as exc:
        assert "refusing_primary_paper_journal" in str(exc)
    else:
        raise AssertionError("primary journal was accepted")
