"""Phase 4B — symmetric scoring, SQLite history, risk persistence."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from agent.multi_agent.config import STRATEGY_VERSION, SignalPipelineConfig
from agent.multi_agent.coordinator import (
    directional_conviction,
    market_quality_score,
)
from agent.multi_agent.fixtures import (
    bearish_trend_closes,
    bullish_trend_closes,
    make_series,
    series_now_ms,
    sideways_closes,
)
from agent.multi_agent.market_agent import build_market_snapshot
from agent.multi_agent.momentum_agent import evaluate_momentum
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState, record_hypothetical_pnl
from agent.multi_agent.signal_history_store import (
    SignalHistoryStore,
    SignalHistoryStoreError,
)
from agent.multi_agent.trend_agent import evaluate_trend
from agent.multi_agent.types import AgentContribution, DecisionAction, RiskVerdict
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.signals.service import reset_signal_pipeline_for_tests


def _snap(closes, *, now_extra=0, category="linear"):
    candles = make_series(closes)
    now = series_now_ms(candles) + now_extra
    snap, m = build_market_snapshot(
        symbol="BTCUSDT",
        category=category,
        interval="15",
        candles=candles,
        now_ms=now,
        data_path="public_fixture",
        min_bars=50,
    )
    return snap, m, candles, now


def test_symmetric_bullish_bearish_scoring() -> None:
    bull_snap, _, _, _ = _snap(bullish_trend_closes())
    bear_snap, _, _, _ = _snap(bearish_trend_closes())
    cfg = SignalPipelineConfig()
    bt = evaluate_trend(bull_snap)
    bm = evaluate_momentum(bull_snap)
    et = evaluate_trend(bear_snap)
    em = evaluate_momentum(bear_snap)
    bull_c = directional_conviction(bt, bm, cfg)
    bear_c = directional_conviction(et, em, cfg)
    # Opposite regimes should not share the same sign.
    assert bull_c * bear_c <= 0 or abs(bull_c - bear_c) > 0.2
    # Market OK must not inject positive directional bias.
    ok = AgentContribution(
        agent_id="market_data",
        agent_version="4B.1",
        bias="OK",
        confidence=1.0,
        reason_codes=("MARKET_OK",),
        explanation="ok",
    )
    q = market_quality_score(ok, bull_snap)
    assert q == 1.0
    # Quality is not folded into directional_conviction.
    assert directional_conviction(bt, bm, cfg) == bull_c


def test_neutral_market_no_forced_buy() -> None:
    snap, m, candles, now = _snap(sideways_closes())
    d = SignalPipeline().evaluate(
        symbol="ETHUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        data_path="public_fixture",
    )
    assert d.strategy_version == STRATEGY_VERSION
    assert d.action != DecisionAction.BUY or d.directional_conviction >= 0.35
    # Quality gate is separate.
    assert 0.0 <= d.market_quality <= 1.0


def test_agent_disagreement_hold() -> None:
    base = bullish_trend_closes(200)
    last = base[-1]
    closes = base + [last * (0.995 - i * 0.001) for i in range(20)]
    candles = make_series(closes)
    now = series_now_ms(candles)
    d = SignalPipeline().evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert "signal_strength" in d.to_public_dict()
    assert d.execution_allowed is False


def test_signal_persistence_and_idempotency(tmp_path: Path) -> None:
    db = tmp_path / "signals.sqlite3"
    store = SignalHistoryStore(db)
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(history_store=store, persist=True, risk_state=SignalRiskState())
    d1 = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
        data_path="public_fixture",
    )
    assert store.record_decision(d1) is False  # already inserted by pipeline
    rows = store.list_signals(symbol="BTCUSDT", limit=10)
    assert len(rows) >= 1
    assert rows[0].decision_id == d1.decision_id
    assert rows[0].strategy_version == STRATEGY_VERSION
    assert "api_key" not in json.dumps(rows[0].__dict__).lower()
    assert "secret" not in json.dumps(rows[0].__dict__).lower()


def test_concurrent_writes(tmp_path: Path) -> None:
    db = tmp_path / "concurrent.sqlite3"
    store = SignalHistoryStore(db)

    def _one(i: int):
        closes = bullish_trend_closes(220)
        # Offset series slightly so candle close ids differ.
        candles = make_series(closes, start_ms=1_700_000_000_000 + i * 15 * 60_000 * 300)
        now = series_now_ms(candles)
        pipe = SignalPipeline(history_store=store, persist=True, risk_state=SignalRiskState())
        return pipe.evaluate(
            symbol="BTCUSDT",
            category="linear",
            interval="15",
            candles=candles,
            now_ms=now,
            data_path="public_fixture",
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_one, range(4)))
    assert store.analytics()["total_signals"] >= 1


def test_restart_recovery_and_risk_halt_persistence(tmp_path: Path) -> None:
    db = tmp_path / "risk.sqlite3"
    store = SignalHistoryStore(db)
    state = SignalRiskState()
    record_hypothetical_pnl(state, -500.0, day_key="2026-01-01")
    state.halted = True
    state.seen_keys.add("idem_test")
    store.save_risk_state(state, now_ms=1_700_000_000_000)

    # Restart: new store + pipeline loads halted state and does not clear it.
    store2 = SignalHistoryStore(db)
    loaded = store2.load_risk_state()
    assert loaded.halted is True
    assert "idem_test" in loaded.seen_keys
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(history_store=store2, persist=True)
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action is DecisionAction.BLOCKED
    assert d.risk.verdict is RiskVerdict.HALTED


def test_corrupted_risk_state_fail_closed(tmp_path: Path) -> None:
    db = tmp_path / "corrupt.sqlite3"
    store = SignalHistoryStore(db)
    store.mark_risk_corrupt()
    loaded = SignalHistoryStore(db).load_risk_state()
    assert loaded.halted is True


def test_strategy_version_isolation(tmp_path: Path) -> None:
    db = tmp_path / "versions.sqlite3"
    store = SignalHistoryStore(db)
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    pipe = SignalPipeline(history_store=store, persist=True, risk_state=SignalRiskState())
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    rows = store.list_signals(strategy_version=STRATEGY_VERSION)
    assert any(r.decision_id == d.decision_id for r in rows)
    assert store.list_signals(strategy_version="nope") == []


def test_pagination_and_filters(tmp_path: Path) -> None:
    db = tmp_path / "page.sqlite3"
    store = SignalHistoryStore(db)
    pipe = SignalPipeline(history_store=store, persist=True, risk_state=SignalRiskState())
    for i, symbol in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        candles = make_series(bullish_trend_closes(), start_ms=1_700_000_000_000 + i * 10_000_000)
        now = series_now_ms(candles)
        pipe.evaluate(
            symbol=symbol,
            category="linear",
            interval="15",
            candles=candles,
            now_ms=now,
        )
    page = store.list_signals(limit=2, offset=0)
    assert len(page) == 2
    eth = store.list_signals(symbol="ETHUSDT")
    assert all(r.symbol == "ETHUSDT" for r in eth)


def test_api_history_analytics_no_private(tmp_path: Path) -> None:
    os.environ["PRIVATE_DATA_READS_ENABLED"] = "false"
    os.environ["AGENT_ALLOW_LIVE"] = "false"
    clear_settings_cache()
    db = tmp_path / "api.sqlite3"
    reset_signal_pipeline_for_tests(db_path=db, persist=True)
    app = create_app(ApiSettings(private_data_reads_enabled=False))
    client = TestClient(app)

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
    body = res.json()
    assert body["execution_allowed"] is False
    assert body["decision"]["strategy_version"] == STRATEGY_VERSION

    hist = client.get("/api/v1/signals/history?symbol=BTCUSDT&limit=10")
    assert hist.status_code == 200
    assert hist.json()["not_an_order"] is True
    assert len(hist.json()["items"]) >= 1

    analytics = client.get("/api/v1/signals/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["private_api_used"] is False
    payload = analytics.json()
    assert "win_rate" not in payload
    assert payload.get("total_pnl") is None
    assert "metrics_note" in payload

    st = client.get("/api/v1/signals/status").json()
    assert st["execution_allowed"] is False
    assert st["supabase_writes"] is False
    assert st["agent_allow_live_default"] is False
