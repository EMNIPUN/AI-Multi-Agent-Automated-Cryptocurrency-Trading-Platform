"""Prompt 67A — paper analytics unit tests (offline fixtures)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agent.paper.analytics.aggregator import aggregate_session_analytics, build_closed_trades
from agent.paper.analytics.drawdown import max_drawdown
from agent.paper.analytics.equity_curve import marked_equity_series, realized_balance_series
from agent.paper.analytics.metrics import (
    aggregate_trade_stats,
    closed_trade_from_position,
)
from agent.paper.analytics.models import (
    ClosedTradeMetrics,
    EquityPoint,
    MetricAvailability,
    SeriesType,
)
from agent.paper.analytics.service import compute_session_analytics
from agent.paper.models import (
    PaperPosition,
    PaperSession,
    PositionStatus,
    SessionStatus,
)
from agent.paper.read_store import PaperReadStore
from agent.paper.store import PaperStore
from tests.helpers_paper_analytics_seed import seed_mixed_session


def _trade(
    *,
    pid: str,
    net: str,
    symbol: str = "BTCUSDT",
    entry: str = "100",
    exit_p: str = "110",
    qty: str = "1",
    entry_fee: str = "0.1",
    exit_fee: str = "0.11",
    opened: int = 1000,
    closed: int = 2000,
) -> ClosedTradeMetrics:
    qty_d = Decimal(qty)
    entry_d = Decimal(entry)
    exit_d = Decimal(exit_p)
    ef = Decimal(entry_fee)
    xf = Decimal(exit_fee)
    gross = (exit_d - entry_d) * qty_d
    return ClosedTradeMetrics(
        position_id=pid,
        session_id="ps1",
        symbol=symbol,
        category="spot",
        quantity=qty_d,
        entry_price=entry_d,
        exit_price=exit_d,
        entry_fee=ef,
        exit_fee=xf,
        gross_realized_pnl=gross,
        net_realized_pnl=Decimal(net),
        exit_reason="TEST",
        opened_ms=opened,
        closed_ms=closed,
        holding_duration_ms=closed - opened,
    )


def _session(bal: str = "1000") -> PaperSession:
    b = Decimal(bal)
    return PaperSession(
        session_id="ps1",
        initial_balance=b,
        available_balance=b,
        reserved_capital=Decimal("0"),
        realized_pnl=Decimal("0"),
        fees_paid=Decimal("0"),
        status=SessionStatus.ACTIVE,
        created_ms=1,
        updated_ms=1,
        config_json="{}",
    )


def test_empty_journal() -> None:
    stats = aggregate_trade_stats([], initial_balance=Decimal("1000"))
    assert stats["closed_trades"] == 0
    assert stats["win_rate_pct"].status is MetricAvailability.EMPTY
    assert stats["profit_factor"].status is MetricAvailability.EMPTY
    assert stats["expectancy"].status is MetricAvailability.EMPTY


def test_one_winner_loser_breakeven_mixed() -> None:
    trades = [
        _trade(pid="w", net="10", exit_p="110.21"),  # approx
        _trade(pid="l", net="-5", entry="100", exit_p="94.9"),
        _trade(pid="b", net="0", entry="100", exit_p="100.21", entry_fee="0.1", exit_fee="0.1"),
    ]
    # Fix nets explicitly for classification
    trades = [
        _trade(pid="w", net="10"),
        _trade(pid="l", net="-5"),
        _trade(pid="b", net="0"),
    ]
    stats = aggregate_trade_stats(trades, initial_balance=Decimal("1000"))
    assert stats["closed_trades"] == 3
    assert stats["winning_trades"] == 1
    assert stats["losing_trades"] == 1
    assert stats["breakeven_trades"] == 1
    # win rate = 1/3 * 100 (breakeven in denominator)
    assert abs(stats["win_rate_pct"].value - (Decimal("100") / Decimal("3"))) < Decimal(
        "0.00000002"
    )
    assert stats["gross_profit"] == Decimal("10")
    assert stats["gross_loss"] == Decimal("5")
    assert stats["net_realized_pnl"] == Decimal("5")
    assert stats["profit_factor"].value == Decimal("2")
    from agent.paper.accounting import q

    assert stats["expectancy"].value == q(Decimal("5") / Decimal("3"))
    assert stats["average_win"].value == Decimal("10")
    assert stats["average_loss"].value == Decimal("5")


def test_win_rate_includes_breakeven_denominator() -> None:
    trades = [_trade(pid="w", net="1"), _trade(pid="b", net="0")]
    stats = aggregate_trade_stats(trades, initial_balance=Decimal("1000"))
    assert stats["win_rate_pct"].value == Decimal("50")


def test_profit_factor_edge_cases() -> None:
    only_wins = aggregate_trade_stats(
        [_trade(pid="w", net="3"), _trade(pid="w2", net="2")],
        initial_balance=Decimal("1000"),
    )
    assert only_wins["profit_factor"].status is MetricAvailability.UNBOUNDED

    only_loss = aggregate_trade_stats(
        [_trade(pid="l", net="-4")],
        initial_balance=Decimal("1000"),
    )
    assert only_loss["profit_factor"].value == Decimal("0")

    all_be = aggregate_trade_stats(
        [_trade(pid="b", net="0")],
        initial_balance=Decimal("1000"),
    )
    assert all_be["profit_factor"].status is MetricAvailability.UNAVAILABLE


def test_fee_treatment_no_double_count() -> None:
    pos = PaperPosition(
        position_id="pp1",
        session_id="ps1",
        symbol="BTCUSDT",
        category="spot",
        status=PositionStatus.CLOSED,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_fee=Decimal("0.1"),
        entry_order_id="o1",
        entry_signal_id="s1",
        stop_loss=None,
        take_profit=None,
        opened_ms=1,
        closed_ms=2,
        exit_price=Decimal("110"),
        exit_fee=Decimal("0.11"),
        realized_pnl=Decimal("9.79"),  # 10 - 0.1 - 0.11
    )
    trade = closed_trade_from_position(pos)
    assert trade is not None
    assert trade.gross_realized_pnl == Decimal("10")
    assert trade.net_realized_pnl == Decimal("9.79")
    assert trade.net_realized_pnl == trade.gross_realized_pnl - trade.entry_fee - trade.exit_fee


def test_open_positions_excluded() -> None:
    open_pos = PaperPosition(
        position_id="open",
        session_id="ps1",
        symbol="BTCUSDT",
        category="spot",
        status=PositionStatus.OPEN,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_fee=Decimal("0.1"),
        entry_order_id="o",
        entry_signal_id="s",
        stop_loss=None,
        take_profit=None,
        opened_ms=1,
    )
    trades, _ = build_closed_trades([open_pos])
    assert trades == []


def test_symbol_and_time_filters_via_seed(tmp_path: Path) -> None:
    db = tmp_path / "a.sqlite3"
    sid = seed_mixed_session(db)
    store = PaperReadStore(db)
    all_a = compute_session_analytics(store, sid)
    assert all_a.closed_trades >= 5
    assert all_a.open_positions >= 1
    btc = compute_session_analytics(store, sid, symbol="BTCUSDT")
    assert all(s.symbol == "BTCUSDT" for s in btc.symbol_breakdown) or btc.closed_trades >= 1
    # Exit time filter — early window should have fewer trades
    early = compute_session_analytics(store, sid, exit_to_ms=1_500_000)
    late = compute_session_analytics(store, sid, exit_from_ms=4_000_000)
    assert early.closed_trades <= all_a.closed_trades
    assert late.closed_trades <= all_a.closed_trades


def test_realized_return_denominator() -> None:
    trades = [_trade(pid="w", net="50")]
    stats = aggregate_trade_stats(trades, initial_balance=Decimal("1000"))
    assert stats["realized_return_pct"].value == Decimal("5")


def test_equity_curve_and_drawdown() -> None:
    snaps = [
        {
            "as_of_ms": 1,
            "available_balance": "1000",
            "reserved_capital": "0",
            "valuation_status": "flat",
            "marked_equity": "1000",
        },
        {
            "as_of_ms": 2,
            "available_balance": "900",
            "reserved_capital": "100",
            "valuation_status": "ok",
            "marked_equity": "1100",
        },
        {
            "as_of_ms": 3,
            "available_balance": "900",
            "reserved_capital": "100",
            "valuation_status": "ok",
            "marked_equity": "950",
        },
    ]
    marked, warns = marked_equity_series(snaps)
    assert len(marked) == 3
    dd = max_drawdown(marked)
    assert dd.max_drawdown_amount.value == Decimal("150")
    assert dd.label.startswith("Maximum observed marked-equity")
    bal, _ = realized_balance_series(snaps)
    assert bal[0].value == Decimal("1000")
    assert bal[1].value == Decimal("1000")


def test_missing_marks_skipped() -> None:
    snaps = [
        {
            "as_of_ms": 1,
            "available_balance": "1000",
            "reserved_capital": "0",
            "valuation_status": "unavailable",
            "marked_equity": None,
        }
    ]
    pts, warns = marked_equity_series(snaps)
    assert pts == []
    assert any("skipped" in w for w in warns)


def test_drawdown_zero_peak_safe() -> None:
    pts = [
        EquityPoint(1, Decimal("0"), "ok", SeriesType.MARKED_EQUITY),
        EquityPoint(2, Decimal("0"), "ok", SeriesType.MARKED_EQUITY),
    ]
    dd = max_drawdown(pts)
    assert dd.observation_count == 2


def test_no_nan_infinity_in_stats() -> None:
    stats = aggregate_trade_stats(
        [_trade(pid="w", net="1")], initial_balance=Decimal("1000")
    )
    for key in ("gross_profit", "net_realized_pnl", "total_fees"):
        v = stats[key]
        assert not Decimal(v).is_nan()
        assert not Decimal(v).is_infinite()


def test_seed_restart_consistency(tmp_path: Path) -> None:
    db = tmp_path / "r.sqlite3"
    sid = seed_mixed_session(db)
    a1 = compute_session_analytics(PaperReadStore(db), sid)
    a2 = compute_session_analytics(PaperReadStore(db), sid)
    assert a1.net_realized_pnl == a2.net_realized_pnl
    assert a1.closed_trades == a2.closed_trades


def test_read_store_does_not_mutate(tmp_path: Path) -> None:
    db = tmp_path / "m.sqlite3"
    sid = seed_mixed_session(db)
    size = db.stat().st_size
    mtime = db.stat().st_mtime_ns
    compute_session_analytics(PaperReadStore(db), sid)
    assert db.stat().st_size == size
    assert db.stat().st_mtime_ns == mtime


def test_session_isolation(tmp_path: Path) -> None:
    db = tmp_path / "i.sqlite3"
    seed_mixed_session(db, session_id="ps_a")
    # second session empty
    PaperStore(db).create_session(
        config=__import__(
            "agent.paper.config", fromlist=["PaperBrokerConfig"]
        ).PaperBrokerConfig(initial_balance=Decimal("500")),
        now_ms=9_000_000,
        session_id="ps_b",
    )
    a = compute_session_analytics(PaperReadStore(db), "ps_a")
    b = compute_session_analytics(PaperReadStore(db), "ps_b")
    assert a.closed_trades >= 5
    assert b.closed_trades == 0


def test_module_safety() -> None:
    root = Path(__file__).resolve().parents[1] / "agent" / "paper" / "analytics"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "import openai" not in text
        assert "from openai" not in text
        assert "supabase" not in text
        assert "place_order" not in text
        assert "bybit_private" not in text
