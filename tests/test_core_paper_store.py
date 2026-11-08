"""SQLite persistence / idempotency / restart tests for paper broker."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import PaperCandle
from agent.paper.store import PaperStore


def _open_long(tmp_path: Path) -> tuple[PaperBroker, str, str]:
    store = PaperStore(tmp_path / "paper.sqlite3")
    cfg = PaperBrokerConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        max_open_positions=3,
        max_total_exposure=Decimal("5000"),
    )
    b = PaperBroker(store, cfg)
    s = b.create_session(now_ms=1)
    sig = PaperSignalInput(
        signal_id="sig1",
        symbol="BTCUSDT",
        category="spot",
        action="BUY",
        risk_verdict="APPROVED",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        position_notional=Decimal("100"),
        signal_candle_start_ms=1000,
        created_ms=1000,
    )
    b.submit_signal(session_id=s.session_id, signal=sig)
    b.process_candle(
        session_id=s.session_id,
        candle=PaperCandle(
            start_ms=2000,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    pos = b.store.get_open_positions(s.session_id)[0]
    return b, s.session_id, pos.position_id


def test_restart_recovery(tmp_path: Path) -> None:
    b, sid, pid = _open_long(tmp_path)
    sess_before = b.get_session(sid)
    assert sess_before is not None
    avail = sess_before.available_balance
    reserved = sess_before.reserved_capital
    fees = sess_before.fees_paid

    # New broker instance on same DB
    store2 = PaperStore(tmp_path / "paper.sqlite3")
    b2 = PaperBroker(store2, PaperBrokerConfig())
    sess = b2.get_session(sid)
    assert sess is not None
    assert sess.available_balance == avail
    assert sess.reserved_capital == reserved
    assert sess.fees_paid == fees
    positions = b2.store.get_open_positions(sid)
    assert len(positions) == 1
    assert positions[0].position_id == pid


def test_transaction_rollback_no_partial(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    cfg = PaperBrokerConfig(initial_balance=Decimal("1000"))
    b = PaperBroker(store, cfg)
    s = b.create_session(now_ms=1)

    # Force a failure mid-transaction by inserting an order then raising
    from agent.paper.models import OrderSide, OrderStatus, PaperOrder
    from agent.paper.store import new_id

    order = PaperOrder(
        order_id=new_id("po"),
        session_id=s.session_id,
        source_signal_id="rollback_sig",
        symbol="BTCUSDT",
        category="spot",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        intended_entry_price=Decimal("100"),
        status=OrderStatus.PENDING,
        created_ms=1,
        simulated=True,
    )
    with pytest.raises(RuntimeError):
        with store.transaction() as conn:
            store.insert_order(conn, order)
            raise RuntimeError("boom")

    assert store.get_order(order.order_id) is None
    sess = store.get_session(s.session_id)
    assert sess is not None
    assert sess.available_balance == Decimal("1000")


def test_account_events_journal(tmp_path: Path) -> None:
    b, sid, _pid = _open_long(tmp_path)
    events = b.store.list_account_events(sid)
    types = {e["event_type"] for e in events}
    assert "SESSION_CREATED" in types
    assert "ORDER_PENDING" in types
    assert "POSITION_OPENED" in types


def test_schema_version(tmp_path: Path) -> None:
    from sqlalchemy import select

    from apps.api.app.persistence.paper_models import PaperMetaRow

    store = PaperStore(tmp_path / "paper.sqlite3")
    with store.transaction() as conn:
        row = conn.scalar(
            select(PaperMetaRow).where(PaperMetaRow.key == "schema_version")
        )
        assert row is not None
        assert int(row.value) == 2
