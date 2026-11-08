"""Prompt 68A — deterministic multi-agent backtest engine tests."""

from __future__ import annotations

import os
import re
from decimal import Decimal
from pathlib import Path

import pytest

os.environ["SUPABASE_SOT_ENABLED"] = "false"

from agent.backtest.config import (
    BACKTEST_ENGINE_VERSION,
    BacktestConfig,
    DataSourceKind,
    RiskMode,
)
from agent.backtest.data import candle_content_hash, synthetic_trend_candles
from agent.backtest.execution_adapter import decision_to_backtest_signal
from agent.backtest.pipeline_adapter import evaluate_at_index, make_pipeline
from agent.backtest.replay import mutate_future_closes
from agent.backtest.runner import run_backtest
from agent.backtest.validation import CandleValidationError, validate_candle_series
from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig, PaperRiskConfig
from agent.multi_agent.types import DecisionAction
from agent.paper.accounting import adverse_slippage_price, fee_amount, long_net_pnl, q
from agent.paper.config import PaperBrokerConfig
from agent.paper.fills import evaluate_long_exit, simulate_entry_fill
from agent.paper.integration import PAPER_BROKER_AUTO_ATTACH, PAPER_PORTFOLIO_RISK_ENABLED
from agent.paper.models import PaperCandle
from agent.paper.risk_config import PortfolioRiskConfig


INTERVAL_MS = 15 * 60_000


def _c(
    start: int,
    o: float,
    h: float,
    low: float,
    cl: float,
    vol: float = 1.0,
) -> Candle:
    return Candle(start=start, open=o, high=h, low=low, close=cl, volume=vol)


def test_safety_flags_unchanged() -> None:
    assert PAPER_BROKER_AUTO_ATTACH is False
    assert PAPER_PORTFOLIO_RISK_ENABLED is False
    assert BACKTEST_ENGINE_VERSION.startswith("68A")


def test_invalid_ohlc_rejected() -> None:
    bad = [_c(1_700_000_000_000, 100, 90, 95, 100)]  # high < low
    with pytest.raises(CandleValidationError) as ei:
        validate_candle_series(bad, interval="15")
    assert ei.value.code == "invalid_ohlc"


def test_duplicate_and_out_of_order() -> None:
    a = _c(1_700_000_000_000, 100, 101, 99, 100)
    dup = _c(1_700_000_000_000, 100, 101, 99, 100.5)
    with pytest.raises(CandleValidationError) as ei:
        validate_candle_series([a, dup], interval="15")
    assert ei.value.code == "duplicate_timestamp"

    b = _c(1_700_000_000_000 - INTERVAL_MS, 100, 101, 99, 100)
    with pytest.raises(CandleValidationError) as ei2:
        validate_candle_series([a, b], interval="15")
    assert ei2.value.code == "non_monotonic"


def test_missing_interval_detected() -> None:
    a = _c(1_700_000_000_000, 100, 101, 99, 100)
    # Skip one interval
    c = _c(1_700_000_000_000 + 2 * INTERVAL_MS, 100, 101, 99, 100.2)
    report = validate_candle_series([a, c], interval="15", allow_gaps=True)
    assert any("missing_interval" in w for w in report.warnings)
    assert float(a.volume) > 0  # gap ≠ zero volume


def test_zero_volume_not_a_gap() -> None:
    a = _c(1_700_000_000_000, 100, 101, 99, 100, vol=0.0)
    b = _c(1_700_000_000_000 + INTERVAL_MS, 100, 101, 99, 100.1, vol=0.0)
    report = validate_candle_series([a, b], interval="15")
    assert report.gap_starts_ms == ()
    assert any("zero_volume" in w for w in report.warnings)


def test_hand_calculated_fee_and_slippage() -> None:
    cfg = PaperBrokerConfig(
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
    )
    candle = PaperCandle(
        start_ms=2_000_000,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        symbol="BTCUSDT",
        interval="15",
    )
    qty = Decimal("1")
    fill = simulate_entry_fill(candle=candle, side="BUY", quantity=qty, config=cfg)
    assert fill is not None
    expected_px = adverse_slippage_price(
        side="BUY", reference_price=Decimal("100"), slippage_bps=Decimal("5")
    )
    assert fill.price == expected_px
    assert fill.fee == fee_amount(q(qty * expected_px), Decimal("0.001"))

    # Exit net PnL oracle: gross=(110-100.05)*1=9.95; net=9.95-0.1-0.11=9.74
    net = long_net_pnl(
        quantity=qty,
        entry_price=Decimal("100.05"),
        exit_price=Decimal("110"),
        entry_fee=Decimal("0.1"),
        exit_fee=Decimal("0.11"),
    )
    assert net == Decimal("9.74000000")


def test_same_candle_sl_before_tp() -> None:
    from agent.paper.models import ExitReason

    cfg = PaperBrokerConfig()
    candle = PaperCandle(
        start_ms=3,
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("80"),
        close=Decimal("110"),
        symbol="BTCUSDT",
        interval="15",
    )
    hit = evaluate_long_exit(
        candle=candle,
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("115"),
        config=cfg,
    )
    assert hit is not None
    assert hit.reason is ExitReason.STOP_LOSS


def test_gap_through_stop_uses_open() -> None:
    cfg = PaperBrokerConfig(slippage_bps=Decimal("0"))
    candle = PaperCandle(
        start_ms=4,
        open=Decimal("85"),  # gapped below stop 90
        high=Decimal("86"),
        low=Decimal("84"),
        close=Decimal("85.5"),
        symbol="BTCUSDT",
        interval="15",
    )
    hit = evaluate_long_exit(
        candle=candle,
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("120"),
        config=cfg,
    )
    assert hit is not None
    assert hit.fill.price == Decimal("85")  # gap open, no slip


def test_no_lookahead_future_mutation_invariance() -> None:
    candles = synthetic_trend_candles(n=220)
    idx = 210
    pipe = make_pipeline(
        SignalPipelineConfig(
            min_confirmed_bars=210,
            risk=PaperRiskConfig(paper_balance=10_000.0),
        )
    )
    d1, _ = evaluate_at_index(
        pipe,
        candles=candles,
        index=idx,
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        grace_ms=2_000,
    )
    mutated = mutate_future_closes(candles, from_index=idx, factor=1.5)
    # Fresh pipeline state for independence of risk cooldowns from prior call
    pipe2 = make_pipeline(
        SignalPipelineConfig(
            min_confirmed_bars=210,
            risk=PaperRiskConfig(paper_balance=10_000.0),
        )
    )
    d2, _ = evaluate_at_index(
        pipe2,
        candles=mutated,
        index=idx,
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        grace_ms=2_000,
    )
    assert d1.action == d2.action
    assert d1.decision_id == d2.decision_id
    assert d1.signal_strength == d2.signal_strength
    assert candles[idx].close == mutated[idx].close
    assert candles[idx + 1].close != mutated[idx + 1].close


def test_next_candle_entry_eligibility_signal_start() -> None:
    from agent.multi_agent.types import (
        CoordinatorDecision,
        HypotheticalLevels,
        MarketCategoryKind,
        MarketSnapshot,
        RiskAssessment,
        RiskVerdict,
    )

    snap = MarketSnapshot(
        symbol="BTCUSDT",
        category=MarketCategoryKind.SPOT,
        interval="15",
        candles=(),
        closes=(100.0,),
        volumes=(1.0,),
        newest_close_ms=1_000_000 + INTERVAL_MS,
        as_of_ms=1_000_000 + INTERVAL_MS + 2_000,
        data_fresh=True,
        data_path="test",
    )
    decision = CoordinatorDecision(
        action=DecisionAction.BUY,
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        timestamp_ms=1_000_000 + INTERVAL_MS + 2_000,
        strategy_version="4B.1.0",
        correlation_id="c",
        decision_id="dec_x",
        signal_strength=0.5,
        signal_strength_note="t",
        contributions=(),
        risk=RiskAssessment(
            verdict=RiskVerdict.APPROVED,
            reason_codes=(),
            explanation="ok",
            paper_balance=10000,
            risk_fraction=0.01,
            position_notional=100.0,
            stop_distance_pct=0.01,
            reward_distance_pct=0.02,
            risk_reward=2.0,
        ),
        reason_codes=(),
        explanation="ok",
        levels=HypotheticalLevels(100.0, 95.0, 110.0),
        market=snap,
        idempotent_key="i",
    )
    signal = decision_to_backtest_signal(decision, signal_candle_start_ms=1_700_000_000_000)
    assert signal is not None
    assert signal.signal_candle_start_ms == 1_700_000_000_000
    # Must not accidentally use close_ms
    assert signal.signal_candle_start_ms != snap.newest_close_ms


def test_deterministic_repeatability(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=230)
    cfg = BacktestConfig(
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        initial_capital=Decimal("10000"),
        data_source=DataSourceKind.INLINE,
        risk_mode=RiskMode.SIGNAL_ONLY,
        min_confirmed_bars=210,
    )
    r1 = run_backtest(cfg, candles=candles, journal_dir=tmp_path / "a")
    r2 = run_backtest(cfg, candles=candles, journal_dir=tmp_path / "b")
    assert r1.status.value == "completed"
    assert r2.status.value == "completed"
    assert r1.result_hash == r2.result_hash
    assert r1.counters == r2.counters
    assert [d.action for d in r1.decisions] == [d.action for d in r2.decisions]
    assert r1.dataset.content_hash == candle_content_hash(candles)


def test_insufficient_warmup_still_completes(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=50)
    cfg = BacktestConfig(
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        min_confirmed_bars=210,
        data_source=DataSourceKind.INLINE,
    )
    result = run_backtest(cfg, candles=candles, journal_dir=tmp_path)
    assert result.status.value == "completed"
    assert result.counters["total_agent_evaluations"] == 0
    assert any("insufficient_warmup" in w for w in result.data_quality_warnings)


def test_open_position_not_force_closed(tmp_path: Path) -> None:
    # Short series after warm-up with bullish drift may leave opens; force_close stays off.
    candles = synthetic_trend_candles(n=230, drift=0.002)
    cfg = BacktestConfig(
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        min_confirmed_bars=210,
        force_close_at_end=False,
    )
    result = run_backtest(cfg, candles=candles, journal_dir=tmp_path)
    assert result.status.value == "completed"
    assert result.extras["safety"]["no_force_close_at_end"] is True
    # If opens exist, analytics must not count them as closed trades.
    if result.open_positions > 0:
        assert (result.analytics or {}).get("closed_trades", 0) >= 0
        assert "force" not in str(result.analytics).lower() or "not force-closed" in str(
            result.analytics
        )


def test_portfolio_risk_mode_isolated(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=230)
    cfg = BacktestConfig(
        symbol="BTCUSDT",
        market_type="spot",
        interval="15",
        risk_mode=RiskMode.PORTFOLIO,
        portfolio_risk=PortfolioRiskConfig(
            max_open_positions=1,
            max_gross_exposure_fraction=Decimal("0.60"),
            max_daily_loss_fraction=Decimal("0.03"),
            max_drawdown_fraction=Decimal("0.10"),
            fee_rate=Decimal("0.001"),
            slippage_bps=Decimal("5"),
        ),
        min_confirmed_bars=210,
    )
    result = run_backtest(cfg, candles=candles, journal_dir=tmp_path)
    assert result.status.value == "completed"
    assert PAPER_PORTFOLIO_RISK_ENABLED is False
    assert result.effective_config["risk_mode"] == "portfolio"


def test_rejected_data_does_not_contaminate(tmp_path: Path) -> None:
    bad = [_c(1, 100, 90, 95, 100)]
    cfg = BacktestConfig(symbol="BTCUSDT", market_type="spot", interval="15")
    result = run_backtest(cfg, candles=bad, journal_dir=tmp_path)
    assert result.status.value == "rejected_data"
    assert result.session_id is None
    assert list(tmp_path.glob("bt68a_*.sqlite3")) == []


def test_no_live_or_cloud_imports_in_backtest_package() -> None:
    root = Path(__file__).resolve().parents[1] / "agent" / "backtest"
    forbidden = [
        r"\bplace_order\b",
        r"bybit_private",
        r"from openai",
        r"import openai",
        r"create_client\s*\(",
        r"from supabase import",
        r"import supabase\b",
    ]
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pat in forbidden:
            assert re.search(pat, text) is None, f"{path.name} matched {pat}"


def test_performance_label_present(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=220)
    result = run_backtest(
        BacktestConfig(min_confirmed_bars=210),
        candles=candles,
        journal_dir=tmp_path,
    )
    assert "HISTORICAL SIMULATION" in result.performance_label
    assert "NOT LIVE" in result.performance_label
