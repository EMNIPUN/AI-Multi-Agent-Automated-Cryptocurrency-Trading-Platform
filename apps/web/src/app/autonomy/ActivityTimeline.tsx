"use client";

import { useMemo } from "react";
import { Activity, Bot, ShieldOff, Zap } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { ReasonList, StatusIndicator } from "@/components/design-system";
import { Skeleton } from "@/components/ui/skeleton";
import type { AutonomySnapshot } from "@/lib/api/orchestrator";
import { formatDateTime, formatRelative } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

type Item = {
  id: string;
  at: number | null;
  kind: "decision" | "veto" | "fill" | "protective" | "worker";
  title: string;
  detail: string | null;
  codes: string[];
};

const ICON = { decision: Bot, veto: ShieldOff, fill: Zap, protective: ShieldOff, worker: Activity } as const;
const TONE = { decision: "text-brand", veto: "text-loss", fill: "text-profit", protective: "text-warning", worker: "text-muted-foreground" } as const;

/** Merges decision ring, protective events and fills into one ordered timeline of backend events. */
export function buildTimeline(snap: AutonomySnapshot | null): Item[] {
  if (!snap) return [];
  const items: Item[] = [];
  for (const d of snap.decision_queue) {
    const vetoed = d.action === "BLOCKED" || (d.risk_verdict && d.risk_verdict !== "APPROVED");
    items.push({
      id: `d-${d.decision_id}`,
      at: d.timestamp_ms,
      kind: vetoed ? "veto" : "decision",
      title: `${d.action} · ${d.symbol}${d.risk_verdict ? ` · risk ${d.risk_verdict}` : ""}`,
      detail: d.explanation,
      codes: d.reason_codes || [],
    });
  }
  for (const e of snap.protective_events) {
    items.push({
      id: `e-${e.event_id}`,
      at: e.created_ms,
      kind: e.protective ? "protective" : "fill",
      title: `${String(e.event_type).replace(/_/g, " ")}${e.exit_reason ? ` · ${e.exit_reason}` : ""}`,
      detail: typeof e.payload?.symbol === "string" ? String(e.payload.symbol) : null,
      codes: e.exit_reason ? [e.exit_reason] : [],
    });
  }
  if (snap.session.last_error) {
    items.push({ id: "worker-error", at: snap.session.heartbeat_ms, kind: "worker", title: "Worker reported an error", detail: null, codes: [snap.session.last_error] });
  }
  return items.sort((a, b) => (b.at ?? 0) - (a.at ?? 0)).slice(0, 40);
}

export function ActivityTimeline({ snap, loading }: { snap: AutonomySnapshot | null; loading: boolean }) {
  const items = useMemo(() => buildTimeline(snap), [snap]);
  return (
    <SectionPanel title="Activity timeline" description="Decisions, vetoes, fills and protective exits as the supervisor recorded them. Newest first.">
      {loading && !snap ? (
        <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}</div>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">No recorded activity yet. Events appear after the worker evaluates a confirmed candle.</p>
      ) : (
        <ol className="relative space-y-3 pl-5 before:absolute before:left-[7px] before:top-2 before:h-[calc(100%-1rem)] before:w-px before:bg-border">
          {items.map((item) => {
            const Icon = ICON[item.kind];
            return (
              <li key={item.id} className="relative">
                <span className={cn("absolute -left-5 top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-border bg-card", TONE[item.kind])} aria-hidden>
                  <Icon className="h-2.5 w-2.5" />
                </span>
                <div className="rounded-xl border border-border bg-muted/30 px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-medium text-foreground">{item.title}</p>
                    <span className="flex items-center gap-2 text-[10px] text-muted-foreground">
                      <StatusIndicator status={item.kind === "veto" ? "BLOCKED" : item.kind === "fill" ? "OK" : item.kind === "worker" ? "FAILED" : "IDLE"} label={item.kind} />
                      <span title={formatDateTime(item.at)}>{formatRelative(item.at)}</span>
                    </span>
                  </div>
                  {item.detail ? <p className="mt-1 text-[11px] text-muted-foreground">{item.detail}</p> : null}
                  {item.codes.length ? <ReasonList codes={item.codes} compact max={3} className="mt-1.5" /> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </SectionPanel>
  );
}
