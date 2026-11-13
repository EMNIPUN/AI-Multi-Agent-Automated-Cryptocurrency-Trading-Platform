"""Local SQLite conversation memory for Orchestrator V2. No Supabase tables."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


DEFAULT_STORE = Path("data/orchestrator_conversations/conversations.sqlite3")
MAX_HISTORY_MESSAGES = 24
SUMMARY_AFTER = 40


class ConversationStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or DEFAULT_STORE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    owner_key TEXT NOT NULL DEFAULT 'local',
                    created_ms INTEGER NOT NULL,
                    updated_ms INTEGER NOT NULL,
                    symbol TEXT,
                    interval TEXT,
                    summary TEXT,
                    last_analysis_json TEXT,
                    last_paper_session TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    created_ms INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_summary_json TEXT,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
                )
                """
            )
            conn.commit()

    def create(self, *, owner_key: str = "local") -> str:
        cid = f"conv_{uuid.uuid4().hex[:16]}"
        now = int(time.time() * 1000)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations
                (conversation_id, owner_key, created_ms, updated_ms)
                VALUES (?, ?, ?, ?)
                """,
                (cid, owner_key, now, now),
            )
            conn.commit()
        return cid

    def get(self, conversation_id: str, *, owner_key: str = "local") -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE conversation_id = ? AND owner_key = ?",
                (conversation_id, owner_key),
            ).fetchone()
        return dict(row) if row else None

    def ensure(self, conversation_id: str | None, *, owner_key: str = "local") -> str:
        if conversation_id and self.get(conversation_id, owner_key=owner_key):
            return conversation_id
        return self.create(owner_key=owner_key)

    def append_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        tool_summary: dict[str, Any] | list[Any] | None = None,
        owner_key: str = "local",
    ) -> None:
        if not self.get(conversation_id, owner_key=owner_key):
            return
        now = int(time.time() * 1000)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (conversation_id, created_ms, role, content, tool_summary_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    now,
                    role,
                    content,
                    json.dumps(tool_summary) if tool_summary is not None else None,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_ms = ? WHERE conversation_id = ?",
                (now, conversation_id),
            )
            conn.commit()
        self._maybe_summarize(conversation_id, owner_key=owner_key)

    def update_context(
        self,
        conversation_id: str,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        last_analysis: dict[str, Any] | None = None,
        last_paper_session: str | None = None,
        owner_key: str = "local",
    ) -> None:
        if not self.get(conversation_id, owner_key=owner_key):
            return
        now = int(time.time() * 1000)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return
            conn.execute(
                """
                UPDATE conversations SET
                    updated_ms = ?,
                    symbol = COALESCE(?, symbol),
                    interval = COALESCE(?, interval),
                    last_analysis_json = COALESCE(?, last_analysis_json),
                    last_paper_session = COALESCE(?, last_paper_session)
                WHERE conversation_id = ?
                """,
                (
                    now,
                    symbol,
                    interval,
                    json.dumps(last_analysis) if last_analysis is not None else None,
                    last_paper_session,
                    conversation_id,
                ),
            )
            conn.commit()

    def recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int = MAX_HISTORY_MESSAGES,
        owner_key: str = "local",
    ) -> list[dict[str, Any]]:
        if not self.get(conversation_id, owner_key=owner_key):
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_ms, tool_summary_json
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, max(1, int(limit))),
            ).fetchall()
        out = [dict(r) for r in reversed(rows)]
        return out

    def model_input_messages(
        self,
        conversation_id: str,
        *,
        latest_user: str,
        owner_key: str = "local",
    ) -> list[dict[str, str]]:
        """Bounded history for OpenAI input (system omitted — caller adds it)."""
        conv = self.get(conversation_id, owner_key=owner_key) or {}
        messages: list[dict[str, str]] = []
        summary = str(conv.get("summary") or "").strip()
        if summary:
            messages.append({"role": "system", "content": f"Prior conversation summary: {summary}"})
        symbol = str(conv.get("symbol") or "").strip()
        interval = str(conv.get("interval") or "").strip()
        if symbol:
            messages.append(
                {
                    "role": "system",
                    "content": f"Active context symbol={symbol}"
                    + (f" interval={interval}" if interval else "")
                    + ".",
                }
            )
        for row in self.recent_messages(conversation_id, owner_key=owner_key):
            role = str(row.get("role") or "")
            if role not in {"user", "assistant"}:
                continue
            content = str(row.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": latest_user})
        return messages[-MAX_HISTORY_MESSAGES:]

    def reset(self, conversation_id: str, *, owner_key: str = "local") -> bool:
        if not self.get(conversation_id, owner_key=owner_key):
            return False
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute(
                """
                UPDATE conversations
                SET summary = NULL, last_analysis_json = NULL, symbol = NULL, interval = NULL, updated_ms = ?
                WHERE conversation_id = ?
                """,
                (int(time.time() * 1000), conversation_id),
            )
            conn.commit()
        return True

    def list_conversations(self, *, owner_key: str = "local", limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT conversation_id, created_ms, updated_ms, symbol, interval
                FROM conversations
                WHERE owner_key = ?
                ORDER BY updated_ms DESC
                LIMIT ?
                """,
                (owner_key, max(1, int(limit))),
            ).fetchall()
        return [dict(r) for r in rows]

    def _maybe_summarize(self, conversation_id: str, *, owner_key: str) -> None:
        with self._connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["n"]
            if int(count) < SUMMARY_AFTER:
                return
            rows = conn.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
                LIMIT 20
                """,
                (conversation_id,),
            ).fetchall()
            # Deterministic local summary — no paid model.
            bits = [f"{r['role']}: {str(r['content'])[:120]}" for r in rows]
            summary = " | ".join(bits)[:800]
            conn.execute(
                "UPDATE conversations SET summary = ? WHERE conversation_id = ?",
                (summary, conversation_id),
            )
            # Drop oldest half after summarizing to bound storage.
            ids = conn.execute(
                """
                SELECT id FROM messages WHERE conversation_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (conversation_id, max(1, int(count) // 2)),
            ).fetchall()
            for row in ids:
                conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
            conn.commit()


_STORE: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _STORE
    if _STORE is None:
        _STORE = ConversationStore()
    return _STORE
