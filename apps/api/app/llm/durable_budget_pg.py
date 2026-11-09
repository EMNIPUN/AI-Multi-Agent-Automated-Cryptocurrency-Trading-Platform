"""Postgres budget ledger. Refuses SQLite. Not ready until migration 20261108_0011."""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from agent.llm_intelligence.audit_repository import LlmStorageError


class PostgresDurableBudget:
    def __init__(
        self,
        engine: Engine,
        *,
        max_calls_per_hour: int = 20,
        daily_budget_usd: float = 1.0,
        min_call_usd: float = 0.01,
    ) -> None:
        if engine.dialect.name == "sqlite":
            raise LlmStorageError("sqlite_forbidden", "LLM budget ledger refuses SQLite")
        self._engine = engine
        self.max_calls_per_hour = max_calls_per_hour
        self.daily_budget_usd = daily_budget_usd
        self.min_call_usd = min_call_usd

    def ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM app.llm_budget_ledger LIMIT 1"))
            return True
        except SQLAlchemyError:
            return False

    def try_begin(self, now_ms: int, idempotency_key: str | None = None) -> str | None:
        if not idempotency_key or not self.ready():
            return "budget_storage_unavailable"
        try:
            with self._engine.begin() as conn:
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('cryptonova_llm_budget'))"))
                existing = conn.execute(
                    text(
                        "SELECT status FROM app.llm_budget_ledger WHERE idempotency_key = :key"
                    ),
                    {"key": idempotency_key},
                ).first()
                if existing is not None:
                    return "reservation_pending"
                hour_count = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM app.llm_budget_ledger
                        WHERE created_at_ms >= :start_ms
                        """
                    ),
                    {"start_ms": now_ms - 3_600_000},
                ).scalar()
                if int(hour_count or 0) >= self.max_calls_per_hour:
                    return "hourly_cap"
                spent = conn.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(CASE
                            WHEN status = 'committed' THEN actual_usd
                            WHEN status = 'reserved' THEN reserved_usd
                            ELSE 0 END), 0)
                        FROM app.llm_budget_ledger
                        WHERE created_at_ms >= :start_ms
                          AND status IN ('reserved', 'committed')
                        """
                    ),
                    {"start_ms": now_ms - 86_400_000},
                ).scalar()
                if float(spent or 0) + self.min_call_usd > self.daily_budget_usd + 1e-9:
                    return "budget_exhausted"
                conn.execute(
                    text(
                        """
                        INSERT INTO app.llm_budget_ledger (
                            reservation_id, idempotency_key, created_at_ms, reserved_usd, status
                        ) VALUES (:reservation_id, :key, :created_at_ms, :reserved_usd, 'reserved')
                        ON CONFLICT (idempotency_key) DO NOTHING
                        """
                    ),
                    {
                        "reservation_id": f"lbr_{idempotency_key[:48]}",
                        "key": idempotency_key,
                        "created_at_ms": now_ms,
                        "reserved_usd": self.min_call_usd,
                    },
                )
            return None
        except SQLAlchemyError:
            return "budget_storage_unavailable"

    def add_cost(self, now_ms: int, usd: float, idempotency_key: str | None = None, **kwargs) -> None:
        if not idempotency_key:
            return
        amount = max(self.min_call_usd, float(usd or 0))
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE app.llm_budget_ledger
                        SET status = 'committed',
                            actual_usd = :amount,
                            prompt_tokens = :prompt_tokens,
                            completion_tokens = :completion_tokens
                        WHERE idempotency_key = :key AND status = 'reserved'
                        """
                    ),
                    {
                        "amount": amount,
                        "prompt_tokens": int(kwargs.get("prompt_tokens") or 0),
                        "completion_tokens": int(kwargs.get("completion_tokens") or 0),
                        "key": idempotency_key,
                    },
                )
        except SQLAlchemyError:
            return None

    def release(self, idempotency_key: str | None = None) -> None:
        if not idempotency_key:
            return
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE app.llm_budget_ledger
                        SET status = 'released', actual_usd = 0
                        WHERE idempotency_key = :key AND status = 'reserved'
                        """
                    ),
                    {"key": idempotency_key},
                )
        except SQLAlchemyError:
            return None

    def end(self) -> None:
        return None

    def snapshot(self, now_ms: int) -> dict[str, float | int | str]:
        if now_ms <= 0:
            now_ms = int(time.time() * 1000)
        try:
            with self._engine.connect() as conn:
                hour_count = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM app.llm_budget_ledger
                        WHERE created_at_ms >= :start_ms
                        """
                    ),
                    {"start_ms": now_ms - 3_600_000},
                ).scalar()
                spent = conn.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(CASE
                            WHEN status = 'committed' THEN actual_usd
                            WHEN status = 'reserved' THEN reserved_usd
                            ELSE 0 END), 0)
                        FROM app.llm_budget_ledger
                        WHERE created_at_ms >= :start_ms
                          AND status IN ('reserved', 'committed')
                        """
                    ),
                    {"start_ms": now_ms - 86_400_000},
                ).scalar()
            spend = float(spent or 0)
            return {
                "calls_this_hour": int(hour_count or 0),
                "estimated_spend_today_usd": spend,
                "daily_budget_usd": self.daily_budget_usd,
                "remaining_usd": max(0.0, float(self.daily_budget_usd) - spend),
                "storage": "postgres",
                "durable_across_processes": True,
            }
        except SQLAlchemyError:
            return {
                "calls_this_hour": 0,
                "estimated_spend_today_usd": 0.0,
                "daily_budget_usd": self.daily_budget_usd,
                "remaining_usd": 0.0,
                "storage": "unavailable",
                "durable_across_processes": False,
            }
