"""Hourly call cap, daily budget, and concurrency. Estimates are not invoices."""

from __future__ import annotations

import threading

from agent.llm_intelligence.config import LlmConfig


class BudgetGuard:
    def __init__(self, config: LlmConfig) -> None:
        self.config = config
        self._sem = threading.BoundedSemaphore(max(1, config.max_concurrency))
        self._lock = threading.Lock()
        self._calls: list[int] = []
        self._spend: list[tuple[int, float]] = []

    def try_begin(self, now_ms: int) -> str | None:
        if not self._sem.acquire(blocking=False):
            return "concurrency_limited"
        with self._lock:
            self._prune(now_ms)
            if len(self._calls) >= self.config.max_calls_per_hour:
                self._sem.release()
                return "hourly_cap"
            if self._spent_today(now_ms) + self.config.min_call_usd > self.config.daily_budget_usd + 1e-9:
                self._sem.release()
                return "budget_exhausted"
            self._calls.append(now_ms)
        return None

    def end(self) -> None:
        self._sem.release()

    def add_cost(self, now_ms: int, usd: float) -> None:
        with self._lock:
            self._spend.append((now_ms, max(0.0, usd)))

    def snapshot(self, now_ms: int) -> dict[str, float | int]:
        with self._lock:
            self._prune(now_ms)
            return {
                "calls_this_hour": len(self._calls),
                "estimated_spend_today_usd": round(self._spent_today(now_ms), 6),
                "daily_budget_usd": self.config.daily_budget_usd,
            }

    def _prune(self, now_ms: int) -> None:
        hour = now_ms - 3_600_000
        day = now_ms - 86_400_000
        self._calls = [ts for ts in self._calls if ts >= hour]
        self._spend = [(ts, usd) for ts, usd in self._spend if ts >= day]

    def _spent_today(self, now_ms: int) -> float:
        day = now_ms - 86_400_000
        return sum(usd for ts, usd in self._spend if ts >= day)
