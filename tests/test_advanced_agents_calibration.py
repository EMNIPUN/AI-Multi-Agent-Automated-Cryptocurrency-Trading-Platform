"""Volume/structure agents + offline calibration fail-closed tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.market_data import Candle
from agent.multi_agent.calibration import (
    CalibrationError,
    LabeledOutcome,
    apply_calibration,
    compare_calibration_metrics,
    compute_metrics,
    fit_calibration_profile,
    load_profile,
    load_profile_or_default,
    save_profile,
)
from agent.multi_agent.config import STRATEGY_VERSION, SignalPipelineConfig
from agent.multi_agent.coordinator import directional_conviction
from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.market_agent import build_market_snapshot
from agent.multi_agent.momentum_agent import evaluate_momentum
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.structure_agent import evaluate_structure
from agent.multi_agent.trend_agent import evaluate_trend
from agent.multi_agent.types import DecisionAction
from agent.multi_agent.volume_agent import evaluate_volume
from agent.orchestrator.agent_registry import REGISTRY


def test_volume_and_structure_agents_emit_contributions() -> None:
    closes = bullish_trend_closes(220)
    candles = make_series(closes)
    last = candles[-1]
    candles[-1] = Candle(
        start=last.start,
        open=last.open,
        high=last.high,
        low=last.low,
        close=last.close,
        volume=last.volume * 3.0,
    )
    snap, _ = build_market_snapshot(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
        data_path="public_fixture",
        min_bars=50,
    )
    vol = evaluate_volume(snap)
    struct = evaluate_structure(snap)
    assert vol.agent_id == "volume"
    assert struct.agent_id == "structure"
    assert vol.bias in {"BULLISH", "BEARISH", "NEUTRAL", "INSUFFICIENT_DATA"}
    assert struct.bias in {"BULLISH", "BEARISH", "NEUTRAL", "INSUFFICIENT_DATA"}


def test_pipeline_includes_volume_structure_and_strategy_version() -> None:
    closes = bullish_trend_closes(220)
    candles = make_series(closes)
    decision = SignalPipeline().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
        data_path="public_fixture",
    )
    assert decision.strategy_version == STRATEGY_VERSION
    ids = {c.agent_id for c in decision.contributions}
    assert "volume" in ids
    assert "structure" in ids
    assert decision.execution_allowed is False
    assert decision.action in {
        DecisionAction.BUY,
        DecisionAction.SELL,
        DecisionAction.HOLD,
        DecisionAction.BLOCKED,
    }


def test_directional_conviction_uses_extended_weights() -> None:
    closes = bullish_trend_closes(220)
    candles = make_series(closes)
    snap, _ = build_market_snapshot(
        symbol="ETHUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=series_now_ms(candles),
        data_path="public_fixture",
        min_bars=50,
    )
    cfg = SignalPipelineConfig()
    trend = evaluate_trend(snap)
    mom = evaluate_momentum(snap)
    vol = evaluate_volume(snap)
    struct = evaluate_structure(snap)
    base = directional_conviction(trend, mom, cfg)
    extended = directional_conviction(trend, mom, cfg, volume=vol, structure=struct)
    assert -1.0 <= extended <= 1.0
    assert isinstance(base, float)


def test_registry_lists_volume_structure_regime() -> None:
    ids = {item.agent_id for item in REGISTRY}
    assert {"volume", "structure", "regime"} <= ids
    assert all(
        not item.places_orders
        for item in REGISTRY
        if item.agent_id in {"volume", "structure", "regime"}
    )


def test_fit_apply_and_persist_calibration(tmp_path: Path) -> None:
    outcomes = [
        LabeledOutcome(
            directional_conviction=0.5 if i % 2 == 0 else -0.5,
            action="BUY" if i % 2 == 0 else "SELL",
            realized_pnl=1.0 if i % 3 else -0.4,
            trend_sign=0.6 if i % 2 == 0 else -0.6,
            momentum_sign=0.4 if i % 2 == 0 else -0.4,
            volume_sign=0.2 if i % 2 == 0 else -0.1,
            structure_sign=0.3 if i % 2 == 0 else -0.2,
        )
        for i in range(40)
    ]
    profile = fit_calibration_profile(
        outcomes,
        strategy_version=STRATEGY_VERSION,
        profile_id="unit_test_profile",
        min_samples=20,
    )
    assert profile.profile_hash
    assert profile.buy_threshold > 0
    assert profile.sell_threshold < 0
    path = save_profile(profile, tmp_path / "profile.json")
    loaded = load_profile(path)
    assert loaded.profile_id == profile.profile_id
    cfg = apply_calibration(SignalPipelineConfig(), loaded)
    assert cfg.calibration_profile_id == "unit_test_profile"
    assert cfg.buy_threshold == loaded.buy_threshold
    assert cfg.weights.trend > 0


def test_corrupt_profile_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"profile_id": "x"}), encoding="utf-8")
    try:
        load_profile(bad)
        assert False, "expected CalibrationError"
    except CalibrationError:
        pass
    cfg = SignalPipelineConfig()
    restored = load_profile_or_default(bad, cfg)
    assert restored.calibration_profile_id is None
    assert restored.buy_threshold == cfg.buy_threshold


def test_compare_calibration_metrics() -> None:
    before = compute_metrics(
        [LabeledOutcome(0.4, "BUY", 1.0), LabeledOutcome(-0.4, "SELL", -0.5)]
    )
    after = compute_metrics(
        [LabeledOutcome(0.4, "BUY", 1.2), LabeledOutcome(-0.4, "SELL", 0.2)]
    )
    cmp = compare_calibration_metrics(before, after)
    assert cmp["delta"]["net_pnl"] == after.net_pnl - before.net_pnl
    assert "calibrated_historical_agreement" in cmp["score_kind"]
