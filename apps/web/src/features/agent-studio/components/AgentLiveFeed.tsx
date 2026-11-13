"use client";

import { Activity, AlertTriangle, CandlestickChart, Shield, Sparkles } from "lucide-react";

import { AnimatedList } from "@/components/magicui/animated-list";
import { Badge } from "@/components/ui/badge";
import type { ObservabilityEvent } from "@/lib/observability/types";
import { cn } from "@/lib/utils";

import { categorizeEvent } from "../lib/workflow-projector";

function iconFor(type: string) {
  const cat = categorizeEvent(type);
  if (cat === "MARKET") return CandlestickChart;
  if (cat === "ANALYSIS" || cat === "SIGNAL") return Sparkles;
  if (cat === "RISK") return Shield;
  if (cat === "ERROR") return AlertTriangle;
  return Activity;
}

function friendlyTitle(type: string) {
  return type
    .replace(/\./g, " · ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Tweet-card-style event cards with Magic UI Animated List. */
export function AgentLiveFeed({
  events,
  selectedEventId,
  onSelect,
}: {
  events: ObservabilityEvent[];
  selectedEventId: string | null;
  onSelect: (id: string) => void;
}) {
  const latest = [...events].slice(-8).reverse();

  return (
    <div className="rounded-3xl border border-border bg-muted/40 p-5 md:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-brand">
            Live feed
          </p>
          <h2 className="mt-1 text-xl font-medium tracking-tight text-foreground">Agent events</h2>
          <p className="text-sm text-foreground">Newest evidence from the worker</p>
        </div>
        <Badge variant="outline" className="rounded-full">
          {latest.length} shown
        </Badge>
      </div>

      {latest.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border px-4 py-10 text-center text-sm text-foreground">
          No events yet. When the worker publishes heartbeats or signals, they appear here.
        </p>
      ) : (
        <AnimatedList delay={450} className="max-h-[420px] overflow-y-auto pr-1">
          {latest.map((event) => {
            const Icon = iconFor(event.event_type);
            const selected = selectedEventId === event.event_id;
            return (
              <button
                key={event.event_id}
                type="button"
                onClick={() => onSelect(event.event_id)}
                className={cn(
                  "w-full rounded-2xl border p-4 text-left transition-colors",
                  selected
                    ? "border-border bg-muted/40"
                    : "border-border bg-muted/60 hover:border-border",
                )}
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border bg-muted/40">
                    <Icon className="h-4 w-4 text-brand" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium text-foreground">
                        {friendlyTitle(event.event_type)}
                      </p>
                      <span className="text-[10px] text-foreground">
                        {new Date(event.occurred_at).toLocaleTimeString()}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-foreground">
                      {event.message || "Evidence event from agent runtime"}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge variant="secondary" className="rounded-full text-[10px]">
                        {categorizeEvent(event.event_type)}
                      </Badge>
                      {event.env_scope?.toLowerCase().includes("sample") ? (
                        <Badge variant="sample" className="rounded-full text-[10px]">
                          SAMPLE
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </AnimatedList>
      )}
    </div>
  );
}
