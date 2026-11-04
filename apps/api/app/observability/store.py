"""In-memory observability event buffer — tests + future worker fan-in (not SoT)."""

from __future__ import annotations

from collections import OrderedDict

from apps.api.app.observability.types import ObservabilityEvent


class ObservabilityEventBuffer:
    """Append-only with idempotent event_id and cursor-based catch-up."""

    def __init__(self, *, maxlen: int = 2_000) -> None:
        self._maxlen = maxlen
        self._by_id: OrderedDict[str, ObservabilityEvent] = OrderedDict()

    def append(self, event: ObservabilityEvent) -> bool:
        """Return True if newly inserted; False if duplicate event_id."""
        if event.event_id in self._by_id:
            return False
        self._by_id[event.event_id] = event
        while len(self._by_id) > self._maxlen:
            self._by_id.popitem(last=False)
        return True

    def extend(self, events: list[ObservabilityEvent]) -> int:
        return sum(1 for e in events if self.append(e))

    def since(self, cursor: str | None) -> list[ObservabilityEvent]:
        items = list(self._by_id.values())
        if not cursor:
            return items
        found = False
        out: list[ObservabilityEvent] = []
        for ev in items:
            if found:
                out.append(ev)
            elif ev.event_id == cursor:
                found = True
        # Unknown cursor → full snapshot recovery (caller should also refetch snapshot).
        if not found:
            return items
        return out

    def all(self) -> list[ObservabilityEvent]:
        return list(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)
