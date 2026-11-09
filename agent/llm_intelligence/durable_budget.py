"""Durable LLM budget ledger. Process-local BudgetGuard remains test-only."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class LedgerRow:
    idempotency_key: str
    created_at_ms: int
    reserved_usd: float
    actual_usd: float | None
    status: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class SharedLedger:
    rows: list[LedgerRow] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class FailClosedBudget:
    """Used when app.llm_budget_ledger is missing. Never calls the provider."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def ready(self) -> bool:
        return False

    def try_begin(self, now_ms: int, idempotency_key: str | None = None) -> str:
        return "budget_storage_unavailable"

    def add_cost(self, now_ms: int, usd: float, **_kwargs) -> None:
        return None

    def release(self, idempotency_key: str | None = None) -> None:
        return None

    def end(self) -> None:
        return None

    def snapshot(self, now_ms: int) -> dict[str, float | int | str]:
        return {
            "calls_this_hour": 0,
            "estimated_spend_today_usd": 0.0,
            "daily_budget_usd": 0.0,
            "storage": self.reason,
        }


class InMemoryDurableBudget:
    """Shared ledger so a new instance sees reservations after a simulated restart."""

    def __init__(
        self,
        ledger: SharedLedger,
        *,
        max_calls_per_hour: int,
        daily_budget_usd: float,
        min_call_usd: float,
    ) -> None:
        self.ledger = ledger
        self.max_calls_per_hour = max_calls_per_hour
        self.daily_budget_usd = daily_budget_usd
        self.min_call_usd = min_call_usd

    def ready(self) -> bool:
        return True

    def try_begin(self, now_ms: int, idempotency_key: str | None = None) -> str | None:
        key = idempotency_key or f"anon:{now_ms}"
        with self.ledger.lock:
            existing = next((row for row in self.ledger.rows if row.idempotency_key == key), None)
            if existing is not None:
                if existing.status == "committed":
                    return None
                return "reservation_pending"
            hour = [row for row in self.ledger.rows if now_ms - row.created_at_ms <= 3_600_000]
            if len(hour) >= self.max_calls_per_hour:
                return "hourly_cap"
            spent = sum(
                (row.actual_usd if row.actual_usd is not None else row.reserved_usd)
                for row in self.ledger.rows
                if row.status in {"reserved", "committed"} and now_ms - row.created_at_ms <= 86_400_000
            )
            if spent + self.min_call_usd > self.daily_budget_usd + 1e-9:
                return "budget_exhausted"
            self.ledger.rows.append(
                LedgerRow(
                    idempotency_key=key,
                    created_at_ms=now_ms,
                    reserved_usd=self.min_call_usd,
                    actual_usd=None,
                    status="reserved",
                )
            )
            return None

    def add_cost(self, now_ms: int, usd: float, idempotency_key: str | None = None, **kwargs) -> None:
        key = idempotency_key
        amount = max(self.min_call_usd, float(usd or 0))
        with self.ledger.lock:
            row = next((item for item in self.ledger.rows if item.idempotency_key == key), None)
            if row is None or row.status != "reserved":
                return
            row.actual_usd = amount
            row.status = "committed"
            row.prompt_tokens = int(kwargs.get("prompt_tokens") or 0)
            row.completion_tokens = int(kwargs.get("completion_tokens") or 0)

    def release(self, idempotency_key: str | None = None) -> None:
        with self.ledger.lock:
            row = next((item for item in self.ledger.rows if item.idempotency_key == idempotency_key), None)
            if row is not None and row.status == "reserved":
                row.status = "released"
                row.actual_usd = 0.0

    def end(self) -> None:
        return None

    def snapshot(self, now_ms: int) -> dict[str, float | int]:
        with self.ledger.lock:
            spent = sum(
                float(row.actual_usd or 0)
                for row in self.ledger.rows
                if row.status == "committed" and now_ms - row.created_at_ms <= 86_400_000
            )
            hour = sum(1 for row in self.ledger.rows if now_ms - row.created_at_ms <= 3_600_000)
            return {
                "calls_this_hour": hour,
                "estimated_spend_today_usd": round(spent, 6),
                "daily_budget_usd": self.daily_budget_usd,
            }
