"""Phase 1D offline tests — confirmed candles + signal dedup."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.candle_time import candle_close_ms, normalize_ts_to_utc_ms
from agent.confirmed_candles import CandleFilterReject, filter_confirmed_candles
from agent.market_data import Candle
from agent.risk import RiskManager
from agent.risk_modes import AccountRiskMode
from agent.runner import AgentRunner
from agent.signal_ids import build_signal_id, correlation_id_from_signal
from agent.signal_ledger import ProcessedSignal, SignalLedger
from agent.strategies.base import Signal, SignalAction
from agent.strategies.ema_rsi import EmaRsiStrategy
from tests.conftest import make_settings


def _ms(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp() * 1000
    )


def _c(start: int, close: float = 10.0) -> Candle:
    return Candle(
        start=start, open=close, high=close + 1, low=close - 1, close=close, volume=1.0
    )


def test_normalize_seconds_to_ms() -> None:
    sec = 1_700_000_000
    assert normalize_ts_to_utc_ms(sec) == sec * 1000
    assert normalize_ts_to_utc_ms(sec * 1000) == sec * 1000


def test_forming_candle_excluded() -> None:
    start = _ms(2026, 1, 1, 12, 0)
    # 15m candle closes 12:15; at 12:14 still forming
    now = _ms(2026, 1, 1, 12, 14)
    series = filter_confirmed_candles(
        [_c(start)], "15", now_ms=now, grace_ms=0, min_bars=1
    )
    assert isinstance(series, CandleFilterReject)
    assert "insufficient confirmed" in series.reason


def test_closed_candle_accepted_after_grace() -> None:
    start = _ms(2026, 1, 1, 12, 0)
    close = candle_close_ms(start, "15")
    now = close + 2_000
    out = filter_confirmed_candles(
        [_c(start)], "15", now_ms=now, grace_ms=2_000, min_bars=1
    )
    assert not isinstance(out, CandleFilterReject)
    assert len(out.candles) == 1
    assert out.newest_close_ms == close


def test_candle_exactly_at_close_boundary_needs_grace() -> None:
    start = _ms(2026, 1, 1, 12, 0)
    close = candle_close_ms(start, "15")
    # Exactly at close, grace=1000 → not confirmed yet
    rejected = filter_confirmed_candles(
        [_c(start)], "15", now_ms=close, grace_ms=1_000, min_bars=1
    )
    assert isinstance(rejected, CandleFilterReject)
    accepted = filter_confirmed_candles(
        [_c(start)], "15", now_ms=close, grace_ms=0, min_bars=1
    )
    assert not isinstance(accepted, CandleFilterReject)


def test_reverse_ordered_bybit_candles() -> None:
    a = _ms(2026, 1, 1, 10, 0)
    b = _ms(2026, 1, 1, 10, 15)
    now = candle_close_ms(b, "15") + 5_000
    # newest first like Bybit
    out = filter_confirmed_candles(
        [_c(b, 11), _c(a, 10)], "15", now_ms=now, grace_ms=0, min_bars=2
    )
    assert not isinstance(out, CandleFilterReject)
    assert out.candles[0].start == a
    assert out.candles[1].start == b


def test_duplicate_candle_timestamps() -> None:
    t = _ms(2026, 1, 1, 10, 0)
    now = candle_close_ms(t, "15") + 5_000
    out = filter_confirmed_candles(
        [_c(t), _c(t)], "15", now_ms=now, grace_ms=0, min_bars=1
    )
    assert isinstance(out, CandleFilterReject)
    assert "duplicate" in out.reason


def test_malformed_ohlcv() -> None:
    t = _ms(2026, 1, 1, 10, 0)
    now = candle_close_ms(t, "15") + 5_000
    bad = Candle(start=t, open=10, high=9, low=11, close=10, volume=1)
    out = filter_confirmed_candles([bad], "15", now_ms=now, grace_ms=0, min_bars=1)
    assert isinstance(out, CandleFilterReject)
    assert "malformed" in out.reason


def test_insufficient_warmup_bars() -> None:
    starts = [_ms(2026, 1, 1, 10, 0) + i * 900_000 for i in range(5)]
    now = candle_close_ms(starts[-1], "15") + 5_000
    out = filter_confirmed_candles(
        [_c(s) for s in starts],
        "15",
        now_ms=now,
        grace_ms=0,
        min_bars=30,
    )
    assert isinstance(out, CandleFilterReject)
    assert "insufficient confirmed" in out.reason


def test_stale_market_data() -> None:
    start = _ms(2026, 1, 1, 10, 0)
    close = candle_close_ms(start, "15")
    now = close + 10_000_000
    out = filter_confirmed_candles(
        [_c(start)],
        "15",
        now_ms=now,
        grace_ms=0,
        min_bars=1,
        max_staleness_ms=60_000,
    )
    assert isinstance(out, CandleFilterReject)
    assert "stale" in out.reason


def test_unsupported_interval() -> None:
    out = filter_confirmed_candles(
        [_c(_ms(2026, 1, 1))], "2", now_ms=_ms(2026, 1, 2), grace_ms=0, min_bars=1
    )
    assert isinstance(out, CandleFilterReject)
    assert "unsupported interval" in out.reason


def test_daily_weekly_monthly_boundaries() -> None:
    d = _ms(2026, 3, 1)
    assert candle_close_ms(d, "D") == d + 86_400_000
    w = _ms(2026, 3, 2)  # Monday
    assert candle_close_ms(w, "W") == w + 7 * 86_400_000
    m = _ms(2026, 1, 1)
    assert candle_close_ms(m, "M") == _ms(2026, 2, 1)
    # Jan 31 close of Jan monthly from Jan 1 open already tested; Feb 1 open:
    assert candle_close_ms(_ms(2026, 2, 1), "M") == _ms(2026, 3, 1)


def test_signal_id_stable_and_correlation() -> None:
    a = build_signal_id(
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        strategy_id="ema_rsi",
        strategy_version="1",
        candle_close_ms=123,
        config_id="cfg",
        action="BUY",
    )
    b = build_signal_id(
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        strategy_id="ema_rsi",
        strategy_version="1",
        candle_close_ms=123,
        config_id="cfg",
        action="BUY",
    )
    c = build_signal_id(
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        strategy_id="ema_rsi",
        strategy_version="1",
        candle_close_ms=124,
        config_id="cfg",
        action="BUY",
    )
    assert a == b
    assert a != c
    assert correlation_id_from_signal(a).startswith("s")


def test_ledger_dedup_survives_restart(tmp_path: Path) -> None:
    db = tmp_path / "sig.sqlite3"
    led1 = SignalLedger(db_path=db)
    sig = ProcessedSignal(
        signal_id="sig_abc",
        symbol="HYPEUSDT",
        category="linear",
        interval="15",
        action="BUY",
        candle_close_ms=1,
    )
    assert led1.mark_processed(env_scope="testnet", account_fp="fp", signal=sig) is True
    led2 = SignalLedger(db_path=db)
    assert led2.has_processed("testnet", "fp", "sig_abc") is True
    assert led2.mark_processed(env_scope="testnet", account_fp="fp", signal=sig) is False


def test_strategy_uses_confirmed_last_bar_metadata() -> None:
    settings = make_settings(ema_fast=2, ema_slow=3, rsi_period=2)
    strat = EmaRsiStrategy(settings)
    # Build enough bars with a clear cross on last confirmed bar
    base = _ms(2026, 1, 1, 0, 0)
    candles = []
    prices = [10, 10, 10, 10, 11, 12]  # slow/fast cross up-ish
    for i, px in enumerate(prices):
        candles.append(_c(base + i * 900_000, px))
    now = candle_close_ms(candles[-1].start, "15") + 5_000
    filtered = filter_confirmed_candles(
        candles, "15", now_ms=now, grace_ms=0, min_bars=strat.min_confirmed_bars()
    )
    assert not isinstance(filtered, CandleFilterReject)
    signal = strat.evaluate(
        filtered.candles, interval="15", symbol="HYPEUSDT", category="linear"
    )
    assert signal.candle_close_ms == filtered.newest_close_ms
    if signal.action is not SignalAction.HOLD:
        assert signal.signal_id.startswith("sig_")


def test_runner_repeated_poll_same_candle_dedup(tmp_path: Path) -> None:
    settings = make_settings(dry_run=True, ema_fast=2, ema_slow=3, rsi_period=2)
    session = MagicMock()
    runner = AgentRunner(
        session,
        settings,
        signal_db_path=tmp_path / "sig.sqlite3",
    )
    # Risk NORMAL with equity
    runner.risk.update_equity(10_000.0)

    base = _ms(2026, 1, 1, 0, 0)
    candles = [_c(base + i * 900_000, 10 + (i * 0.5)) for i in range(30)]
    buy = Signal(
        action=SignalAction.BUY,
        reason="cross",
        price=20.0,
        candle_start_ms=candles[-1].start,
        candle_close_ms=candle_close_ms(candles[-1].start, "15"),
        signal_id=build_signal_id(
            symbol="HYPEUSDT",
            category="linear",
            interval="15",
            strategy_id="ema_rsi",
            strategy_version="1",
            candle_close_ms=candle_close_ms(candles[-1].start, "15"),
            config_id="x",
            action="BUY",
        ),
    )

    with (
        patch("agent.runner.get_equity", return_value=10_000.0),
        patch(
            "agent.runner.get_position",
            return_value=__import__(
                "agent.market_data", fromlist=["PositionSnapshot", "PositionStatus"]
            ).PositionSnapshot(
                status=__import__(
                    "agent.market_data", fromlist=["PositionStatus"]
                ).PositionStatus.FLAT
            ),
        ),
        patch("agent.runner.fetch_candles", return_value=candles),
        patch.object(runner.strategy, "evaluate", return_value=buy),
        patch.object(runner, "_now_ms", return_value=candle_close_ms(candles[-1].start, "15") + 60_000),
        patch.object(runner.executor, "execute", return_value=True) as execute,
        patch.object(
            runner.risk,
            "plan_trade",
            return_value=__import__("agent.risk", fromlist=["TradePlan"]).TradePlan(
                symbol="HYPEUSDT",
                side="Buy",
                qty="1",
                reduce_only=False,
                reason="x",
            ),
        ),
    ):
        runner.tick()
        runner.tick()

    assert execute.call_count == 1


def test_new_closed_candle_allows_new_signal(tmp_path: Path) -> None:
    led = SignalLedger(db_path=tmp_path / "s.sqlite3")
    sid1 = "sig_one"
    sid2 = "sig_two"
    led.mark_processed(
        env_scope="testnet",
        account_fp="fp",
        signal=ProcessedSignal(sid1, "HYPEUSDT", "linear", "15", "BUY", 1),
    )
    assert led.has_processed("testnet", "fp", sid1)
    assert not led.has_processed("testnet", "fp", sid2)


def test_different_symbols_independent(tmp_path: Path) -> None:
    led = SignalLedger(db_path=tmp_path / "s.sqlite3")
    a = build_signal_id(
        symbol="AAAUSDT",
        category="linear",
        interval="15",
        strategy_id="ema_rsi",
        strategy_version="1",
        candle_close_ms=1,
        config_id="c",
        action="BUY",
    )
    b = build_signal_id(
        symbol="BBBUSDT",
        category="linear",
        interval="15",
        strategy_id="ema_rsi",
        strategy_version="1",
        candle_close_ms=1,
        config_id="c",
        action="BUY",
    )
    assert a != b
    led.mark_processed(
        env_scope="t",
        account_fp="f",
        signal=ProcessedSignal(a, "AAAUSDT", "linear", "15", "BUY", 1),
    )
    assert not led.has_processed("t", "f", b)


def test_phase_1a_unknown_still_blocks(tmp_path: Path) -> None:
    from agent.market_data import PositionSnapshot, PositionStatus
    from agent.strategies.base import Signal

    mgr = RiskManager(make_settings(), db_path=tmp_path / "r.sqlite3")
    mgr.update_equity(10_000.0)
    assert (
        mgr.plan_trade(
            MagicMock(),
            "HYPEUSDT",
            Signal(action=SignalAction.BUY, reason="x", price=1.0),
            PositionSnapshot(status=PositionStatus.UNKNOWN, reason="x"),
            10_000.0,
            0,
        )
        is None
    )


def test_phase_1b_unresolved_still_blocks(tmp_path: Path) -> None:
    mgr = RiskManager(
        make_settings(),
        db_path=tmp_path / "r.sqlite3",
        unresolved_intent_checker=lambda: [object()],
    )
    mgr.update_equity(10_000.0)
    assert mgr.authorize_new_exposure() is not None


def test_phase_1c_halt_still_blocks(tmp_path: Path) -> None:
    mgr = RiskManager(make_settings(), db_path=tmp_path / "r.sqlite3")
    mgr.update_equity(10_000.0)
    mgr.update_equity(9_000.0)
    assert mgr.state.mode is AccountRiskMode.HALTED
    assert mgr.authorize_new_exposure() is not None


def test_dry_run_and_mainnet_lock_unchanged() -> None:
    from agent.config import live_orders_blocked

    s = make_settings(dry_run=True, allow_live=False)
    assert s.dry_run is True
    with patch("agent.config.is_live_mainnet", return_value=True):
        assert live_orders_blocked(make_settings(dry_run=False, allow_live=False)) is not None
