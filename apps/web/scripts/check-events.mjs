/** Offline Node check — no npm deps required. */
import assert from "node:assert/strict";

function dedupeEvents(events) {
  const seen = new Set();
  const out = [];
  for (const ev of events) {
    if (seen.has(ev.event_id)) continue;
    seen.add(ev.event_id);
    out.push(ev);
  }
  return out;
}

function sortEventsChronological(events) {
  return [...events].sort((a, b) => {
    const ta = Date.parse(a.occurred_at);
    const tb = Date.parse(b.occurred_at);
    if (ta !== tb) return ta - tb;
    return a.event_id.localeCompare(b.event_id);
  });
}

function mergeSnapshotAndCursor(snapshotEvents, cursorEvents, cursor) {
  const base = dedupeEvents(sortEventsChronological(snapshotEvents));
  if (!cursor) {
    return dedupeEvents(sortEventsChronological([...base, ...cursorEvents]));
  }
  const idx = base.findIndex((e) => e.event_id === cursor);
  const retained = idx >= 0 ? base.slice(0, idx + 1) : base;
  return dedupeEvents(sortEventsChronological([...retained, ...cursorEvents]));
}

function isHeartbeatStale(heartbeatAt, staleAfterSeconds, nowMs = Date.now()) {
  if (!heartbeatAt) return true;
  const t = Date.parse(heartbeatAt);
  if (Number.isNaN(t)) return true;
  return nowMs - t > staleAfterSeconds * 1000;
}

const ev = (id, at) => ({ event_id: id, occurred_at: at });

assert.deepEqual(
  dedupeEvents([ev("1", "2026-11-04T10:00:00Z"), ev("1", "2026-11-04T10:00:01Z"), ev("2", "2026-11-04T10:00:02Z")]).map(
    (e) => e.event_id,
  ),
  ["1", "2"],
);

const merged = mergeSnapshotAndCursor(
  [ev("a", "2026-11-04T10:00:00Z"), ev("b", "2026-11-04T10:00:01Z"), ev("c", "2026-11-04T10:00:02Z")],
  [ev("c", "2026-11-04T10:00:02Z"), ev("d", "2026-11-04T10:00:03Z")],
  "b",
);
assert.deepEqual(
  merged.map((e) => e.event_id),
  ["a", "b", "c", "d"],
);

const now = Date.parse("2026-11-04T12:00:30Z");
assert.equal(isHeartbeatStale("2026-11-04T12:00:00Z", 30, now), false);
assert.equal(isHeartbeatStale("2026-11-04T11:59:00Z", 30, now), true);
assert.equal(isHeartbeatStale(null, 30, now), true);

console.log("check-events.mjs: ok");
