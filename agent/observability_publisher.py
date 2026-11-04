"""
Optional observability publisher hook for AgentRunner (Phase 3A).

Default is NullObservabilityPublisher — no network, no DB writes, no Bybit.
Wire an InMemoryObservabilityPublisher (or future sink) from tests / worker only.
Never treat published events as execution authority.
"""

from __future__ import annotations

from apps.api.app.observability.publisher import (
    InMemoryObservabilityPublisher,
    NullObservabilityPublisher,
    ObservabilityPublisher,
)

__all__ = [
    "InMemoryObservabilityPublisher",
    "NullObservabilityPublisher",
    "ObservabilityPublisher",
]
