"use client";

import { useEffect, useMemo, useState } from "react";

import type { AgentSnapshot, ObservabilityEvent } from "@/lib/observability/types";

import { detectReplayGaps, projectStudio, sliceEventsForReplay } from "../lib/workflow-projector";
import type { StudioProjection } from "../types";

export function useReplayState(baseSnap: AgentSnapshot | null, enabled: boolean) {
  const events = useMemo(
    () => (baseSnap ? projectStudio(baseSnap).events : []),
    [baseSnap],
  );
  const gaps = useMemo(() => detectReplayGaps(events), [events]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<0.5 | 1 | 2>(1);

  useEffect(() => {
    if (!enabled) {
      setPlaying(false);
      setIndex(Math.max(0, events.length - 1));
    }
  }, [enabled, events.length]);

  useEffect(() => {
    if (!enabled || !playing || events.length === 0) return;
    const ms = 1000 / speed;
    const id = window.setInterval(() => {
      setIndex((current) => {
        if (current >= events.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, ms);
    return () => window.clearInterval(id);
  }, [enabled, playing, speed, events.length]);

  const replaySnap: AgentSnapshot | null = useMemo(() => {
    if (!enabled || !baseSnap) return null;
    const sliced: ObservabilityEvent[] = sliceEventsForReplay(events, index);
    return {
      ...baseSnap,
      events: sliced,
      notes: [
        ...baseSnap.notes,
        "REPLAY mode — historical evidence only. No live execution.",
      ],
    };
  }, [enabled, baseSnap, events, index]);

  const projection: StudioProjection | null = useMemo(
    () => (replaySnap ? projectStudio(replaySnap) : null),
    [replaySnap],
  );

  return {
    index,
    setIndex,
    playing,
    setPlaying,
    speed,
    setSpeed,
    events,
    projection,
    gap: events.length === 0 || gaps.hasGap,
    gapCount: gaps.gapCount,
    largestGapMs: gaps.largestGapMs,
  };
}
