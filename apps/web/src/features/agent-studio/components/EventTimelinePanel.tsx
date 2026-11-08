"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Pause, Play } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ObservabilityEvent } from "@/lib/observability/types";

import { categorizeEvent } from "../lib/workflow-projector";
import type { EventCategory } from "../types";

async function copyText(value: string): Promise<void> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
  } catch {
    // fall through
  }
  try {
    const el = document.createElement("textarea");
    el.value = value;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  } catch {
    // Clipboard unavailable — silent fail; avoid console overlay noise.
  }
}

const CATEGORIES: Array<EventCategory | "ALL"> = [
  "ALL",
  "MARKET",
  "ANALYSIS",
  "SIGNAL",
  "RISK",
  "ORDER",
  "SYSTEM",
  "ERROR",
];

export function EventTimelinePanel({
  events,
  selectedEventId,
  onSelect,
  onJumpStage,
  onJumpChart,
  candleTimes,
}: {
  events: ObservabilityEvent[];
  selectedEventId: string | null;
  onSelect: (eventId: string) => void;
  onJumpStage: (eventType: string) => void;
  onJumpChart?: (eventId: string) => void;
  candleTimes?: Set<number>;
}) {
  const reduce = useReducedMotion();
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("ALL");
  const [query, setQuery] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...events]
      .reverse()
      .filter((event) => {
        const cat = categorizeEvent(event.event_type);
        if (category !== "ALL" && cat !== category) return false;
        if (!q) return true;
        return (
          event.event_type.toLowerCase().includes(q) ||
          event.message.toLowerCase().includes(q) ||
          (event.symbol || "").toLowerCase().includes(q) ||
          event.event_id.toLowerCase().includes(q)
        );
      })
      .slice(0, 80);
  }, [events, category, query]);

  return (
    <div className="rounded-xl border border-[#253348] bg-[#101827] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-display text-lg">Activity timeline</h2>
          <p className="text-xs text-muted-foreground">
            Deduped by event_id · times are event occurred_at
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setAutoScroll((v) => !v)}
          aria-pressed={autoScroll}
        >
          {autoScroll ? <Pause className="mr-1 h-3.5 w-3.5" /> : <Play className="mr-1 h-3.5 w-3.5" />}
          {autoScroll ? "Pause auto-follow" : "Resume"}
        </Button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        {CATEGORIES.map((item) => (
          <Button
            key={item}
            size="sm"
            variant={category === item ? "secondary" : "ghost"}
            onClick={() => setCategory(item)}
          >
            {item}
          </Button>
        ))}
      </div>
      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search type, symbol, message, event id"
        className="mb-3"
        aria-label="Search events"
      />

      <ScrollArea className="h-[320px] pr-3">
        {filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events match this filter.</p>
        ) : (
          <div className="flex flex-col">
            <AnimatePresence initial={false}>
              {filtered.map((event) => {
                const cat = categorizeEvent(event.event_type);
                const selected = selectedEventId === event.event_id;
                return (
                  <motion.div
                    key={event.event_id}
                    role="button"
                    tabIndex={0}
                    layout={!reduce}
                    initial={reduce ? false : { opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduce ? undefined : { opacity: 0, height: 0 }}
                    transition={{ duration: 0.18 }}
                    className={`mb-2 w-full cursor-pointer rounded-lg border px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      selected
                        ? "border-primary bg-primary/10"
                        : "border-[#253348] bg-[#080D19]/60 hover:border-primary/40"
                    }`}
                    onClick={() => {
                      onSelect(event.event_id);
                      onJumpStage(event.event_type);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelect(event.event_id);
                        onJumpStage(event.event_type);
                      }
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <Badge variant="outline">{cat}</Badge>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {new Date(event.occurred_at).toISOString()}
                      </span>
                    </div>
                    <p className="mt-1 text-xs font-medium">{event.event_type}</p>
                    <p className="text-sm text-muted-foreground">{event.message}</p>
                    <div className="mt-1 flex flex-wrap gap-2 font-mono text-[10px] text-muted-foreground">
                      <span>{event.symbol || "—"}</span>
                      <span>corr={event.correlation_id || "—"}</span>
                      <button
                        type="button"
                        className="underline-offset-2 hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          void copyText(event.event_id);
                        }}
                      >
                        copy id
                      </button>
                      {onJumpChart ? (
                        <button
                          type="button"
                          className="underline-offset-2 hover:underline"
                          onClick={(e) => {
                            e.stopPropagation();
                            const startMs = event.payload.candle_start_ms;
                            const time =
                              typeof startMs === "number" ? Math.floor(startMs / 1000) : null;
                            if (
                              time == null ||
                              (candleTimes && candleTimes.size > 0 && !candleTimes.has(time))
                            ) {
                              return;
                            }
                            onJumpChart(event.event_id);
                          }}
                        >
                          show on chart
                        </button>
                      ) : null}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
