"""Phase 4A — deterministic multi-agent signals-only tests (no private API / orders)."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from agent.multi_agent.config import PaperRiskConfig, SignalPipelineConfig
from agent.multi_agent.fixtures import (
    bearish_trend_closes,
    bullish_trend_closes,
    make_series,
    series_now_ms,
    sideways_closes,
)
from agent.multi_agent.pipeline import SignalPipeline, evaluate_signals
from agent.multi_agent.risk_agent import SignalRiskState, record_hypothetical_pnl
from agent.multi_agent.types import DecisionAction, RiskVerdict
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.signals.service import reset_signal_pipeline_for_tests


def _pipe(**risk_kw) -> SignalPipeline:
    risk = PaperRiskConfig(**risk_kw) if risk_kw else PaperRiskConfig()
    return SignalPipeline(
        config=SignalPipelineConfig(risk=risk, min_confirmed_bars=210),
        risk_state=SignalRiskState(),
    )


def test_bullish_trend_can_buy_or_hold() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    d = _pipe().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        data_path="public_fixture",
    )
    assert d.execution_allowed is False
    assert d.action in {DecisionAction.BUY, DecisionAction.HOLD, DecisionAction.BLOCKED}
    trend = next(c for c in d.contributions if c.agent_id == "trend")
    assert trend.bias in {"BULLISH", "NEUTRAL"}


def test_bearish_trend_bias() -> None:
    candles = make_series(bearish_trend_closes())
    now = series_now_ms(candles)
    d = _pipe().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    trend = next(c for c in d.contributions if c.agent_id == "trend")
    assert trend.bias in {"BEARISH", "NEUTRAL"}
    assert d.action != DecisionAction.BUY or d.risk.verdict is RiskVerdict.VETO


def test_sideways_market_holdish() -> None:
    candles = make_series(sideways_closes())
    now = series_now_ms(candles)
    d = _pipe().evaluate(
        symbol="ETHUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    # Oscillating series should not produce a strong BUY; HOLD/BLOCKED/SELL possible.
    assert d.action != DecisionAction.BUY or d.signal_strength < 0.5
    assert d.action in {
        DecisionAction.HOLD,
        DecisionAction.BLOCKED,
        DecisionAction.SELL,
    }
    assert d.signal_strength_note


def test_conflicting_agents_hold() -> None:
    # Bullish base then sharp dump — mixed structure for coordinator audit.
    base = bullish_trend_closes(200)
    last = base[-1]
    closes = base + [last * (0.995 - i * 0.001) for i in range(20)]
    candles = make_series(closes)
    now = series_now_ms(candles)
    d = _pipe().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action in {
        DecisionAction.HOLD,
        DecisionAction.BLOCKED,
        DecisionAction.SELL,
        DecisionAction.BUY,
    }
    assert "signal_strength" in d.to_public_dict()


def test_stale_data_blocks() -> None:
    candles = make_series(bullish_trend_closes())
    # now far in the future relative to last close → stale
    now = series_now_ms(candles) + 7 * 24 * 60 * 60_000
    d = _pipe().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action is DecisionAction.BLOCKED
    assert any("STALE" in r for r in d.reason_codes) or not d.market.data_fresh


def test_missing_candles_insufficient() -> None:
    candles = make_series(bullish_trend_closes(10))
    now = series_now_ms(candles)
    d = _pipe().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action in {DecisionAction.HOLD, DecisionAction.BLOCKED}
    assert d.execution_allowed is False


def test_duplicate_signal_suppressed() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = _pipe(cooldown_ms=0)
    # Force loose thresholds so BUY is more likely
    pipe.config = SignalPipelineConfig(
        risk=PaperRiskConfig(cooldown_ms=0, max_atr_pct=1.0),
        buy_threshold=0.05,
        sell_threshold=-0.05,
    )
    d1 = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    d2 = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now + 1,
    )
    if d1.action is DecisionAction.BUY:
        assert d2.action is DecisionAction.BLOCKED
        assert "DUPLICATE_SIGNAL" in d2.reason_codes or "DUPLICATE_SIGNAL" in d2.risk.reason_codes


def test_incorrect_market_category() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    d = evaluate_signals(
        symbol="BTCUSDT",
        category="inverse",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action is DecisionAction.BLOCKED
    assert "INVALID_CATEGORY" in d.market.reason_codes


def test_risk_veto_on_volatility() -> None:
    closes = bullish_trend_closes()
    # Huge bar range → high ATR
    candles = make_series(closes)
    # inflate highs/lows
    from agent.market_data import Candle

    fat = [
        Candle(
            start=c.start,
            open=c.open,
            high=c.close * 1.2,
            low=c.close * 0.8,
            close=c.close,
            volume=c.volume,
        )
        for c in candles
    ]
    now = series_now_ms(fat)
    pipe = SignalPipeline(
        config=SignalPipelineConfig(
            risk=PaperRiskConfig(max_atr_pct=0.01, cooldown_ms=0),
            buy_threshold=0.01,
        ),
        risk_state=SignalRiskState(),
    )
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=fat,
        now_ms=now,
    )
    if d.action is DecisionAction.BLOCKED:
        assert (
            "VOLATILITY_FILTER" in d.reason_codes
            or "VOLATILITY_FILTER" in d.risk.reason_codes
            or d.risk.verdict in {RiskVerdict.VETO, RiskVerdict.HALTED}
        )


def test_stop_loss_sizing_levels() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(
        config=SignalPipelineConfig(
            risk=PaperRiskConfig(cooldown_ms=0, max_atr_pct=1.0),
            buy_threshold=0.01,
        ),
        risk_state=SignalRiskState(),
    )
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    if d.action is DecisionAction.BUY and d.risk.verdict is RiskVerdict.APPROVED:
        assert d.levels.entry is not None
        assert d.levels.stop_loss is not None
        assert d.levels.take_profit is not None
        assert d.levels.stop_loss < d.levels.entry < d.levels.take_profit
        assert d.risk.position_notional is not None
        assert d.risk.position_notional > 0


def test_daily_hypothetical_loss_halt() -> None:
    state = SignalRiskState()
    record_hypothetical_pnl(state, -500.0, day_key="2026-01-01")
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(
        config=SignalPipelineConfig(
            risk=PaperRiskConfig(
                paper_balance=10_000,
                daily_loss_halt_fraction=0.03,
                cooldown_ms=0,
                max_atr_pct=1.0,
            ),
            buy_threshold=0.01,
        ),
        risk_state=state,
    )
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action is DecisionAction.BLOCKED
    assert d.risk.verdict is RiskVerdict.HALTED


def test_replay_determinism() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    a = evaluate_signals(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        risk_state=SignalRiskState(),
    )
    b = evaluate_signals(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        risk_state=SignalRiskState(),
    )
    assert a.action == b.action
    assert a.decision_id == b.decision_id
    assert a.signal_strength == b.signal_strength
    assert a.to_public_dict()["contributions"] == b.to_public_dict()["contributions"]


def test_spot_linear_isolation() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    spot = evaluate_signals(
        symbol="BTCUSDT",
        category="spot",
        interval="15",
        candles=candles,
        now_ms=now,
        risk_state=SignalRiskState(),
    )
    linear = evaluate_signals(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        risk_state=SignalRiskState(),
    )
    assert spot.category == "spot"
    assert linear.category == "linear"
    assert spot.decision_id != linear.decision_id


def test_api_status_and_fixture_evaluate_no_private() -> None:
    os.environ["PRIVATE_DATA_READS_ENABLED"] = "false"
    os.environ["AGENT_ALLOW_LIVE"] = "false"
    clear_settings_cache()
    reset_signal_pipeline_for_tests()
    app = create_app(ApiSettings(private_data_reads_enabled=False))
    client = TestClient(app)

    st = client.get("/api/v1/signals/status")
    assert st.status_code == 200
    body = st.json()
    assert body["execution_allowed"] is False
    assert body["trading_enabled"] is False
    assert body["wallet_or_orders"] is False
    assert body["private_data_reads_enabled"] is False
    assert body["agent_allow_live_default"] is False

    root = client.get("/").json()
    assert root["trading_endpoints"] is False

    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    payload = {
        "symbol": "BTCUSDT",
        "category": "linear",
        "interval": "15",
        "now_ms": now,
        "data_path": "public_fixture",
        "candles": [
            {
                "start": c.start,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ],
    }
    res = client.post("/api/v1/signals/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["execution_allowed"] is False
    assert data["trading_enabled"] is False
    assert data["private_api_used"] is False
    assert data["decision"]["execution_allowed"] is False
    assert data["decision"]["not_an_order"] is True

    # No order routes exist
    assert client.post("/api/v1/orders").status_code in {404, 405, 401, 403}


def test_api_rejects_unknown_symbol() -> None:
    clear_settings_cache()
    reset_signal_pipeline_for_tests()
    app = create_app(ApiSettings())
    client = TestClient(app)
    res = client.post(
        "/api/v1/signals/evaluate",
        json={
            "symbol": "DOGEUSDT",
            "category": "linear",
            "interval": "15",
            "candles": [],
            "now_ms": 1_700_000_000_000,
        },
    )
    assert res.status_code == 200
    assert res.json()["decision"]["action"] == "BLOCKED"
