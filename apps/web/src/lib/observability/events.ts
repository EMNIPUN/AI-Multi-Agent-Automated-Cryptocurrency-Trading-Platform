import type { ObservabilityEvent } from "./types";

/** Deduplicate by event_id preserving first-seen order. */
export function dedupeEvents(events: ObservabilityEvent[]): ObservabilityEvent[] {
  const seen = new Set<string>();
  const out: ObservabilityEvent[] = [];
  for (const ev of events) {
    if (seen.has(ev.event_id)) continue;
    seen.add(ev.event_id);
    out.push(ev);
  }
  return out;
}

/** Stable chronological order (occurred_at asc, then event_id). */
export function sortEventsChronological(
  events: ObservabilityEvent[],
): ObservabilityEvent[] {
  return [...events].sort((a, b) => {
    const ta = Date.parse(a.occurred_at);
    const tb = Date.parse(b.occurred_at);
    if (ta !== tb) return ta - tb;
    return a.event_id.localeCompare(b.event_id);
  });
}

/**
 * Reconnect merge: apply snapshot events, then append cursor-tail events.
 * Unknown/missing cursor: treat incoming as full replacement after snapshot base.
 */
export function mergeSnapshotAndCursor(
  snapshotEvents: ObservabilityEvent[],
  cursorEvents: ObservabilityEvent[],
  cursor: string | null | undefined,
): ObservabilityEvent[] {
  const base = dedupeEvents(sortEventsChronological(snapshotEvents));
  if (!cursor) {
    return dedupeEvents(sortEventsChronological([...base, ...cursorEvents]));
  }
  const idx = base.findIndex((e) => e.event_id === cursor);
  const retained = idx >= 0 ? base.slice(0, idx + 1) : base;
  return dedupeEvents(sortEventsChronological([...retained, ...cursorEvents]));
}

export function isHeartbeatStale(
  heartbeatAt: string | null | undefined,
  staleAfterSeconds: number,
  nowMs: number = Date.now(),
): boolean {
  if (!heartbeatAt) return true;
  const t = Date.parse(heartbeatAt);
  if (Number.isNaN(t)) return true;
  return nowMs - t > staleAfterSeconds * 1000;
}
