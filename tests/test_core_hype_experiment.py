"""HYPEUSDT paper experiment. The 3 USDT target does not force a trade."""

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
from agent.supervisor.experiment import assess_position_budget, parse_linear_instrument, run_hype_experiment


def test_five_usdt_budget_stays_flat_when_the_minimum_is_too_large() -> None:
    assessment = assess_position_budget(
        price=Decimal("20"),
        min_qty=Decimal("1"),
        qty_step=Decimal("0.1"),
        min_notional=Decimal("5"),
    )
    assert assessment["risk_budget"] == "0.05"
    assert assessment["feasible"] is False
    assert assessment["result"] == "FLAT"
    assert assessment["leverage"] == "1"


def test_experiment_does_not_order_when_flat(tmp_path: Path) -> None:
    report = run_hype_experiment(
        [Candle(start=1_000, open=20, high=21, low=19, close=20, volume=1)],
        {
            "price": Decimal("20"),
            "min_qty": Decimal("1"),
            "qty_step": Decimal("0.1"),
            "min_notional": Decimal("5"),
        },
        tmp_path / "hype.sqlite3",
    )
    assert report["result"] == "FLAT"
    assert report["orders"] == 0
    assert report["symbol"] == "HYPEUSDT"
    assert report["funding"] == "unsupported"
    assert report["shorting"] == "unsupported"
    assert report["liquidation"] == "unsupported"
    assert report["live_orders"] is False
    assert report["profit_target_is_not_a_requirement"] is True


def test_public_instrument_payload_parses_without_a_network_call() -> None:
    parsed = parse_linear_instrument(
        {
            "result": {
                "list": [
                    {
                        "lotSizeFilter": {
                            "minOrderQty": "0.01",
                            "qtyStep": "0.01",
                            "minNotionalValue": "5",
                        }
                    }
                ]
            }
        },
        price=Decimal("1"),
    )
    assert parsed["min_qty"] == Decimal("0.01")


def test_feasible_hold_records_no_order(tmp_path: Path) -> None:
    def evaluate(**kwargs):
        ts = int(kwargs["now_ms"])
        bar = Candle(start=ts, open=1, high=1, low=1, close=1, volume=1)
        market = MarketSnapshot(
            symbol="HYPEUSDT",
            category=MarketCategoryKind.LINEAR,
            interval="15",
            candles=(bar,),
            closes=(1.0,),
            volumes=(1.0,),
            newest_close_ms=ts,
            as_of_ms=ts,
            data_fresh=True,
            data_path="fixture",
        )
        return CoordinatorDecision(
            action=DecisionAction.HOLD,
            symbol="HYPEUSDT",
            category="linear",
            interval="15",
            timestamp_ms=ts,
            strategy_version="ema_rsi",
            correlation_id="hype",
            decision_id=f"hold-{ts}",
            signal_strength=0.0,
            signal_strength_note="no setup",
            contributions=(),
            risk=RiskAssessment(
                verdict=RiskVerdict.APPROVED,
                reason_codes=("hold",),
                explanation="no setup",
                paper_balance=5.0,
                risk_fraction=0.01,
                position_notional=None,
                stop_distance_pct=0.02,
                reward_distance_pct=None,
                risk_reward=None,
            ),
            reason_codes=("hold",),
            explanation="no setup",
            levels=HypotheticalLevels(entry=None, stop_loss=None, take_profit=None),
            market=market,
            idempotent_key=f"hold-{ts}",
        )

    report = run_hype_experiment(
        [Candle(start=1_000, open=1, high=1.1, low=0.9, close=1, volume=10)],
        {
            "price": Decimal("1"),
            "min_qty": Decimal("0.01"),
            "qty_step": Decimal("0.01"),
            "min_notional": Decimal("0.01"),
        },
        tmp_path / "hype-hold.sqlite3",
        evaluate=evaluate,
    )
    assert report["feasible"] is True
    assert report["orders"] == 0
    assert report["hold_count"] == 1
    assert report["live_orders"] is False
