"""RiskManager fail-closed behavior for UNKNOWN position state."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.market_data import PositionSnapshot, PositionStatus
from agent.risk import RiskManager
from agent.strategies.base import Signal, SignalAction
from tests.conftest import make_settings


def test_plan_trade_blocks_new_entry_when_unknown() -> None:
    risk = RiskManager(make_settings())
    session = MagicMock()
    signal = Signal(action=SignalAction.BUY, reason="cross", price=10.0)
    snapshot = PositionSnapshot(
        status=PositionStatus.UNKNOWN,
        reason="position api error retCode=10003: Invalid request",
    )

    plan = risk.plan_trade(
        session, "HYPEUSDT", signal, snapshot, equity=1000.0, open_count=0
    )

    assert plan is None


def test_plan_trade_allows_close_when_open_confirmed() -> None:
    risk = RiskManager(make_settings())
    session = MagicMock()
    signal = Signal(action=SignalAction.SELL, reason="exit", price=10.0)
    snapshot = PositionSnapshot(
        status=PositionStatus.OPEN,
        position={
            "symbol": "HYPEUSDT",
            "side": "Buy",
            "size": 1.0,
            "avgPrice": 9.0,
            "unrealisedPnl": 0.0,
        },
    )

    with patch("agent.risk.normalize_qty", return_value="1"):
        plan = risk.plan_trade(
            session, "HYPEUSDT", signal, snapshot, equity=1000.0, open_count=1
        )

    assert plan is not None
    assert plan.reduce_only is True
    assert plan.side == "Sell"
    assert plan.qty == "1"


def test_open_position_count_treats_unknown_as_occupied() -> None:
    risk = RiskManager(make_settings(max_open_positions=1))
    positions = {
        "AAAUSDT": PositionSnapshot(status=PositionStatus.UNKNOWN, reason="timeout"),
        "BBBUSDT": PositionSnapshot(status=PositionStatus.FLAT),
    }
    assert risk.open_position_count(positions) == 1
