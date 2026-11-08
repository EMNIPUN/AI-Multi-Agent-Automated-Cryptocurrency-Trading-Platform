"""Unit tests for local paper broker — offline fixtures only."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from agent.paper.accounting import (
    adverse_slippage_price,
    fee_amount,
    long_gross_pnl,
    long_net_pnl,
    notional,
)
from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.fills import evaluate_long_exit
from agent.paper.models import ExitReason, PaperCandle
from agent.paper.store import PaperStore


def _cfg(**kwargs) -> PaperBrokerConfig:
    base = dict(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        max_open_positions=1,
        max_total_exposure=Decimal("1000"),
    )
    base.update(kwargs)
    return PaperBrokerConfig(**base)


def _broker(tmp_path: Path, **kwargs) -> PaperBroker:
    store = PaperStore(tmp_path / "paper.sqlite3")
    return PaperBroker(store, _cfg(**kwargs))


def _buy_signal(
    *,
    signal_id: str = "sig_buy_1",
    entry: str = "100",
    stop: str = "95",
    tp: str = "110",
    notional_v: str = "100",
    candle_ms: int = 1_000_000,
    created_ms: int = 1_000_000,
) -> PaperSignalInput:
    return PaperSignalInput(
        signal_id=signal_id,
        symbol="BTCUSDT",
        category="spot",
        action="BUY",
        risk_verdict="APPROVED",
        entry_price=Decimal(entry),
        stop_loss=Decimal(stop),
        take_profit=Decimal(tp),
        position_notional=Decimal(notional_v),
        signal_candle_start_ms=candle_ms,
        created_ms=created_ms,
        interval="15",
    )


def _candle(
    start_ms: int,
    o: str,
    h: str,
    l: str,
    c: str,
    symbol: str = "BTCUSDT",
) -> PaperCandle:
    return PaperCandle(
        start_ms=start_ms,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        symbol=symbol,
        interval="15",
    )


def test_session_initialization(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    assert s.available_balance == Decimal("1000")
    assert s.reserved_capital == Decimal("0")
    assert s.realized_pnl == Decimal("0")
    loaded = b.get_session(s.session_id)
    assert loaded is not None
    assert loaded.available_balance == Decimal("1000")


def test_hold_ignored(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    sig = _buy_signal()
    sig = PaperSignalInput(**{**sig.__dict__, "action": "HOLD"})
    r = b.submit_signal(session_id=s.session_id, signal=sig)
    assert r.reason == "HOLD_IGNORED"
    assert r.ok is False


def test_blocked_ignored(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    sig = PaperSignalInput(**{**_buy_signal().__dict__, "action": "BLOCKED"})
    r = b.submit_signal(session_id=s.session_id, signal=sig)
    assert r.reason == "BLOCKED_IGNORED"


def test_risk_veto_ignored(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    sig = PaperSignalInput(**{**_buy_signal().__dict__, "risk_verdict": "VETO"})
    r = b.submit_signal(session_id=s.session_id, signal=sig)
    assert r.reason == "RISK_VETO_IGNORED"


def test_valid_buy_pending(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    r = b.submit_signal(session_id=s.session_id, signal=_buy_signal())
    assert r.ok and r.reason == "ORDER_PENDING"
    assert r.order_id is not None


def test_invalid_quantity_rejected(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    sig = PaperSignalInput(
        **{**_buy_signal().__dict__, "position_notional": Decimal("0")}
    )
    r = b.submit_signal(session_id=s.session_id, signal=sig)
    assert r.ok is False
    assert r.reason == "INVALID_NOTIONAL"


def test_insufficient_funds_rejected(tmp_path: Path) -> None:
    b = _broker(tmp_path, initial_balance=Decimal("10"))
    s = b.create_session(now_ms=1)
    r = b.submit_signal(
        session_id=s.session_id,
        signal=_buy_signal(notional_v="100"),
    )
    assert r.ok is False
    assert r.reason == "INSUFFICIENT_FUNDS"


def test_adverse_slippage_and_entry_fee() -> None:
    ref = Decimal("100")
    buy = adverse_slippage_price(
        side="BUY", reference_price=ref, slippage_bps=Decimal("5")
    )
    assert buy == Decimal("100.05")
    n = notional(Decimal("1"), buy)
    fee = fee_amount(n, Decimal("0.001"))
    assert fee == Decimal("0.10005")


def test_entry_fill_opens_position(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    r = b.submit_signal(session_id=s.session_id, signal=_buy_signal(candle_ms=1000))
    assert r.ok
    # Same candle as signal → await next
    await_r = b.process_candle(
        session_id=s.session_id, candle=_candle(1000, "100", "101", "99", "100.5")
    )
    assert any(x.reason == "AWAITING_NEXT_CANDLE" for x in await_r)

    fill_r = b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "102", "99", "101")
    )
    assert any(x.reason == "FILLED_ENTRY" for x in fill_r)
    positions = b.store.get_open_positions(s.session_id)
    assert len(positions) == 1
    assert positions[0].entry_price == Decimal("100.05")  # 5 bps adverse
    sess = b.get_session(s.session_id)
    assert sess is not None
    assert sess.available_balance < Decimal("1000")
    assert sess.reserved_capital > 0
    assert sess.fees_paid > 0


def test_no_lookahead(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(session_id=s.session_id, signal=_buy_signal(candle_ms=5000))
    # Earlier candle must not fill
    r = b.process_candle(
        session_id=s.session_id, candle=_candle(4000, "100", "101", "99", "100")
    )
    assert any(x.reason == "AWAITING_NEXT_CANDLE" for x in r)
    assert b.store.get_open_positions(s.session_id) == []


def test_missing_next_candle_stays_pending(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    r = b.submit_signal(session_id=s.session_id, signal=_buy_signal())
    order = b.store.get_order(r.order_id)  # type: ignore[arg-type]
    assert order is not None
    assert order.status.value == "PENDING"
    assert b.store.get_open_positions(s.session_id) == []


def test_mark_to_market(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(session_id=s.session_id, signal=_buy_signal(candle_ms=1000))
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "102", "99", "101")
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(3000, "101", "105", "100", "104")
    )
    pos = b.store.get_open_positions(s.session_id)[0]
    assert pos.mark_price == Decimal("104")
    assert pos.unrealized_pnl != 0


def test_tp_exit(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(
        session_id=s.session_id,
        signal=_buy_signal(entry="100", stop="90", tp="110", candle_ms=1000),
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100.5")
    )
    r = b.process_candle(
        session_id=s.session_id, candle=_candle(3000, "105", "111", "104", "110.5")
    )
    assert any("TAKE_PROFIT" in x.reason for x in r)
    assert b.store.get_open_positions(s.session_id) == []


def test_sl_exit(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(
        session_id=s.session_id,
        signal=_buy_signal(entry="100", stop="95", tp="120", candle_ms=1000),
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    r = b.process_candle(
        session_id=s.session_id, candle=_candle(3000, "98", "99", "94", "96")
    )
    assert any("STOP_LOSS" in x.reason for x in r)


def test_same_bar_sl_tp_collision() -> None:
    cfg = _cfg()
    candle = _candle(1, "100", "120", "90", "100")
    trig = evaluate_long_exit(
        candle=candle,
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        config=cfg,
    )
    assert trig is not None
    assert trig.reason is ExitReason.STOP_LOSS


def test_gap_through_stop() -> None:
    cfg = _cfg()
    # Open gaps below stop
    candle = _candle(1, "90", "92", "88", "91")
    trig = evaluate_long_exit(
        candle=candle,
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("120"),
        config=cfg,
    )
    assert trig is not None
    assert trig.reason is ExitReason.STOP_LOSS
    # Fill base is gap open (90), then adverse sell slippage
    assert trig.fill.price < Decimal("90")


def test_no_exit() -> None:
    cfg = _cfg()
    candle = _candle(1, "100", "105", "98", "102")
    trig = evaluate_long_exit(
        candle=candle,
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("120"),
        config=cfg,
    )
    assert trig is None


def test_net_realized_pnl_and_balance(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(
        session_id=s.session_id,
        signal=_buy_signal(
            entry="100", stop="90", tp="110", notional_v="100", candle_ms=1000
        ),
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    pos = b.store.get_open_positions(s.session_id)[0]
    entry = pos.entry_price
    qty = pos.quantity
    entry_fee = pos.entry_fee

    b.process_candle(
        session_id=s.session_id, candle=_candle(3000, "110", "111", "109", "110")
    )
    # TP at 110 with sell slippage
    closed = b.store.get_position(pos.position_id)
    assert closed is not None and closed.status.value == "CLOSED"
    expected_net = long_net_pnl(
        quantity=qty,
        entry_price=entry,
        exit_price=closed.exit_price,  # type: ignore[arg-type]
        entry_fee=entry_fee,
        exit_fee=closed.exit_fee,
    )
    assert closed.realized_pnl == expected_net
    sess = b.get_session(s.session_id)
    assert sess is not None
    assert sess.available_balance == Decimal("1000") + expected_net
    assert sess.reserved_capital == Decimal("0")
    assert sess.realized_pnl == expected_net


def test_max_positions(tmp_path: Path) -> None:
    b = _broker(tmp_path, max_open_positions=1)
    s = b.create_session(now_ms=1)
    b.submit_signal(
        session_id=s.session_id, signal=_buy_signal(signal_id="a", candle_ms=1000)
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    assert len(b.store.get_open_positions(s.session_id)) == 1
    # Different symbol so one-per-symbol does not mask max-positions guard
    r = b.submit_signal(
        session_id=s.session_id,
        signal=PaperSignalInput(
            signal_id="b",
            symbol="ETHUSDT",
            category="spot",
            action="BUY",
            risk_verdict="APPROVED",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit=Decimal("110"),
            position_notional=Decimal("100"),
            signal_candle_start_ms=3000,
            created_ms=3000,
        ),
    )
    assert r.reason == "MAX_OPEN_POSITIONS"


def test_max_exposure(tmp_path: Path) -> None:
    b = _broker(tmp_path, max_total_exposure=Decimal("50"))
    s = b.create_session(now_ms=1)
    r = b.submit_signal(
        session_id=s.session_id, signal=_buy_signal(notional_v="100")
    )
    assert r.reason == "MAX_EXPOSURE"


def test_duplicate_signal(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    r1 = b.submit_signal(session_id=s.session_id, signal=_buy_signal())
    r2 = b.submit_signal(session_id=s.session_id, signal=_buy_signal())
    assert r2.reason == "DUPLICATE_SIGNAL"
    assert r2.order_id == r1.order_id


def test_duplicate_fill(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(session_id=s.session_id, signal=_buy_signal(candle_ms=1000))
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    # Replaying same candle
    r = b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    assert any(x.reason == "DUPLICATE_CANDLE" for x in r)
    assert len(b.store.get_open_positions(s.session_id)) == 1


def test_duplicate_exit(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.submit_signal(
        session_id=s.session_id,
        signal=_buy_signal(entry="100", stop="95", tp="120", candle_ms=1000),
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    b.process_candle(
        session_id=s.session_id, candle=_candle(3000, "98", "99", "94", "96")
    )
    # Second SL candle shouldn't reopen/close again
    assert b.store.get_open_positions(s.session_id) == []
    r = b.process_candle(
        session_id=s.session_id, candle=_candle(4000, "90", "91", "89", "90")
    )
    assert all("CLOSED_" not in x.reason for x in r)


def test_out_of_order_candle(tmp_path: Path) -> None:
    b = _broker(tmp_path)
    s = b.create_session(now_ms=1)
    b.process_candle(
        session_id=s.session_id, candle=_candle(3000, "100", "101", "99", "100")
    )
    r = b.process_candle(
        session_id=s.session_id, candle=_candle(2000, "100", "101", "99", "100")
    )
    assert any(x.reason == "OUT_OF_ORDER_CANDLE" for x in r)


def test_gross_vs_net_math() -> None:
    qty = Decimal("1")
    entry = Decimal("100")
    exit_p = Decimal("110")
    entry_fee = Decimal("0.1")
    exit_fee = Decimal("0.11")
    gross = long_gross_pnl(quantity=qty, entry_price=entry, exit_price=exit_p)
    net = long_net_pnl(
        quantity=qty,
        entry_price=entry,
        exit_price=exit_p,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
    )
    assert gross == Decimal("10")
    assert net == Decimal("9.79")


def test_no_private_bybit_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "agent" / "paper"
    banned = (
        "from agent.automation",
        "import agent.automation",
        "place_order",
        "bybit_private",
        "import openai",
        "from openai",
    )
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for token in banned:
            assert token.lower() not in lower, f"{path.name} contains {token}"
