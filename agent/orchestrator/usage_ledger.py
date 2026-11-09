"""Durable OpenAI orchestrator usage accounting. Isolated SQLite only."""

from __future__ import annotations

import sqlite3
import time
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
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
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
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM orchestrator_usage WHERE created_ms >= ?",
                (int(since_ms),),
            ).fetchone()
        return float(row["total"] if row else 0.0)

    def summary(self, *, now_ms: int | None = None) -> dict[str, Any]:
        clock = int(now_ms if now_ms is not None else time.time() * 1000)
        day_ms = clock - 86_400_000
        month_ms = clock - 30 * 86_400_000
        with self._connect() as conn:
            total_calls = conn.execute("SELECT COUNT(*) AS n FROM orchestrator_usage").fetchone()["n"]
        return {
            "ledger_path": str(self.path),
            "total_calls": int(total_calls),
            "spent_usd_24h": self.spent_since_ms(day_ms),
            "spent_usd_30d": self.spent_since_ms(month_ms),
            "openai_called_recorded": True,
            "live_orders": False,
            "places_orders": False,
        }
