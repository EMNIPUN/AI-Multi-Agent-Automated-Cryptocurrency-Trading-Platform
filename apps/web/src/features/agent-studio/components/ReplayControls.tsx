"use client";

import { motion, useReducedMotion } from "motion/react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ObservabilityEvent } from "@/lib/observability/types";

import { studioSpring } from "../lib/motion-tokens";

export function ReplayControls({
  enabled,
  playing,
  index,
  total,
  speed,
  gap,
  gapCount = 0,
  largestGapMs = 0,
  onPlay,
  onPause,
  onPrev,
  onNext,
  onSpeed,
  onScrub,
  onExit,
}: {
  enabled: boolean;
  playing: boolean;
  index: number;
  total: number;
  speed: 0.5 | 1 | 2;
  gap: boolean;
  gapCount?: number;
  largestGapMs?: number;
  onPlay: () => void;
  onPause: () => void;
  onPrev: () => void;
  onNext: () => void;
  onSpeed: (speed: 0.5 | 1 | 2) => void;
  onScrub: (index: number) => void;
  onExit: () => void;
}) {
  const reduce = useReducedMotion();
  if (!enabled) return null;
  const largestMinutes = Math.round(largestGapMs / 60_000);
  return (
    <motion.div
      layout={!reduce}
      className="mb-4 rounded-2xl border border-[hsl(var(--ai)/0.45)] bg-[hsl(var(--ai)/0.08)] p-3 backdrop-blur-sm"
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Badge variant="ai">REPLAY</Badge>
          <p className="text-sm">Historical evidence only — no live execution.</p>
        </div>
        <Button size="sm" variant="outline" onClick={onExit}>
          Return to live
        </Button>
      </div>
      {gap ? (
        <p className="mb-2 text-xs text-[hsl(var(--warning))]" role="status">
          {total === 0
            ? "Replay history is empty or truncated by ledger retention."
            : `Replay gap warning: ${gapCount} chronological gap${gapCount === 1 ? "" : "s"} detected${
                largestMinutes > 0 ? ` (largest ~${largestMinutes}m)` : ""
              }. Missing intervals are not invented.`}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onPrev} disabled={index <= 0}>
          Previous
        </Button>
        {playing ? (
          <Button size="sm" onClick={onPause}>
            Pause
          </Button>
        ) : (
          <Button size="sm" onClick={onPlay} disabled={total === 0}>
            Play
          </Button>
        )}
        <Button size="sm" variant="secondary" onClick={onNext} disabled={index >= total - 1}>
          Next
        </Button>
        {([0.5, 1, 2] as const).map((value) => (
          <motion.div key={value} whileTap={reduce ? undefined : { scale: 0.96 }} transition={studioSpring}>
            <Button
              size="sm"
              variant={speed === value ? "default" : "ghost"}
              onClick={() => onSpeed(value)}
            >
              {value}x
            </Button>
          </motion.div>
        ))}
        <input
          aria-label="Replay scrubber"
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          value={index}
          onChange={(e) => onScrub(Number(e.target.value))}
          className="min-w-[160px] flex-1"
        />
        <span className="font-mono text-xs text-muted-foreground">
          {total === 0 ? "0/0" : `${index + 1}/${total}`}
        </span>
      </div>
      <EventHint events={[]} />
    </motion.div>
  );
}

function EventHint({ events }: { events: ObservabilityEvent[] }) {
  void events;
  return null;
}
