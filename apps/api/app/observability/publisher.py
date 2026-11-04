"""
Worker → observability publisher adapter (Phase 3A plan + no-op default).

Does not touch SQLite intent/risk stores. Does not call Bybit.
Idempotent event_ids are the caller's responsibility.
"""

from __future__ import annotations

from typing import Protocol

from apps.api.app.observability.store import ObservabilityEventBuffer
from apps.api.app.observability.types import ObservabilityEvent


class ObservabilityPublisher(Protocol):
    def publish(self, event: ObservabilityEvent) -> bool: ...


class NullObservabilityPublisher:
    """Default for AgentRunner — zero side effects."""

    def publish(self, event: ObservabilityEvent) -> bool:
        return False


class InMemoryObservabilityPublisher:
    def __init__(self, buffer: ObservabilityEventBuffer | None = None) -> None:
        self.buffer = buffer or ObservabilityEventBuffer()

    def publish(self, event: ObservabilityEvent) -> bool:
        return self.buffer.append(event)
