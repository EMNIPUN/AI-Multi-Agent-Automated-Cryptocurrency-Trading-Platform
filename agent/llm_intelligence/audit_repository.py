"""Audit storage. In-memory is tests only. Runtime must not pretend memory is durable."""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Protocol

from agent.llm_intelligence.schemas import LlmEvaluation


class LlmStorageError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LlmAuditRepository(Protocol):
    def ready(self) -> bool: ...

    def storage_kind(self) -> str: ...

    def save(self, record: LlmEvaluation) -> LlmEvaluation: ...

    def get(self, evaluation_id: str) -> LlmEvaluation | None: ...

    def get_by_idempotency(self, key: str) -> LlmEvaluation | None: ...

    def list_recent(self, *, limit: int) -> list[LlmEvaluation]: ...


class InMemoryLlmAuditRepository:
    storage_name = "memory_test_only"

    def __init__(self) -> None:
        self._rows: dict[str, LlmEvaluation] = {}
        self._by_key: dict[str, str] = {}
        self._lock = threading.Lock()

    def ready(self) -> bool:
        return True

    def storage_kind(self) -> str:
        return self.storage_name

    def save(self, record: LlmEvaluation) -> LlmEvaluation:
        with self._lock:
            existing = self._by_key.get(record.idempotency_key)
            if existing:
                prior = self._rows[existing]
                return replace(prior, idempotent_replay=True)
            self._rows[record.evaluation_id] = record
            self._by_key[record.idempotency_key] = record.evaluation_id
            return record

    def get(self, evaluation_id: str) -> LlmEvaluation | None:
        return self._rows.get(evaluation_id)

    def get_by_idempotency(self, key: str) -> LlmEvaluation | None:
        row_id = self._by_key.get(key)
        if not row_id:
            return None
        return self._rows.get(row_id)

    def list_recent(self, *, limit: int) -> list[LlmEvaluation]:
        rows = sorted(self._rows.values(), key=lambda row: row.requested_at_ms, reverse=True)
        return rows[: max(1, min(limit, 100))]


class UnavailableLlmAuditRepository:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def ready(self) -> bool:
        return False

    def storage_kind(self) -> str:
        return "unavailable"

    def save(self, record: LlmEvaluation) -> LlmEvaluation:
        raise LlmStorageError("storage_unavailable", self.reason)

    def get(self, evaluation_id: str) -> LlmEvaluation | None:
        raise LlmStorageError("storage_unavailable", self.reason)

    def get_by_idempotency(self, key: str) -> LlmEvaluation | None:
        return None

    def list_recent(self, *, limit: int) -> list[LlmEvaluation]:
        raise LlmStorageError("storage_unavailable", self.reason)
