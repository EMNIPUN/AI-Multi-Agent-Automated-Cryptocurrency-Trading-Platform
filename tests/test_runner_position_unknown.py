"""AgentRunner must not open exposure when position state is UNKNOWN."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.confirmed_candles import ConfirmedCandleSeries
from agent.market_data import Candle, PositionSnapshot, PositionStatus
from agent.runner import AgentRunner
from agent.strategies.base import Signal, SignalAction
from tests.conftest import make_settings


def _series() -> ConfirmedCandleSeries:
    candles = [
        Candle(
            start=1_700_000_000_000 + i * 900_000,
            open=10,
            high=11,
            low=9,
            close=10,
            volume=1,
        )
        for i in range(40)
    ]
    return ConfirmedCandleSeries(
        candles=candles,
        interval="15",
        newest_close_ms=candles[-1].start + 900_000,
        skipped_forming=1,
    )


def test_runner_tick_blocks_entries_and_journals_when_position_unknown(
    tmp_path: Path,
) -> None:
    settings = make_settings(dry_run=True, allow_live=False)
    session = MagicMock()
    runner = AgentRunner(session, settings, signal_db_path=tmp_path / "sig.sqlite3")
    runner.journal = runner.journal.__class__(log_dir=tmp_path)
    runner.risk.update_equity(1_000.0)

    unknown = PositionSnapshot(
        status=PositionStatus.UNKNOWN,
        reason="position query timeout: timed out",
    )
    buy = Signal(
        action=SignalAction.BUY,
        reason="ema cross",
        price=10.0,
        candle_close_ms=1,
        signal_id="sig_test_buy",
    )

    with (
        patch("agent.runner.get_equity", return_value=1000.0),
        patch("agent.runner.get_position", return_value=unknown),
        patch("agent.runner.fetch_candles", return_value=_series().candles),
        patch("agent.runner.filter_confirmed_candles", return_value=_series()),
        patch.object(runner.strategy, "evaluate", return_value=buy),
        patch.object(runner.executor, "execute") as execute,
        patch.object(runner.risk, "plan_trade") as plan_trade,
    ):
        keep_going = runner.tick()

    assert keep_going is True
    plan_trade.assert_not_called()
    execute.assert_not_called()

    rows = runner.journal.path.read_text(encoding="utf-8").splitlines()
    assert any("blocked" in row and "position_state=UNKNOWN" in row for row in rows)
    assert any("position query timeout" in row for row in rows)


def test_runner_tick_does_not_treat_unknown_as_flat_for_display_path(
    tmp_path: Path,
) -> None:
    settings = make_settings()
    session = MagicMock()
    runner = AgentRunner(session, settings, signal_db_path=tmp_path / "sig2.sqlite3")
    runner.journal = runner.journal.__class__(log_dir=tmp_path)
    runner.risk.update_equity(1_000.0)

    unknown = PositionSnapshot(
        status=PositionStatus.UNKNOWN,
        reason="malformed position response: missing result.list",
    )
    hold = Signal(action=SignalAction.HOLD, reason="no cross", price=10.0)

    with (
        patch("agent.runner.get_equity", return_value=1000.0),
        patch("agent.runner.get_position", return_value=unknown),
        patch("agent.runner.fetch_candles", return_value=_series().candles),
        patch("agent.runner.filter_confirmed_candles", return_value=_series()),
        patch.object(runner.strategy, "evaluate", return_value=hold),
        patch.object(runner.executor, "execute") as execute,
    ):
        runner.tick()

    execute.assert_not_called()
