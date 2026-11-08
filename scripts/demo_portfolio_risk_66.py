#!/usr/bin/env python3
"""
Synthetic portfolio risk demonstration (Prompt 66).

Disposable local paper session. Not live trading performance.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.equity import reconcile_equity
from agent.paper.models import PaperCandle
from agent.paper.portfolio import load_risk_state_view
from agent.paper.risk import ProposedEntry, evaluate_portfolio_entry
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore


def main() -> int:
    db = ROOT / "data" / "demo_cryptonova_paper_66.sqlite3"
    if db.exists():
        db.unlink()

    bcfg = PaperBrokerConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        max_open_positions=5,
        max_total_exposure=Decimal("5000"),
    )
    pr = PortfolioRiskConfig(
        max_risk_fraction_per_trade=Decimal("0.01"),
        max_open_positions=2,
        max_gross_exposure_fraction=Decimal("0.60"),
        max_daily_loss_fraction=Decimal("0.03"),
        max_drawdown_fraction=Decimal("0.10"),
        min_net_risk_reward=Decimal("1.5"),
        fee_rate=bcfg.fee_rate,
        slippage_bps=bcfg.slippage_bps,
    )
    broker = PaperBroker(PaperStore(db), bcfg, portfolio_risk=pr)
    sess = broker.create_session(now_ms=1_700_000_000_000, session_id="demo_ps_66")

    print("=== CryptoNova Portfolio Risk Demo 66 (SYNTHETIC) ===")
    print(f"Session: {sess.session_id}  Start equity: {sess.initial_balance} USDT")
    print(f"Limits: risk/trade=1%  max_pos=2  exposure=60%  daily_loss=3%  DD=10%")

    # Candidate A — valid
    a = evaluate_portfolio_entry(
        session=sess,
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=ProposedEntry(
            symbol="BTCUSDT",
            category="spot",
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profit=Decimal("110"),
            requested_notional=Decimal("500"),
        ),
        config=pr,
        risk_state=load_risk_state_view(broker.store, sess.session_id),
        now_ms=1_700_000_000_000,
    )
    print(f"\nCandidate A (BTC): {a.verdict.value} codes={a.reason_codes}")
    print(f"  sized_qty={a.sized_quantity} notional={a.sized_notional} net_rr={a.net_rr}")

    if a.approved and a.sized_notional is not None:
        broker.submit_signal(
            session_id=sess.session_id,
            signal=PaperSignalInput(
                signal_id="demo66_a",
                symbol="BTCUSDT",
                category="spot",
                action="BUY",
                risk_verdict="APPROVED",
                entry_price=Decimal("100"),
                stop_loss=Decimal("95"),
                take_profit=Decimal("110"),
                position_notional=a.sized_notional,
                signal_candle_start_ms=1_700_000_000_000,
                created_ms=1_700_000_000_000,
            ),
        )
        broker.process_candle(
            session_id=sess.session_id,
            candle=PaperCandle(
                start_ms=1_700_000_900_000,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100.5"),
                symbol="BTCUSDT",
                interval="15",
            ),
        )

    sess = broker.get_session(sess.session_id)
    assert sess is not None
    opens = broker.store.get_open_positions(sess.session_id)
    eq = reconcile_equity(session=sess, open_positions=opens)
    print(f"\nAfter A fill: open={len(opens)} equity={eq.marked_equity} status={eq.valuation_status.value}")
    print(f"  available={eq.available_balance} reserved={eq.reserved_capital} uPnL={eq.unrealized_pnl}")

    # Candidate B — oversized request, should resize or reject under exposure/risk
    b = evaluate_portfolio_entry(
        session=sess,
        open_positions=opens,
        pending_buy_exposure=Decimal("0"),
        proposed=ProposedEntry(
            symbol="ETHUSDT",
            category="spot",
            side="BUY",
            entry_price=Decimal("50"),
            stop_loss=Decimal("45"),
            take_profit=Decimal("60"),
            requested_notional=Decimal("5000"),
        ),
        config=pr,
        risk_state=load_risk_state_view(broker.store, sess.session_id),
        now_ms=1_700_001_000_000,
    )
    print(f"\nCandidate B (ETH oversized): {b.verdict.value} codes={b.reason_codes}")
    print(f"  sized_qty={b.sized_quantity} notional={b.proposed_exposure} net_rr={b.net_rr}")

    # Force daily-loss halt and show blocked entry
    with broker.store.transaction() as conn:
        broker.store.upsert_risk_state(
            conn,
            session_id=sess.session_id,
            halted=True,
            halt_reason="DAILY_LOSS_LIMIT",
            halt_ms=1_700_002_000_000,
            peak_marked_equity=Decimal("1000"),
            day_key="2023-11-14",
            day_start_equity=Decimal("1000"),
            updated_ms=1_700_002_000_000,
        )
    blocked = broker.submit_signal(
        session_id=sess.session_id,
        signal=PaperSignalInput(
            signal_id="demo66_blocked",
            symbol="SOLUSDT",
            category="spot",
            action="BUY",
            risk_verdict="APPROVED",
            entry_price=Decimal("20"),
            stop_loss=Decimal("18"),
            take_profit=Decimal("25"),
            position_notional=Decimal("50"),
            signal_candle_start_ms=1_700_002_000_000,
            created_ms=1_700_002_000_000,
        ),
    )
    print(f"\nAfter daily-loss halt, new entry: ok={blocked.ok} reason={blocked.reason}")

    # Restart recovery
    broker2 = PaperBroker(PaperStore(db), bcfg, portfolio_risk=pr)
    view = load_risk_state_view(broker2.store, sess.session_id)
    print(f"Restart halt preserved: halted={view.halted} reason={view.halt_reason}")
    print(f"DB: {db}")
    print("NOTE: Synthetic local simulation only — not live trading performance.")
    print("PAPER_BROKER_AUTO_ATTACH remains OFF. No exchange/cloud writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
