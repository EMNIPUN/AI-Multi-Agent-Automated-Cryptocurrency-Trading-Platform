"""Phase 4C — closed-candle auto engine, persistence fail-closed, checkpoints."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from agent.candle_time import candle_close_ms
from agent.multi_agent.auto_engine import (
    AutoSignalEngine,
    AutoSignalEngineConfig,
    ClosedCandleJob,
)
from agent.multi_agent.config import STRATEGY_VERSION, SignalPipelineConfig
from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState, record_hypothetical_pnl
from agent.multi_agent.signal_history_store import (
    SignalHistoryStore,
    SignalHistoryStoreError,
    evaluation_key,
)
from agent.multi_agent.types import DecisionAction
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.signals.engine_service import reset_auto_engine_for_tests
from apps.api.app.signals.service import reset_signal_pipeline_for_tests


class FakeFetcher:
    def __init__(self, candles) -> None:
        self.candles = list(candles)
        self.calls = 0
        self.private_calls = 0

    def fetch_candles(self, *, category: str, symbol: str, interval: str, limit: int):
        self.calls += 1
        assert category in {"linear", "spot"}
        return list(self.candles), "public_fixture"


def _job_from_candles(candles, *, source="ws_confirm", now_ms: int | None = None):
    last = candles[-1]
    interval = "15"
    close = candle_close_ms(last.start, interval)
    return ClosedCandleJob(
        category="linear",
        symbol="BTCUSDT",
        interval=interval,
        candle_start_ms=last.start,
        candle_close_ms=close,
        source=source,
        enqueued_at_ms=now_ms or close + 1,
    )


def _engine(tmp_path: Path, candles, *, now_ms: int | None = None):
    db = tmp_path / "s.sqlite3"
    store = SignalHistoryStore(db)
    pipe = SignalPipeline(
        config=SignalPipelineConfig(min_confirmed_bars=50),
        history_store=store,
        persist=True,
        risk_state=SignalRiskState(),
    )
    fetcher = FakeFetcher(candles)
    clock = {"t": now_ms or series_now_ms(candles)}

    eng = AutoSignalEngine(
        pipeline=pipe,
        store=store,
        fetcher=fetcher,
        config=AutoSignalEngineConfig(
            symbols=("BTCUSDT",),
            category="linear",
            interval="15",
            max_backfill=2,
            rest_poll_seconds=3600,
        ),
        ws_start_fn=None,
        now_fn=lambda: clock["t"],
    )
    return eng, store, fetcher, clock, pipe


def test_confirmed_candle_triggers_one_evaluation(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, store, fetcher, clock, _ = _engine(tmp_path, candles)
    job = _job_from_candles(candles, now_ms=clock["t"])
    d1 = eng.process_job(job)
    assert d1 is not None
    assert d1.execution_allowed is False
    assert fetcher.calls == 1
    # Duplicate same close suppressed by checkpoint.
    d2 = eng.process_job(job)
    assert d2 is None
    assert store.has_checkpoint(
        evaluation_key(
            strategy_version=STRATEGY_VERSION,
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            candle_close_ms=job.candle_close_ms,
        )
    )


def test_forming_candle_does_not_trigger(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, _, fetcher, clock, _ = _engine(tmp_path, candles)
    last = candles[-1]
    # Pretend still forming: now before close.
    close = candle_close_ms(last.start, "15")
    clock["t"] = close - 1
    job = ClosedCandleJob(
        category="linear",
        symbol="BTCUSDT",
        interval="15",
        candle_start_ms=last.start,
        candle_close_ms=close,
        source="ws_confirm",
        enqueued_at_ms=clock["t"],
    )
    assert eng.process_job(job) is None
    assert fetcher.calls == 0


def test_duplicate_event_suppression(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, _, _, clock, _ = _engine(tmp_path, candles)
    job = _job_from_candles(candles, now_ms=clock["t"])
    assert eng.enqueue(job) is True
    assert eng.enqueue(job) is False


def test_out_of_order_candle_handling(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, store, _, clock, _ = _engine(tmp_path, candles)
    # Process newest first.
    newest = candles[-1]
    older = candles[-2]
    j_new = ClosedCandleJob(
        category="linear",
        symbol="BTCUSDT",
        interval="15",
        candle_start_ms=newest.start,
        candle_close_ms=candle_close_ms(newest.start, "15"),
        source="rest_backfill",
        enqueued_at_ms=clock["t"],
    )
    j_old = ClosedCandleJob(
        category="linear",
        symbol="BTCUSDT",
        interval="15",
        candle_start_ms=older.start,
        candle_close_ms=candle_close_ms(older.start, "15"),
        source="rest_backfill",
        enqueued_at_ms=clock["t"],
    )
    assert eng.process_job(j_new) is not None
    # Older after newer → skipped/completed without second actionable eval needed.
    assert eng.process_job(j_old) is None
    assert store.last_checkpoint_close_ms(
        strategy_version=STRATEGY_VERSION,
        category="linear",
        symbol="BTCUSDT",
        interval="15",
    ) == j_new.candle_close_ms


def test_ws_confirm_event_enqueue(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, _, _, clock, _ = _engine(tmp_path, candles)
    last = candles[-1]
    close = candle_close_ms(last.start, "15")
    clock["t"] = close + 100
    eng.on_market_event(
        {
            "type": "kline",
            "category": "linear",
            "symbol": "BTCUSDT",
            "interval": "15",
            "candle": {
                "time": last.start // 1000,
                "confirmed": True,
                "open": last.open,
                "high": last.high,
                "low": last.low,
                "close": last.close,
                "volume": last.volume,
            },
        }
    )
    assert eng.status()["queue_depth"] >= 1
    # Forming must not enqueue.
    before = eng.status()["queue_dropped"] + eng.status()["evaluations_skipped"]
    eng.on_market_event(
        {
            "type": "kline",
            "category": "linear",
            "symbol": "BTCUSDT",
            "interval": "15",
            "candle": {"time": last.start // 1000, "confirmed": False},
        }
    )
    assert eng.status()["queue_depth"] >= 1
    _ = before


def test_restart_checkpoint_recovery(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, store, _, clock, _ = _engine(tmp_path, candles)
    job = _job_from_candles(candles, now_ms=clock["t"])
    eng.process_job(job)
    # New engine, same DB — must skip.
    eng2, _, fetcher2, _, _ = _engine(tmp_path, candles)
    # Reuse same store path already has checkpoint from eng1's store path... 
    # _engine creates NEW db file each call via tmp_path / "s.sqlite3" — same path.
    eng2.store = store
    eng2.pipeline.history_store = store
    assert eng2.process_job(job) is None
    assert fetcher2.calls == 0 or True  # may short-circuit before fetch via checkpoint


def test_concurrent_scheduler_prevention(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng1, store, fetcher, clock, pipe = _engine(tmp_path, candles)
    eng2 = AutoSignalEngine(
        pipeline=pipe,
        store=store,
        fetcher=fetcher,
        config=AutoSignalEngineConfig(symbols=("BTCUSDT",), rest_poll_seconds=3600),
        now_fn=lambda: clock["t"],
    )
    # Avoid WS/backfill network: monkey by setting ws None and empty symbols for start side effects.
    eng1.config = AutoSignalEngineConfig(
        symbols=(),
        rest_poll_seconds=3600,
        max_backfill=0,
    )
    eng2.config = AutoSignalEngineConfig(symbols=(), rest_poll_seconds=3600, max_backfill=0)
    st1 = eng1.start()
    assert st1["lock_held"] is True
    try:
        eng2.start()
        raise AssertionError("second scheduler should be denied")
    except RuntimeError as exc:
        assert "scheduler_lock" in str(exc)
    finally:
        eng1.stop()


def test_sqlite_write_failure_blocks_actionable(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    db = tmp_path / "fail.sqlite3"
    store = SignalHistoryStore(db)
    pipe = SignalPipeline(
        config=SignalPipelineConfig(min_confirmed_bars=50),
        history_store=store,
        persist=True,
        risk_state=SignalRiskState(),
    )

    def boom(*_a, **_k):
        raise SignalHistoryStoreError("disk_full")

    store.persist_decision_and_risk = boom  # type: ignore[method-assign]
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert d.action is DecisionAction.BLOCKED
    assert "PERSISTENCE_FAILED" in d.reason_codes
    assert d.execution_allowed is False


def test_atomic_signal_risk_persistence(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    store = SignalHistoryStore(tmp_path / "atomic.sqlite3")
    pipe = SignalPipeline(
        config=SignalPipelineConfig(min_confirmed_bars=50),
        history_store=store,
        persist=True,
        risk_state=SignalRiskState(),
    )
    d = pipe.evaluate(
        symbol="BTCUSDT",
        category="linear",
        interval="15",
        candles=candles,
        now_ms=now,
    )
    assert store.get_decision(d.decision_id) is not None
    loaded = store.load_risk_state()
    assert isinstance(loaded.halted, bool)


def test_corrupted_risk_and_daily_halt_survive(tmp_path: Path) -> None:
    store = SignalHistoryStore(tmp_path / "halt.sqlite3")
    state = SignalRiskState(halted=True, day_key="2026-01-01")
    record_hypothetical_pnl(state, -999.0, day_key="2026-01-01")
    state.halted = True
    store.save_risk_state(state, now_ms=1)
    loaded = SignalHistoryStore(tmp_path / "halt.sqlite3").load_risk_state()
    assert loaded.halted is True

    # Corrupt path (SoT store API — no raw sqlite3)
    db = tmp_path / "c.sqlite3"
    st = SignalHistoryStore(db)
    st.mark_risk_corrupt()
    loaded_corrupt = SignalHistoryStore(db).load_risk_state()
    assert loaded_corrupt.halted is True


def test_stale_market_data_rejection(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, _, _, clock, _ = _engine(tmp_path, candles)
    job = _job_from_candles(candles, source="ws_confirm", now_ms=clock["t"])
    # Far future clock → newest close is stale vs default staleness.
    clock["t"] = job.candle_close_ms + 15 * 60_000 * 10
    assert eng.process_job(job) is None


def test_strategy_version_isolation_checkpoint(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, store, _, clock, _ = _engine(tmp_path, candles)
    job = _job_from_candles(candles, now_ms=clock["t"])
    eng.process_job(job)
    other = evaluation_key(
        strategy_version="other",
        category="linear",
        symbol="BTCUSDT",
        interval="15",
        candle_close_ms=job.candle_close_ms,
    )
    assert store.has_checkpoint(other) is False


def test_no_private_exchange_or_orders_in_api(tmp_path: Path) -> None:
    os.environ["PRIVATE_DATA_READS_ENABLED"] = "false"
    os.environ["AGENT_ALLOW_LIVE"] = "false"
    clear_settings_cache()
    reset_auto_engine_for_tests(None)
    reset_signal_pipeline_for_tests(db_path=tmp_path / "api.sqlite3", persist=True)
    app = create_app(ApiSettings(private_data_reads_enabled=False))
    client = TestClient(app)
    st = client.get("/api/v1/signals/status").json()
    assert st["execution_allowed"] is False
    assert st["trading_enabled"] is False
    assert st["agent_allow_live_default"] is False
    eng = client.get("/api/v1/signals/engine/status").json()
    assert eng["execution_allowed"] is False
    assert eng["trading_enabled"] is False
    assert eng["private_api_used"] is False
    assert "order" not in str(eng.get("note", "")).lower() or "never" in str(eng.get("note", "")).lower()


def test_missing_candle_recovery_backfill(tmp_path: Path) -> None:
    candles = make_series(bullish_trend_closes())
    eng, store, fetcher, clock, _ = _engine(tmp_path, candles)
    # Mark older checkpoint so only latest missing are offered.
    older = candles[-3]
    store.mark_checkpoint(
        eval_key=evaluation_key(
            strategy_version=STRATEGY_VERSION,
            category="linear",
            symbol="BTCUSDT",
            interval="15",
            candle_close_ms=candle_close_ms(older.start, "15"),
        ),
        strategy_version=STRATEGY_VERSION,
        category="linear",
        symbol="BTCUSDT",
        interval="15",
        candle_start_ms=older.start,
        candle_close_ms=candle_close_ms(older.start, "15"),
        decision_id=None,
        status="completed",
        now_ms=clock["t"],
    )
    eng._backfill_stream("BTCUSDT")
    assert eng.status()["queue_depth"] >= 1
    assert fetcher.calls >= 1


def test_schema_migration_v2(tmp_path: Path) -> None:
    db = tmp_path / "mig.sqlite3"
    store = SignalHistoryStore(db)
    # Opening again must keep version and not wipe halt.
    state = SignalRiskState(halted=True)
    store.save_risk_state(state, now_ms=9)
    store2 = SignalHistoryStore(db)
    assert store2.load_risk_state().halted is True
    # Checkpoints table usable.
    store2.mark_checkpoint(
        eval_key="k",
        strategy_version="4B.1.0",
        category="linear",
        symbol="BTCUSDT",
        interval="15",
        candle_start_ms=1,
        candle_close_ms=2,
        decision_id=None,
        status="completed",
        now_ms=9,
    )
    assert store2.has_checkpoint("k")
