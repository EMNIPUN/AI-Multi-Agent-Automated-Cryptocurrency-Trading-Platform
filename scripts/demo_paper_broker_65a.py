#!/usr/bin/env python3
"""
Synthetic local paper-broker demonstration (Prompt 65A).

Uses fictional prices/costs. Not live trading performance.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.paper.accounting import long_gross_pnl, long_net_pnl
from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import PaperCandle
from agent.paper.store import PaperStore


def main() -> int:
    db = ROOT / "data" / "demo_cryptonova_paper_65a.sqlite3"
    if db.exists():
        db.unlink()

    cfg = PaperBrokerConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        max_open_positions=1,
        max_total_exposure=Decimal("1000"),
    )
    broker = PaperBroker(PaperStore(db), cfg)
    sess = broker.create_session(now_ms=1_700_000_000_000, session_id="demo_ps_65a")

    signal = PaperSignalInput(
        signal_id="demo_sig_btc_buy_1",
        symbol="BTCUSDT",
        category="spot",
        action="BUY",
        risk_verdict="APPROVED",
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("52000"),
        position_notional=Decimal("200"),
        signal_candle_start_ms=1_700_000_000_000,
        created_ms=1_700_000_000_000,
        interval="15",
    )
    order_r = broker.submit_signal(session_id=sess.session_id, signal=signal)
    assert order_r.ok and order_r.order_id

    # Signal candle (no fill — need next confirmed bar)
    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=1_700_000_000_000,
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )

    # Next candle → entry
    entry_results = broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=1_700_000_900_000,
            open=Decimal("50000"),
            high=Decimal("50500"),
            low=Decimal("49800"),
            close=Decimal("50200"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    assert any(r.reason == "FILLED_ENTRY" for r in entry_results)
    pos = broker.store.get_open_positions(sess.session_id)[0]

    # Mark candle (no exit)
    broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=1_700_001_800_000,
            open=Decimal("50200"),
            high=Decimal("51000"),
            low=Decimal("50100"),
            close=Decimal("50800"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )

    # TP candle
    exit_results = broker.process_candle(
        session_id=sess.session_id,
        candle=PaperCandle(
            start_ms=1_700_002_700_000,
            open=Decimal("51500"),
            high=Decimal("52100"),
            low=Decimal("51400"),
            close=Decimal("52050"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    assert any("TAKE_PROFIT" in r.reason for r in exit_results)

    closed = broker.store.get_position(pos.position_id)
    assert closed is not None and closed.exit_price is not None
    final = broker.get_session(sess.session_id)
    assert final is not None

    gross = long_gross_pnl(
        quantity=closed.quantity,
        entry_price=closed.entry_price,
        exit_price=closed.exit_price,
    )
    net = long_net_pnl(
        quantity=closed.quantity,
        entry_price=closed.entry_price,
        exit_price=closed.exit_price,
        entry_fee=closed.entry_fee,
        exit_fee=closed.exit_fee,
    )
    assert closed.realized_pnl == net
    assert final.available_balance == Decimal("1000") + net
    assert final.reserved_capital == Decimal("0")

    print("=== CryptoNova Paper Broker Demo 65A (SYNTHETIC) ===")
    print(f"Session ID:        {sess.session_id}")
    print(f"Starting balance:  {cfg.initial_balance} USDT")
    print(f"Signal ID:         {signal.signal_id}")
    print(f"Paper order ID:    {order_r.order_id}")
    print(f"Fill price:        {closed.entry_price}")
    print(f"Position quantity: {closed.quantity}")
    print(f"Exit reason:       {closed.exit_reason}")
    print(f"Exit price:        {closed.exit_price}")
    print(f"Gross PnL:         {gross}")
    print(f"Fees (entry+exit): {closed.entry_fee + closed.exit_fee}")
    print(f"Net PnL:           {net}")
    print(f"Ending balance:    {final.available_balance} USDT")
    print("NOTE: Synthetic local simulation only — not live trading performance.")
    print(f"DB path:           {db}")
    print("To inspect via 65B read API (loopback):")
    print(f"  PAPER_READ_API_ENABLED=true PAPER_SQLITE_PATH={db}")
    print("Broker auto-attach remains OFF. Do not overwrite other paper sessions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
