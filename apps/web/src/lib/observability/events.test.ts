import { describe, expect, it } from "vitest";

import {
  dedupeEvents,
  isHeartbeatStale,
  mergeSnapshotAndCursor,
  sortEventsChronological,
} from "./events";
import type { ObservabilityEvent } from "./types";

function ev(
  id: string,
  at: string,
  type = "agent.heartbeat",
): ObservabilityEvent {
  return {
    schema_version: "1.0.0",
    event_id: id,
    event_type: type,
    occurred_at: at,
    env_scope: "fixture",
    execution_mode: "DRY_RUN",
    message: id,
    payload: {},
  };
}

describe("event helpers", () => {
  it("dedupes by event_id", () => {
    const a = ev("1", "2026-11-04T10:00:00Z");
    const b = ev("1", "2026-11-04T10:00:01Z");
    const c = ev("2", "2026-11-04T10:00:02Z");
    expect(dedupeEvents([a, b, c]).map((e) => e.event_id)).toEqual(["1", "2"]);
  });

  it("sorts chronologically", () => {
    const out = sortEventsChronological([
      ev("b", "2026-11-04T10:00:02Z"),
      ev("a", "2026-11-04T10:00:01Z"),
    ]);
    expect(out.map((e) => e.event_id)).toEqual(["a", "b"]);
  });

  it("merges snapshot + cursor tail with dedup", () => {
    const snap = [
      ev("a", "2026-11-04T10:00:00Z"),
      ev("b", "2026-11-04T10:00:01Z"),
      ev("c", "2026-11-04T10:00:02Z"),
    ];
    const tail = [
      ev("c", "2026-11-04T10:00:02Z"),
      ev("d", "2026-11-04T10:00:03Z"),
    ];
    const merged = mergeSnapshotAndCursor(snap, tail, "b");
    expect(merged.map((e) => e.event_id)).toEqual(["a", "b", "c", "d"]);
  });

  it("detects stale heartbeats", () => {
    const now = Date.parse("2026-11-04T12:00:30Z");
    expect(
      isHeartbeatStale("2026-11-04T12:00:00Z", 30, now),
    ).toBe(false);
    expect(
      isHeartbeatStale("2026-11-04T11:59:00Z", 30, now),
    ).toBe(true);
    expect(isHeartbeatStale(null, 30, now)).toBe(true);
  });
});
