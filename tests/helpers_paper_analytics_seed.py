"""Deterministic paper journal seed for analytics tests/demo."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agent.paper.broker import PaperBroker, PaperSignalInput
from agent.paper.config import PaperBrokerConfig
from agent.paper.models import PaperCandle
from agent.paper.risk_config import PortfolioRiskConfig
from agent.paper.store import PaperStore


def seed_mixed_session(db_path: Path, *, session_id: str = "ps_analytics") -> str:
    """
    Create >=5 closed trades (wins, losses, breakeven), multi-symbol,
    equity snapshots via portfolio_risk candle processing, plus one open.
    """
    store = PaperStore(db_path)
    bcfg = PaperBrokerConfig(
        initial_balance=Decimal("1000"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("0"),  # simplify hand calc
        max_open_positions=5,
        max_total_exposure=Decimal("5000"),
    )
    # Disable mark-required gate for sequential fill by using portfolio risk
    # only for equity snapshots; size via explicit small notionals.
    pr = PortfolioRiskConfig(
        max_risk_fraction_per_trade=Decimal("0.50"),
        max_open_positions=5,
        max_gross_exposure_fraction=Decimal("1.0"),
        max_daily_loss_fraction=Decimal("0.99"),
        max_drawdown_fraction=Decimal("0.99"),
        min_net_risk_reward=Decimal("0"),
        fee_rate=bcfg.fee_rate,
        slippage_bps=bcfg.slippage_bps,
        require_valid_marks_for_entries=False,
    )
    broker = PaperBroker(store, bcfg, portfolio_risk=pr)
    broker.create_session(now_ms=1_000_000, session_id=session_id)

    def run_round(
        *,
        sig: str,
        symbol: str,
        entry: str,
        stop: str,
        tp: str,
        notional: str,
        t0: int,
        fill_open: str,
        exit_o: str,
        exit_h: str,
        exit_l: str,
        exit_c: str,
    ) -> None:
        broker.submit_signal(
            session_id=session_id,
            signal=PaperSignalInput(
                signal_id=sig,
                symbol=symbol,
                category="spot",
                action="BUY",
                risk_verdict="APPROVED",
                entry_price=Decimal(entry),
                stop_loss=Decimal(stop),
                take_profit=Decimal(tp),
                position_notional=Decimal(notional),
                signal_candle_start_ms=t0,
                created_ms=t0,
            ),
        )
        broker.process_candle(
            session_id=session_id,
            candle=PaperCandle(
                start_ms=t0 + 1000,
                open=Decimal(fill_open),
                high=Decimal(fill_open),
                low=Decimal(fill_open),
                close=Decimal(fill_open),
                symbol=symbol,
                interval="15",
            ),
        )
        broker.process_candle(
            session_id=session_id,
            candle=PaperCandle(
                start_ms=t0 + 2000,
                open=Decimal(exit_o),
                high=Decimal(exit_h),
                low=Decimal(exit_l),
                close=Decimal(exit_c),
                symbol=symbol,
                interval="15",
            ),
        )

    # 1 winner TP BTC
    run_round(
        sig="t1",
        symbol="BTCUSDT",
        entry="100",
        stop="90",
        tp="110",
        notional="100",
        t0=1_000_000,
        fill_open="100",
        exit_o="109",
        exit_h="111",
        exit_l="108",
        exit_c="110",
    )
    # 2 loser SL ETH
    run_round(
        sig="t2",
        symbol="ETHUSDT",
        entry="50",
        stop="45",
        tp="60",
        notional="50",
        t0=2_000_000,
        fill_open="50",
        exit_o="46",
        exit_h="47",
        exit_l="44",
        exit_c="45",
    )
    # 3 winner SOL
    run_round(
        sig="t3",
        symbol="SOLUSDT",
        entry="20",
        stop="18",
        tp="22",
        notional="40",
        t0=3_000_000,
        fill_open="20",
        exit_o="21",
        exit_h="23",
        exit_l="20.5",
        exit_c="22",
    )
    # 4 loser BTC again
    run_round(
        sig="t4",
        symbol="BTCUSDT",
        entry="100",
        stop="95",
        tp="120",
        notional="80",
        t0=4_000_000,
        fill_open="100",
        exit_o="96",
        exit_h="97",
        exit_l="94",
        exit_c="95",
    )
    # 5 near-breakeven: exit ≈ entry * 1.001/0.999 so net≈0 after 10bps fees
    # Exact zero BE is covered by pure unit fixtures; seed yields ~0 net.
    run_round(
        sig="t5",
        symbol="ETHUSDT",
        entry="50",
        stop="40",
        tp="50.10010010",
        notional="30",
        t0=5_000_000,
        fill_open="50",
        exit_o="50",
        exit_h="50.11",
        exit_l="49.9",
        exit_c="50.10",
    )

    # Leave one open BTC
    broker.submit_signal(
        session_id=session_id,
        signal=PaperSignalInput(
            signal_id="open1",
            symbol="BTCUSDT",
            category="spot",
            action="BUY",
            risk_verdict="APPROVED",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("130"),
            position_notional=Decimal("50"),
            signal_candle_start_ms=6_000_000,
            created_ms=6_000_000,
        ),
    )
    broker.process_candle(
        session_id=session_id,
        candle=PaperCandle(
            start_ms=6_001_000,
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            symbol="BTCUSDT",
            interval="15",
        ),
    )
    return session_id
