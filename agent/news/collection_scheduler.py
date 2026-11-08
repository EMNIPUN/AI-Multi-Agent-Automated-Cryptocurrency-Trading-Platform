"""Bounded news collection scheduler (Prompt 69B). Off unless explicitly enabled."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class SchedulerStatus:
    enabled: bool = False
    running: bool = False
    owner_id: str | None = None
    last_tick_ms: int | None = None
    last_error: str | None = None
    ticks: int = 0
    note: str = (
        "Manual POST /api/v1/news/collect only. "
        "Set NEWS_AUTO_COLLECTION_ENABLED=true after migration 20261108_0008. "
        "Feeds are polled, not realtime."
    )


class InProcessLease:
    """Shared lease so two workers in one test cannot both poll."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.owner_id: str | None = None
        self.expires_at_ms = 0

    def try_acquire(self, owner_id: str, *, now_ms: int, ttl_ms: int) -> bool:
        with self._lock:
            if self.owner_id and self.owner_id != owner_id and self.expires_at_ms > now_ms:
                return False
            self.owner_id = owner_id
            self.expires_at_ms = now_ms + ttl_ms
            return True

    def release(self, owner_id: str) -> None:
        with self._lock:
            if self.owner_id == owner_id:
                self.owner_id = None
                self.expires_at_ms = 0


class NewsCollectionScheduler:
    def __init__(
        self,
        *,
        owner_id: str,
        interval_seconds: int,
        lease: InProcessLease,
        tick: Callable[[], None],
        enabled: bool,
    ) -> None:
        self.owner_id = owner_id
        self.interval_seconds = max(60, interval_seconds)
        self.lease = lease
        self.tick = tick
        self.enabled = enabled
        self.status = SchedulerStatus(enabled=enabled, owner_id=owner_id if enabled else None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self, *, now_ms: int | None = None) -> bool:
        if not self.enabled:
            self.status.last_error = "auto_collection_disabled"
            return False
        clock = now_ms if now_ms is not None else int(time.time() * 1000)
        ttl = self.interval_seconds * 1000
        if not self.lease.try_acquire(self.owner_id, now_ms=clock, ttl_ms=ttl):
            self.status.last_error = "lease_held"
            return False
        try:
            self.tick()
            self.status.last_tick_ms = clock
            self.status.last_error = None
            self.status.ticks += 1
            return True
        except Exception as exc:  # noqa: BLE001
            self.status.last_error = type(exc).__name__
            return False
        finally:
            self.lease.release(self.owner_id)

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self.status.running = True

        def _loop() -> None:
            while not self._stop.is_set():
                self.run_once()
                self._stop.wait(self.interval_seconds)

        self._thread = threading.Thread(target=_loop, name="news-collect", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.status.running = False
        self.lease.release(self.owner_id)
