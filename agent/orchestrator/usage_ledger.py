"""Durable OpenAI orchestrator usage accounting with atomic budget reservation."""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_LEDGER = Path("data/orchestrator_usage/usage.sqlite3")


@dataclass(frozen=True)
class UsageRecord:
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    model: str
    created_ms: int


class UsageLedger:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_LEDGER)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_ms INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    openai_called INTEGER NOT NULL DEFAULT 1,
                    live_orders INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orchestrator_reservations (
                    idempotency_key TEXT PRIMARY KEY,
                    created_ms INTEGER NOT NULL,
                    reserved_usd REAL NOT NULL,
                    actual_usd REAL,
                    status TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def record(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        model: str,
        created_ms: int | None = None,
    ) -> None:
        ts = int(created_ms if created_ms is not None else time.time() * 1000)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO orchestrator_usage
                (created_ms, model, prompt_tokens, completion_tokens, cost_usd, openai_called, live_orders)
                VALUES (?, ?, ?, ?, ?, 1, 0)
                """,
                (ts, model, int(prompt_tokens), int(completion_tokens), float(cost_usd)),
            )
            conn.commit()

    def spent_since_ms(self, since_ms: int) -> float:
        with self._connect() as conn:
            usage = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM orchestrator_usage WHERE created_ms >= ?",
                (int(since_ms),),
            ).fetchone()
            reserved = conn.execute(
                """
                SELECT COALESCE(SUM(reserved_usd), 0) AS total
                FROM orchestrator_reservations
                WHERE status = 'reserved' AND created_ms >= ?
                """,
                (int(since_ms),),
            ).fetchone()
        return float(usage["total"] if usage else 0.0) + float(reserved["total"] if reserved else 0.0)

    def total_spent_usd(self) -> float:
        with self._connect() as conn:
            usage = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM orchestrator_usage"
            ).fetchone()
            reserved = conn.execute(
                """
                SELECT COALESCE(SUM(reserved_usd), 0) AS total
                FROM orchestrator_reservations WHERE status = 'reserved'
                """
            ).fetchone()
        return float(usage["total"] if usage else 0.0) + float(reserved["total"] if reserved else 0.0)

    def try_reserve(
        self,
        *,
        reserved_usd: float,
        daily_budget_usd: float,
        monthly_budget_usd: float,
        total_budget_usd: float | None = None,
        idempotency_key: str | None = None,
        model: str = "",
        now_ms: int | None = None,
    ) -> tuple[bool, str, str]:
        """Atomically reserve budget. Returns (ok, key_or_reason, reason_code)."""
        key = (idempotency_key or f"res_{uuid.uuid4().hex}").strip()
        clock = int(now_ms if now_ms is not None else time.time() * 1000)
        amount = max(0.0, float(reserved_usd))
        day_ms = clock - 86_400_000
        month_ms = clock - 30 * 86_400_000
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT status, reserved_usd FROM orchestrator_reservations WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if existing is not None:
                status = str(existing["status"])
                if status in {"reserved", "committed"}:
                    conn.commit()
                    return True, key, "idempotent_hit"
                # released/failed — allow reuse by deleting
                conn.execute(
                    "DELETE FROM orchestrator_reservations WHERE idempotency_key = ?",
                    (key,),
                )

            def _spent(since: int) -> float:
                u = conn.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM orchestrator_usage WHERE created_ms >= ?",
                    (since,),
                ).fetchone()
                r = conn.execute(
                    """
                    SELECT COALESCE(SUM(reserved_usd), 0) AS total
                    FROM orchestrator_reservations
                    WHERE status = 'reserved' AND created_ms >= ?
                    """,
                    (since,),
                ).fetchone()
                return float(u["total"] or 0) + float(r["total"] or 0)

            spent_day = _spent(day_ms)
            spent_month = _spent(month_ms)
            spent_total = float(
                conn.execute("SELECT COALESCE(SUM(cost_usd), 0) AS total FROM orchestrator_usage").fetchone()[
                    "total"
                ]
                or 0
            ) + float(
                conn.execute(
                    "SELECT COALESCE(SUM(reserved_usd), 0) AS total FROM orchestrator_reservations WHERE status = 'reserved'"
                ).fetchone()["total"]
                or 0
            )
            if spent_day + amount > float(daily_budget_usd):
                conn.commit()
                return False, key, "daily_budget_exceeded"
            if spent_month + amount > float(monthly_budget_usd):
                conn.commit()
                return False, key, "monthly_budget_exceeded"
            if total_budget_usd is not None and spent_total + amount > float(total_budget_usd):
                conn.commit()
                return False, key, "total_budget_exceeded"
            conn.execute(
                """
                INSERT INTO orchestrator_reservations
                (idempotency_key, created_ms, reserved_usd, actual_usd, status, model)
                VALUES (?, ?, ?, NULL, 'reserved', ?)
                """,
                (key, clock, amount, model or ""),
            )
            conn.commit()
        return True, key, "reserved"

    def commit_reservation(
        self,
        idempotency_key: str,
        *,
        actual_usd: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = "",
        created_ms: int | None = None,
    ) -> None:
        key = str(idempotency_key or "").strip()
        if not key:
            return
        ts = int(created_ms if created_ms is not None else time.time() * 1000)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM orchestrator_reservations WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO orchestrator_usage
                    (created_ms, model, prompt_tokens, completion_tokens, cost_usd, openai_called, live_orders)
                    VALUES (?, ?, ?, ?, ?, 1, 0)
                    """,
                    (ts, model or "", int(prompt_tokens), int(completion_tokens), float(actual_usd)),
                )
                conn.commit()
                return
            if str(row["status"]) == "committed":
                conn.commit()
                return
            conn.execute(
                """
                UPDATE orchestrator_reservations
                SET status = 'committed', actual_usd = ?, prompt_tokens = ?, completion_tokens = ?, model = ?
                WHERE idempotency_key = ?
                """,
                (float(actual_usd), int(prompt_tokens), int(completion_tokens), model or "", key),
            )
            conn.execute(
                """
                INSERT INTO orchestrator_usage
                (created_ms, model, prompt_tokens, completion_tokens, cost_usd, openai_called, live_orders)
                VALUES (?, ?, ?, ?, ?, 1, 0)
                """,
                (ts, model or "", int(prompt_tokens), int(completion_tokens), float(actual_usd)),
            )
            conn.commit()

    def release_reservation(self, idempotency_key: str) -> None:
        key = str(idempotency_key or "").strip()
        if not key:
            return
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE orchestrator_reservations
                SET status = 'released'
                WHERE idempotency_key = ? AND status = 'reserved'
                """,
                (key,),
            )
            conn.commit()

    def summary(self, *, now_ms: int | None = None) -> dict[str, Any]:
        clock = int(now_ms if now_ms is not None else time.time() * 1000)
        day_ms = clock - 86_400_000
        month_ms = clock - 30 * 86_400_000
        with self._connect() as conn:
            total_calls = conn.execute("SELECT COUNT(*) AS n FROM orchestrator_usage").fetchone()["n"]
            open_reservations = conn.execute(
                "SELECT COUNT(*) AS n FROM orchestrator_reservations WHERE status = 'reserved'"
            ).fetchone()["n"]
        return {
            "ledger_path": str(self.path),
            "total_calls": int(total_calls),
            "open_reservations": int(open_reservations),
            "spent_usd_24h": self.spent_since_ms(day_ms),
            "spent_usd_30d": self.spent_since_ms(month_ms),
            "spent_usd_total": self.total_spent_usd(),
            "openai_called_recorded": True,
            "live_orders": False,
            "places_orders": False,
        }
