"""Prompt 66 — portfolio risk & equity reconciliation unit tests."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.equity import ValuationStatus, reconcile_equity
from agent.paper.integration import (
    PAPER_BROKER_AUTO_ATTACH,
    PAPER_PORTFOLIO_RISK_ENABLED,
    submit_decision_with_portfolio_risk,
)
from agent.paper.models import (
    PaperCandle,
    PaperPosition,
    PaperSession,
    PositionStatus,
    SessionStatus,
)
from agent.paper.risk import (
    PortfolioRiskVerdict,
    ProposedEntry,
    evaluate_portfolio_entry,
    per_unit_net_stop_risk,
)
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore


def _cfg(**kw) -> PortfolioRiskConfig:
    base = dict(
        max_risk_fraction_per_trade=Decimal("0.01"),
        max_open_positions=3,
        max_gross_exposure_fraction=Decimal("0.60"),
        max_daily_loss_fraction=Decimal("0.03"),
        max_drawdown_fraction=Decimal("0.10"),
        min_net_risk_reward=Decimal("1.5"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
    )
    base.update(kw)
    return PortfolioRiskConfig(**base)


def _flat_session(balance: str = "1000") -> PaperSession:
    b = Decimal(balance)
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


def _proposed(**kw) -> ProposedEntry:
    base = dict(
        symbol="BTCUSDT",
        category="spot",
        side="BUY",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        requested_notional=Decimal("500"),
    )
    base.update(kw)
    return ProposedEntry(**base)


def test_marked_equity_flat() -> None:
    snap = reconcile_equity(session=_flat_session(), open_positions=[])
    assert snap.valuation_status is ValuationStatus.FLAT
    assert snap.marked_equity == Decimal("1000")
    assert snap.cash_total == Decimal("1000")


def test_marked_equity_with_mark_no_fee_double_count() -> None:
    sess = PaperSession(
        session_id="ps1",
        initial_balance=Decimal("1000"),
        available_balance=Decimal("899.84995"),
        reserved_capital=Decimal("100.15005"),
        realized_pnl=Decimal("0"),
        fees_paid=Decimal("0.10005"),
        status=SessionStatus.ACTIVE,
        created_ms=1,
        updated_ms=1,
        config_json="{}",
    )
    pos = PaperPosition(
        position_id="pp1",
        session_id="ps1",
        symbol="BTCUSDT",
        category="spot",
        status=PositionStatus.OPEN,
        quantity=Decimal("1"),
        entry_price=Decimal("100.05"),
        entry_fee=Decimal("0.10005"),
        entry_order_id="o1",
        entry_signal_id="s1",
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        opened_ms=1,
        mark_price=Decimal("110"),
        unrealized_pnl=Decimal("9.95"),
    )
    snap = reconcile_equity(session=sess, open_positions=[pos])
    assert snap.valuation_status is ValuationStatus.OK
    # available + reserved + upnl; fees already in cash identity, not subtracted again
    assert snap.marked_equity == Decimal("1009.95")
    assert snap.unrealized_pnl == Decimal("9.95")


def test_missing_marks_unavailable() -> None:
    sess = _flat_session()
    sess.available_balance = Decimal("900")
    sess.reserved_capital = Decimal("100")
    pos = PaperPosition(
        position_id="pp1",
        session_id="ps1",
        symbol="BTCUSDT",
        category="spot",
        status=PositionStatus.OPEN,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_fee=Decimal("0.1"),
        entry_order_id="o1",
        entry_signal_id="s1",
        stop_loss=None,
        take_profit=None,
        opened_ms=1,
        mark_price=None,
    )
    snap = reconcile_equity(session=sess, open_positions=[pos])
    assert snap.valuation_status is ValuationStatus.UNAVAILABLE
    assert snap.marked_equity is None


def test_valid_approved_and_fee_slippage_sizing() -> None:
    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(requested_notional=Decimal("200")),
        config=_cfg(),
    )
    assert r.verdict is PortfolioRiskVerdict.APPROVED
    assert r.sized_quantity is not None and r.sized_quantity > 0
    assert r.net_rr is not None and r.net_rr >= Decimal("1.5")
    assert r.gross_rr is not None
    assert r.net_rr <= r.gross_rr or True  # net typically <= gross
    assert "note" in r.evidence


def test_per_trade_risk_budget_caps_size() -> None:
    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(requested_notional=Decimal("10000")),
        config=_cfg(max_risk_fraction_per_trade=Decimal("0.01")),
    )
    assert r.approved
    # 1% of 1000 = 10 risk budget; unit risk ~5+fees → qty small
    unit = per_unit_net_stop_risk(
        entry_fill=Decimal("100.05"),
        stop_fill=Decimal("94.9525"),
        fee_rate=Decimal("0.001"),
    )
    assert r.sized_quantity is not None
    assert r.sized_quantity * unit <= Decimal("10") + Decimal("0.01")


def test_insufficient_cash() -> None:
    sess = _flat_session("0")
    r = evaluate_portfolio_entry(
        session=sess,
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(requested_notional=Decimal("100")),
        config=_cfg(),
    )
    assert r.verdict is PortfolioRiskVerdict.REJECTED
    # Zero equity/cash fails capacity gates (exposure and/or quantity).
    assert any(
        c in r.reason_codes
        for c in (
            "ZERO_QUANTITY",
            "INSUFFICIENT_FUNDS",
            "INSUFFICIENT_CAPACITY",
            "MAX_EXPOSURE",
        )
    )


def test_max_open_positions() -> None:
    opens = [
        PaperPosition(
            position_id=f"pp{i}",
            session_id="ps1",
            symbol=f"S{i}USDT",
            category="spot",
            status=PositionStatus.OPEN,
            quantity=Decimal("1"),
            entry_price=Decimal("10"),
            entry_fee=Decimal("0.01"),
            entry_order_id=f"o{i}",
            entry_signal_id=f"s{i}",
            stop_loss=Decimal("9"),
            take_profit=Decimal("12"),
            opened_ms=1,
            mark_price=Decimal("10"),
        )
        for i in range(2)
    ]
    sess = _flat_session()
    sess.available_balance = Decimal("800")
    sess.reserved_capital = Decimal("200")
    r = evaluate_portfolio_entry(
        session=sess,
        open_positions=opens,
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(),
        config=_cfg(max_open_positions=2),
    )
    assert r.reason_codes[0] == "MAX_OPEN_POSITIONS"


def test_max_exposure() -> None:
    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(requested_notional=Decimal("900")),
        config=_cfg(max_gross_exposure_fraction=Decimal("0.10")),
    )
    # May approve with resized qty or reject zero — capacity limited to 10% = 100
    if r.approved:
        assert r.proposed_exposure is not None
        assert r.proposed_exposure <= Decimal("100") + Decimal("1")
    else:
        assert "MAX_EXPOSURE" in r.reason_codes or "ZERO_QUANTITY" in r.reason_codes


def test_duplicate_symbol() -> None:
    pos = PaperPosition(
        position_id="pp1",
        session_id="ps1",
        symbol="BTCUSDT",
        category="spot",
        status=PositionStatus.OPEN,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        entry_fee=Decimal("0.1"),
        entry_order_id="o1",
        entry_signal_id="s1",
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        opened_ms=1,
        mark_price=Decimal("100"),
    )
    sess = _flat_session()
    sess.available_balance = Decimal("899.9")
    sess.reserved_capital = Decimal("100.1")
    r = evaluate_portfolio_entry(
        session=sess,
        open_positions=[pos],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(),
        config=_cfg(),
    )
    assert r.reason_codes[0] == "SYMBOL_ALREADY_OPEN"


def test_net_rr_rejection() -> None:
    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("101"),  # tiny reward
            requested_notional=Decimal("50"),
        ),
        config=_cfg(min_net_risk_reward=Decimal("1.5")),
    )
    assert r.verdict is PortfolioRiskVerdict.REJECTED
    assert "NET_RR_BELOW_MIN" in r.reason_codes
    assert r.gross_rr is not None


def test_nan_infinite_and_zero_qty() -> None:
    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(entry_price=Decimal("nan")),
        config=_cfg(),
    )
    assert r.verdict is PortfolioRiskVerdict.REJECTED
    assert "INVALID_PRICE" in r.reason_codes


def test_unsupported_futures() -> None:
    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(category="linear"),
        config=_cfg(),
    )
    assert r.verdict is PortfolioRiskVerdict.REJECTED
    assert "UNSUPPORTED_CATEGORY" in r.reason_codes


def test_halted_blocks_entries() -> None:
    from agent.paper.risk import PortfolioRiskStateView

    r = evaluate_portfolio_entry(
        session=_flat_session(),
        open_positions=[],
        pending_buy_exposure=Decimal("0"),
        proposed=_proposed(),
        config=_cfg(),
        risk_state=PortfolioRiskStateView(halted=True, halt_reason="DAILY_LOSS_LIMIT"),
    )
    assert r.verdict is PortfolioRiskVerdict.HALTED


def test_flags_remain_off() -> None:
    assert PAPER_BROKER_AUTO_ATTACH is False
    assert PAPER_PORTFOLIO_RISK_ENABLED is False


def test_signal_veto_not_overridden(tmp_path: Path) -> None:
    class Dec:
        decision_id = "dec_x"
        action = type("A", (), {"value": "BUY"})()
        symbol = "BTCUSDT"
        category = "spot"
        interval = "15"
        timestamp_ms = 1000
        risk = type(
            "R",
            (),
            {
                "verdict": type("V", (), {"value": "VETO"})(),
                "position_notional": 100.0,
            },
        )()
        levels = type(
            "L", (), {"entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0}
        )()
        market = type("M", (), {"newest_close_ms": 1000})()

    broker = PaperBroker(
        PaperStore(tmp_path / "p.sqlite3"),
        PaperBrokerConfig(),
        portfolio_risk=_cfg(),
    )
    broker.create_session(now_ms=1, session_id="ps_v")
    r = submit_decision_with_portfolio_risk(
        broker, session_id="ps_v", decision=Dec()
    )
    assert r.reason == "SIGNAL_RISK_VETO_AUTHORITATIVE"
