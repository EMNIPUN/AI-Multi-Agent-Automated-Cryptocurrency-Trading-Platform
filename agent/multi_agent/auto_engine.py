"""
Phase 4C — automatic closed-candle signal engine (signals only).

Watches public market confirms, evaluates via SignalPipeline, persists durably.
Never places orders or uses private exchange APIs.
"""

from __future__ import annotations

import logging
import os
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol

from agent.candle_time import candle_close_ms, default_staleness_ms, is_candle_confirmed
from agent.confirmed_candles import CandleFilterReject, filter_confirmed_candles
from agent.market_data import Candle
from agent.multi_agent.config import STRATEGY_VERSION, SignalPipelineConfig
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.signal_history_store import (
    CheckpointWrite,
    SignalHistoryStore,
    SignalHistoryStoreError,
    evaluation_key,
)
from agent.multi_agent.types import CoordinatorDecision, DecisionAction

logger = logging.getLogger(__name__)

AUTO_ENGINE_VERSION = "4C.1.0"
QUEUE_MAX = 64
MAX_BACKFILL_CANDLES = 3
LEASE_MS = 30_000
LEASE_RENEW_EVERY_S = 10.0
REST_POLL_EVERY_S = 20.0
MAX_RETRIES = 3
RETRY_BACKOFF_S = (0.5, 1.0, 2.0)


class EngineState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ClosedCandleJob:
    category: str
    symbol: str
    interval: str
    candle_start_ms: int
    candle_close_ms: int
    source: str  # ws_confirm | rest_backfill | rest_poll
    enqueued_at_ms: int


@dataclass
class EngineStatus:
    state: str = EngineState.STOPPED.value
    engine_version: str = AUTO_ENGINE_VERSION
    strategy_version: str = STRATEGY_VERSION
    owner_id: str | None = None
    lock_held: bool = False
    symbols: list[str] = field(default_factory=list)
    category: str = "linear"
    interval: str = "15"
    queue_depth: int = 0
    queue_dropped: int = 0
    last_error: str | None = None
    last_evaluated: dict[str, Any] | None = None
    last_persisted_signal: dict[str, Any] | None = None
    last_candle: dict[str, Any] | None = None
    data_freshness_ms: int | None = None
    processing_lag_ms: int | None = None
    evaluations_ok: int = 0
    evaluations_skipped: int = 0
    evaluations_failed: int = 0
    trading_enabled: bool = False
    execution_allowed: bool = False
    private_api_used: bool = False
    note: str = "Automatic SIGNAL evaluation only — never automatic trading"


class KlineFetcher(Protocol):
    def fetch_candles(
        self, *, category: str, symbol: str, interval: str, limit: int
    ) -> tuple[list[Candle], str]: ...


class RestKlineFetcher:
    """Public REST only — injected BybitPublicRestClient wrapper."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def fetch_candles(
        self, *, category: str, symbol: str, interval: str, limit: int
    ) -> tuple[list[Candle], str]:
        from apps.api.app.market_data.schemas import MarketCategory

        cat = MarketCategory(category)
        kl = self._client.get_klines(
            category=cat, symbol=symbol.upper(), interval=interval, limit=limit
        )
        candles = [
            Candle(
                start=int(b.time) * 1000,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
            for b in kl.candles
        ]
        return candles, str(kl.data_path or "public_rest_only")


@dataclass
class AutoSignalEngineConfig:
    symbols: tuple[str, ...] = ("BTCUSDT",)
    category: str = "linear"
    interval: str = "15"
    strategy_version: str = STRATEGY_VERSION
    max_backfill: int = MAX_BACKFILL_CANDLES
    queue_max: int = QUEUE_MAX
    rest_poll_seconds: float = REST_POLL_EVERY_S
    enabled_on_start: bool = False


class AutoSignalEngine:
    """
    Single-writer closed-candle evaluator.

    Concurrency: SQLite scheduler_lock lease + in-process guard.
    """

    def __init__(
        self,
        *,
        pipeline: SignalPipeline,
        store: SignalHistoryStore,
        fetcher: KlineFetcher,
        config: AutoSignalEngineConfig | None = None,
        ws_start_fn: Callable[[Callable[[dict[str, Any]], None]], Callable[[], None]]
        | None = None,
        now_fn: Callable[[], int] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.store = store
        self.fetcher = fetcher
        self.config = config or AutoSignalEngineConfig()
        self._ws_start_fn = ws_start_fn
        self._now = now_fn or (lambda: int(time.time() * 1000))
        self._owner_id = f"eng-{uuid.uuid4().hex[:12]}"
        self._hostname = socket.gethostname()[:64]
        self._pid = os.getpid()
        self._state = EngineState.STOPPED
        self._queue: queue.Queue[ClosedCandleJob | None] = queue.Queue(
            maxsize=self.config.queue_max
        )
        self._status = EngineStatus(
            symbols=list(self.config.symbols),
            category=self.config.category,
            interval=self.config.interval,
            strategy_version=self.config.strategy_version,
            owner_id=self._owner_id,
        )
        self._worker: threading.Thread | None = None
        self._lease_thread: threading.Thread | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ws_stop: Callable[[], None] | None = None
        self._lock = threading.RLock()
        self._seen_job_keys: set[str] = set()

    def status(self) -> dict[str, Any]:
        with self._lock:
            st = self._status
            st.state = self._state.value
            st.queue_depth = self._queue.qsize()
            st.owner_id = self._owner_id
            return {
                "state": st.state,
                "engine_version": st.engine_version,
                "strategy_version": st.strategy_version,
                "owner_id": st.owner_id,
                "lock_held": st.lock_held,
                "symbols": list(st.symbols),
                "category": st.category,
                "interval": st.interval,
                "queue_depth": st.queue_depth,
                "queue_dropped": st.queue_dropped,
                "last_error": st.last_error,
                "last_evaluated": st.last_evaluated,
                "last_persisted_signal": st.last_persisted_signal,
                "last_candle": st.last_candle,
                "data_freshness_ms": st.data_freshness_ms,
                "processing_lag_ms": st.processing_lag_ms,
                "evaluations_ok": st.evaluations_ok,
                "evaluations_skipped": st.evaluations_skipped,
                "evaluations_failed": st.evaluations_failed,
                "trading_enabled": False,
                "execution_allowed": False,
                "private_api_used": False,
                "not_automatic_trading": True,
                "note": st.note,
                "audit": self.store.recent_audit(limit=10),
                "db_path": str(self.store.db_path),
            }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._state in {EngineState.RUNNING, EngineState.STARTING, EngineState.DEGRADED}:
                return self.status()
            self._state = EngineState.STARTING
            self._stop.clear()
        now_ms = self._now()
        try:
            acquired = self.store.try_acquire_scheduler_lock(
                owner_id=self._owner_id,
                hostname=self._hostname,
                pid=self._pid,
                now_ms=now_ms,
                lease_ms=LEASE_MS,
            )
        except SignalHistoryStoreError as exc:
            with self._lock:
                self._state = EngineState.STOPPED
                self._status.last_error = f"lock_acquire:{exc}"
            raise
        if not acquired:
            with self._lock:
                self._state = EngineState.STOPPED
                self._status.lock_held = False
                self._status.last_error = "scheduler_lock_held_by_another_process"
            self.store.write_audit(
                "lock_denied",
                {"owner_id": self._owner_id},
                now_ms=now_ms,
            )
            raise RuntimeError("scheduler_lock_held_by_another_process")

        with self._lock:
            self._status.lock_held = True
            self._status.last_error = None

        self.store.write_audit(
            "engine_start",
            {
                "owner_id": self._owner_id,
                "symbols": list(self.config.symbols),
                "interval": self.config.interval,
                "category": self.config.category,
            },
            now_ms=now_ms,
        )

        self._worker = threading.Thread(
            target=self._worker_loop, name="signal-auto-worker", daemon=True
        )
        self._lease_thread = threading.Thread(
            target=self._lease_loop, name="signal-auto-lease", daemon=True
        )
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="signal-auto-poll", daemon=True
        )
        self._worker.start()
        self._lease_thread.start()
        self._poll_thread.start()

        if self._ws_start_fn is not None:
            try:
                self._ws_stop = self._ws_start_fn(self.on_market_event)
            except Exception as exc:  # noqa: BLE001
                self._set_degraded(f"ws_start_failed:{type(exc).__name__}")

        # Bounded backfill for each stream.
        for sym in self.config.symbols:
            try:
                self._backfill_stream(sym)
            except Exception as exc:  # noqa: BLE001
                self._set_degraded(f"backfill:{type(exc).__name__}")

        with self._lock:
            if self._state != EngineState.DEGRADED:
                self._state = EngineState.RUNNING
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._state is EngineState.STOPPED:
                return self.status()
            self._state = EngineState.STOPPING
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._ws_stop is not None:
            try:
                self._ws_stop()
            except Exception:  # noqa: BLE001
                pass
            self._ws_stop = None
        for t in (self._worker, self._lease_thread, self._poll_thread):
            if t is not None and t.is_alive():
                t.join(timeout=5.0)
        now_ms = self._now()
        try:
            self.store.release_scheduler_lock(owner_id=self._owner_id, now_ms=now_ms)
            self.store.write_audit(
                "engine_stop", {"owner_id": self._owner_id}, now_ms=now_ms
            )
        except SignalHistoryStoreError:
            pass
        with self._lock:
            self._status.lock_held = False
            self._state = EngineState.STOPPED
            self._worker = None
            self._lease_thread = None
            self._poll_thread = None
        return self.status()

    def on_market_event(self, event: dict[str, Any]) -> None:
        """WS hub / manager callback — only confirmed klines enqueue work."""
        if self._stop.is_set():
            return
        if event.get("type") != "kline":
            return
        candle = event.get("candle") or {}
        if not isinstance(candle, dict):
            return
        if not bool(candle.get("confirmed")):
            return
        category = str(event.get("category") or self.config.category)
        symbol = str(event.get("symbol") or "").upper()
        interval = str(event.get("interval") or self.config.interval)
        if symbol not in self.config.symbols:
            return
        if interval != self.config.interval:
            return
        if category != self.config.category:
            return
        try:
            start_ms = int(candle.get("time") or candle.get("start") or 0)
            if start_ms < 1_000_000_000_000:
                start_ms *= 1000
        except (TypeError, ValueError):
            return
        if start_ms <= 0:
            return
        close_ms = candle_close_ms(start_ms, interval)
        now_ms = self._now()
        if not is_candle_confirmed(start_ms, interval, now_ms=now_ms, grace_ms=0):
            # Exchange confirm flag present but local clock not past close — skip.
            return
        self.enqueue(
            ClosedCandleJob(
                category=category,
                symbol=symbol,
                interval=interval,
                candle_start_ms=start_ms,
                candle_close_ms=close_ms,
                source="ws_confirm",
                enqueued_at_ms=now_ms,
            )
        )

    def enqueue(self, job: ClosedCandleJob) -> bool:
        key = evaluation_key(
            strategy_version=self.config.strategy_version,
            category=job.category,
            symbol=job.symbol,
            interval=job.interval,
            candle_close_ms=job.candle_close_ms,
        )
        with self._lock:
            if key in self._seen_job_keys:
                self._status.evaluations_skipped += 1
                return False
            # Bound in-memory dedupe set.
            if len(self._seen_job_keys) > 2000:
                self._seen_job_keys = set(list(self._seen_job_keys)[-500:])
            self._seen_job_keys.add(key)
        try:
            self._queue.put_nowait(job)
            return True
        except queue.Full:
            with self._lock:
                self._status.queue_dropped += 1
                self._status.last_error = "queue_full_backpressure"
            # Allow retry later — remove from seen so REST poll can re-offer.
            with self._lock:
                self._seen_job_keys.discard(key)
            return False

    def process_job(self, job: ClosedCandleJob) -> CoordinatorDecision | None:
        """Synchronously evaluate one closed candle (tests + worker)."""
        now_ms = self._now()
        ekey = evaluation_key(
            strategy_version=self.config.strategy_version,
            category=job.category,
            symbol=job.symbol,
            interval=job.interval,
            candle_close_ms=job.candle_close_ms,
        )
        if self.store.has_checkpoint(ekey):
            with self._lock:
                self._status.evaluations_skipped += 1
            return None

        # Reject incomplete / not-yet-closed.
        if not is_candle_confirmed(
            job.candle_start_ms, job.interval, now_ms=now_ms, grace_ms=0
        ):
            return None

        # Stale rejection: if close is older than staleness window relative to now
        # AND we are not backfilling intentionally — still allow backfill within max.
        lag = now_ms - job.candle_close_ms
        with self._lock:
            self._status.processing_lag_ms = max(0, lag)
            self._status.last_candle = {
                "symbol": job.symbol,
                "interval": job.interval,
                "candle_start_ms": job.candle_start_ms,
                "candle_close_ms": job.candle_close_ms,
                "source": job.source,
            }

        last_err: Exception | None = None
        for attempt, delay in enumerate((0.0, *RETRY_BACKOFF_S[: MAX_RETRIES - 1])):
            if delay:
                time.sleep(delay)
            try:
                candles, data_path = self.fetcher.fetch_candles(
                    category=job.category,
                    symbol=job.symbol,
                    interval=job.interval,
                    limit=250,
                )
                filtered = filter_confirmed_candles(
                    candles, interval=job.interval, now_ms=now_ms, grace_ms=0
                )
                if isinstance(filtered, CandleFilterReject) or not filtered.candles:
                    raise SignalHistoryStoreError("no_confirmed_candles")
                confirmed = filtered.candles
                # Ensure target close exists and is the latest we intend.
                newest = confirmed[-1]
                newest_close = candle_close_ms(newest.start, job.interval)
                if newest_close < job.candle_close_ms:
                    raise SignalHistoryStoreError("target_candle_missing")
                # If REST returned newer bars, still evaluate — pipeline uses newest confirmed.
                # Out-of-order older jobs: if already past checkpoint of a newer close, skip.
                last_cp = self.store.last_checkpoint_close_ms(
                    strategy_version=self.config.strategy_version,
                    category=job.category,
                    symbol=job.symbol,
                    interval=job.interval,
                )
                if last_cp is not None and job.candle_close_ms < last_cp:
                    # Out-of-order older candle after newer processed — skip safely.
                    self.store.mark_checkpoint(
                        eval_key=ekey,
                        strategy_version=self.config.strategy_version,
                        category=job.category,
                        symbol=job.symbol,
                        interval=job.interval,
                        candle_start_ms=job.candle_start_ms,
                        candle_close_ms=job.candle_close_ms,
                        decision_id=None,
                        status="completed",
                        now_ms=now_ms,
                    )
                    with self._lock:
                        self._status.evaluations_skipped += 1
                    return None

                # Stale market data relative to interval.
                stale_lim = default_staleness_ms(job.interval)
                if now_ms - newest_close > stale_lim and job.source == "ws_confirm":
                    raise SignalHistoryStoreError("stale_market_data")

                decision = self.pipeline.evaluate(
                    symbol=job.symbol,
                    category=job.category,
                    interval=job.interval,
                    candles=confirmed,
                    now_ms=now_ms,
                    data_path=data_path if job.source.startswith("rest") else "public_ws_confirm",
                    checkpoint=CheckpointWrite(
                        eval_key=ekey,
                        strategy_version=self.config.strategy_version,
                        category=job.category,
                        symbol=job.symbol,
                        interval=job.interval,
                        candle_start_ms=job.candle_start_ms,
                        candle_close_ms=job.candle_close_ms,
                        decision_id=None,  # filled in same TX from decision.decision_id
                        status="completed",
                    ),
                )
                # Only advance checkpoint after durable evaluate path.
                # Pipeline require_persist converts BUY/SELL to BLOCKED on write failure.
                if "PERSISTENCE_FAILED" in decision.reason_codes:
                    raise SignalHistoryStoreError("pipeline_persist_failed")
                with self._lock:
                    self._status.evaluations_ok += 1
                    self._status.data_freshness_ms = max(0, now_ms - newest_close)
                    self._status.last_evaluated = {
                        "eval_key": ekey,
                        "decision_id": decision.decision_id,
                        "action": decision.action.value,
                        "at_ms": now_ms,
                    }
                    if decision.action is not DecisionAction.BLOCKED or (
                        "PERSISTENCE_FAILED" not in decision.reason_codes
                    ):
                        self._status.last_persisted_signal = {
                            "decision_id": decision.decision_id,
                            "action": decision.action.value,
                            "symbol": decision.symbol,
                            "signal_strength": decision.signal_strength,
                            "strategy_version": decision.strategy_version,
                            "source_mode": decision.source_mode,
                            "timestamp_ms": decision.timestamp_ms,
                        }
                    self._status.last_error = None
                    if self._state is EngineState.DEGRADED:
                        self._state = EngineState.RUNNING
                self.store.write_audit(
                    "evaluated",
                    {
                        "eval_key": ekey,
                        "action": decision.action.value,
                        "decision_id": decision.decision_id,
                        "source": job.source,
                        "attempt": attempt + 1,
                    },
                    now_ms=now_ms,
                )
                return decision
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue

        with self._lock:
            self._status.evaluations_failed += 1
            self._status.last_error = type(last_err).__name__ if last_err else "unknown"
        try:
            self.store.write_audit(
                "evaluate_failed",
                {
                    "eval_key": ekey,
                    "error": type(last_err).__name__ if last_err else "unknown",
                    "source": job.source,
                },
                now_ms=now_ms,
            )
        except SignalHistoryStoreError:
            pass
        self._set_degraded(self._status.last_error or "evaluate_failed")
        # Do not mark checkpoint — retry after restart / later poll.
        return None

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                self.process_job(item)
            except Exception as exc:  # noqa: BLE001
                self._set_degraded(type(exc).__name__)

    def _lease_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(LEASE_RENEW_EVERY_S)
            if self._stop.is_set():
                break
            now_ms = self._now()
            try:
                ok = self.store.try_acquire_scheduler_lock(
                    owner_id=self._owner_id,
                    hostname=self._hostname,
                    pid=self._pid,
                    now_ms=now_ms,
                    lease_ms=LEASE_MS,
                )
                with self._lock:
                    self._status.lock_held = bool(ok)
                if not ok:
                    self._set_degraded("scheduler_lock_lost")
                    self._stop.set()
                    break
            except SignalHistoryStoreError as exc:
                self._set_degraded(f"lease:{type(exc).__name__}")
                self._stop.set()
                break

    def _poll_loop(self) -> None:
        # Initial slight delay so start() backfill runs first.
        time.sleep(1.0)
        while not self._stop.is_set():
            for sym in self.config.symbols:
                if self._stop.is_set():
                    break
                try:
                    self._offer_latest_closed(sym, source="rest_poll")
                except Exception as exc:  # noqa: BLE001
                    self._set_degraded(f"poll:{type(exc).__name__}")
            self._stop.wait(self.config.rest_poll_seconds)

    def _backfill_stream(self, symbol: str) -> None:
        candles, _ = self.fetcher.fetch_candles(
            category=self.config.category,
            symbol=symbol,
            interval=self.config.interval,
            limit=50,
        )
        now_ms = self._now()
        filtered = filter_confirmed_candles(
            candles, interval=self.config.interval, now_ms=now_ms, grace_ms=0
        )
        if isinstance(filtered, CandleFilterReject) or not filtered.candles:
            return
        confirmed = filtered.candles
        last_cp = self.store.last_checkpoint_close_ms(
            strategy_version=self.config.strategy_version,
            category=self.config.category,
            symbol=symbol,
            interval=self.config.interval,
        )
        missing: list[Candle] = []
        for c in confirmed:
            close = candle_close_ms(c.start, self.config.interval)
            if last_cp is not None and close <= last_cp:
                continue
            missing.append(c)
        # Bound backfill — only the oldest N of the missing gap (then catch up via poll).
        for c in missing[-self.config.max_backfill :]:
            close = candle_close_ms(c.start, self.config.interval)
            self.enqueue(
                ClosedCandleJob(
                    category=self.config.category,
                    symbol=symbol.upper(),
                    interval=self.config.interval,
                    candle_start_ms=c.start,
                    candle_close_ms=close,
                    source="rest_backfill",
                    enqueued_at_ms=now_ms,
                )
            )

    def _offer_latest_closed(self, symbol: str, *, source: str) -> None:
        candles, _ = self.fetcher.fetch_candles(
            category=self.config.category,
            symbol=symbol,
            interval=self.config.interval,
            limit=5,
        )
        now_ms = self._now()
        filtered = filter_confirmed_candles(
            candles, interval=self.config.interval, now_ms=now_ms, grace_ms=0
        )
        if isinstance(filtered, CandleFilterReject) or not filtered.candles:
            return
        c = filtered.candles[-1]
        close = candle_close_ms(c.start, self.config.interval)
        self.enqueue(
            ClosedCandleJob(
                category=self.config.category,
                symbol=symbol.upper(),
                interval=self.config.interval,
                candle_start_ms=c.start,
                candle_close_ms=close,
                source=source,
                enqueued_at_ms=now_ms,
            )
        )

    def _set_degraded(self, err: str) -> None:
        with self._lock:
            self._status.last_error = err
            if self._state in {
                EngineState.RUNNING,
                EngineState.STARTING,
                EngineState.DEGRADED,
            }:
                self._state = EngineState.DEGRADED
        logger.warning("auto_signal_engine_degraded error=%s", err)
