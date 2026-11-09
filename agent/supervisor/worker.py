"""Background paper supervisor worker.

Runs independently of the chat socket. Fetches public confirmed candles and
advances the paper journal while the supervisor is RUNNING. Never attaches
API keys and never submits an exchange order.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

from agent.market_data import Candle
from agent.supervisor.machine import PaperSupervisor, SupervisorState

logger = logging.getLogger(__name__)


CandleFetcher = Callable[..., list[Candle]]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class PaperSupervisorWorker:
    """Single-owner background loop over a PaperSupervisor."""

    def __init__(
        self,
        supervisor: PaperSupervisor,
        *,
        fetch_candles: CandleFetcher,
        poll_seconds: float | None = None,
        history: int = 220,
    ) -> None:
        self.supervisor = supervisor
        self.fetch_candles = fetch_candles
        self.poll_seconds = max(
            5.0,
            float(poll_seconds if poll_seconds is not None else _env_float("CRYPTONOVA_PAPER_SUPERVISOR_POLL_SECONDS", 30.0)),
        )
        self.history = max(50, int(history))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_cycle: dict[str, Any] = {}
        self.last_attempt_ms: int | None = None
        self.last_success_ms: int | None = None
        self.consecutive_failures = 0
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="paper-supervisor-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, join_seconds: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_seconds)
        if thread is None or not thread.is_alive():
            self._thread = None

    def tick_once(self) -> dict[str, Any]:
        """One evaluation cycle. Safe for tests without a background thread."""
        status = self.supervisor.status()
        state = str(status.get("state") or SupervisorState.STOPPED.value)
        auth = status.get("authorization") if isinstance(status.get("authorization"), dict) else {}
        recoverable = state == SupervisorState.ERROR.value and status.get("last_error") == "market_data_unavailable"
        if state not in {SupervisorState.RUNNING.value, SupervisorState.PAUSED.value, SupervisorState.HALTED.value, SupervisorState.STOPPING.value} and not recoverable:
            body = self.supervisor.status(skipped=True, reason="supervisor_not_running", worker="idle")
            self.last_cycle = body
            return body
        symbol = str(auth.get("symbol") or "HYPEUSDT")
        category = str(auth.get("category") or "linear")
        interval = str(auth.get("interval") or "15")
        now_ms = int(time.time() * 1000)
        self.last_attempt_ms = now_ms
        try:
            candles = self.fetch_candles(
                symbol=symbol,
                category=category,
                interval=interval,
                limit=self.history,
                now_ms=now_ms,
            )
        except Exception as exc:  # noqa: BLE001 — fail closed
            logger.warning("paper_supervisor_candle_fetch_failed type=%s", type(exc).__name__)
            try:
                body = self.supervisor.run_cycle(
                    [],
                    symbol=symbol,
                    category=category,
                    interval=interval,
                    now_ms=now_ms,
                    data_fresh=False,
                )
                body["worker"] = "fetch_failed"
            except RuntimeError as claim_exc:
                # Another worker still holds the lease (common after DNS blips / dual API).
                if "busy" not in str(claim_exc).lower():
                    raise
                body = self.supervisor.status(
                    skipped=True,
                    reason="market_data_unavailable",
                    worker="fetch_failed_busy",
                )
            body["live_orders"] = False
            body["exchange_order_sent"] = False
            self.last_cycle = body
            self.consecutive_failures += 1
            self.last_error = "market_data_unavailable"
            return body
        try:
            body = self.supervisor.run_cycle(
                candles,
                symbol=symbol,
                category=category,
                interval=interval,
                now_ms=now_ms,
                data_fresh=True,
            )
            body["worker"] = "tick"
        except RuntimeError as claim_exc:
            if "busy" not in str(claim_exc).lower():
                raise
            logger.warning("paper_supervisor_tick_skipped reason=supervisor_worker_busy")
            body = self.supervisor.status(
                skipped=True,
                reason="supervisor_worker_busy",
                worker="tick_busy",
            )
            self.last_cycle = body
            self.consecutive_failures += 1
            self.last_error = "supervisor_worker_busy"
            return body
        body["live_orders"] = False
        body["exchange_order_sent"] = False
        self.last_cycle = body
        if body.get("state") == SupervisorState.ERROR.value:
            self.consecutive_failures += 1
            self.last_error = str(body.get("last_error") or "cycle_failed")
        else:
            self.last_success_ms = now_ms
            self.consecutive_failures = 0
            self.last_error = None
        return body

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick_once()
            except Exception:  # noqa: BLE001
                self.consecutive_failures += 1
                self.last_error = "worker_tick_failed"
                logger.exception("paper_supervisor_worker_tick_failed")
            self._stop.wait(self.poll_seconds)
