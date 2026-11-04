"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ObservabilityEvent } from "@/lib/observability/types";

export function ReplayControls({
  enabled,
  playing,
  index,
  total,
  speed,
  gap,
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
  onPlay: () => void;
  onPause: () => void;
  onPrev: () => void;
  onNext: () => void;
  onSpeed: (speed: 0.5 | 1 | 2) => void;
  onScrub: (index: number) => void;
  onExit: () => void;
}) {
  if (!enabled) return null;
  return (
    <div className="mb-4 rounded-xl border border-[hsl(var(--ai)/0.45)] bg-[hsl(var(--ai)/0.08)] p-3">
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
        <p className="mb-2 text-xs text-[hsl(var(--warning))]">
          Replay history is empty or truncated by ledger retention.
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
          <Button
            key={value}
            size="sm"
            variant={speed === value ? "default" : "ghost"}
            onClick={() => onSpeed(value)}
          >
            {value}x
          </Button>
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
    </div>
  );
}

function EventHint({ events }: { events: ObservabilityEvent[] }) {
  void events;
  return null;
}
