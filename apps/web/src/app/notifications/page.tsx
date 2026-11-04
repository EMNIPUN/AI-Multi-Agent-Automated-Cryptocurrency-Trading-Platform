"use client";

import { useEffect, useMemo, useState } from "react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { localAgentFixture } from "@/lib/fixtures/agentSnapshot";
import type { AgentSnapshot, ObservabilityEvent } from "@/lib/observability/types";

type Severity = "info" | "warning" | "danger";

const ALERT_TYPES: Record<string, { title: string; severity: Severity }> = {
  "agent.error": { title: "Agent error", severity: "danger" },
  "agent.halted": { title: "Agent halted", severity: "danger" },
  "risk.blocked": { title: "Signal blocked", severity: "warning" },
  "risk.halted": { title: "Risk halt", severity: "danger" },
  "order.reconciliation_required": { title: "Reconciliation required", severity: "warning" },
  "market.candle_rejected": { title: "Invalid market data", severity: "warning" },
};

function severityVariant(severity: Severity) {
  if (severity === "danger") return "danger" as const;
  if (severity === "warning") return "warning" as const;
  return "outline" as const;
}

function formatLocal(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toLocaleString()} · UTC ${date.toISOString()}`;
}

function dedupe(events: ObservabilityEvent[]) {
  const seen = new Set<string>();
  const out: ObservabilityEvent[] = [];
  for (const event of events) {
    if (seen.has(event.event_id)) continue;
    seen.add(event.event_id);
    out.push(event);
  }
  return out;
}

export default function NotificationsPage() {
  const [snap, setSnap] = useState<AgentSnapshot | null>(null);
  const [mode, setMode] = useState<"fixture" | "unavailable">("fixture");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/observability/snapshot?source=sample", { cache: "no-store" });
        if (!res.ok) throw new Error("fail");
        const data = (await res.json()) as AgentSnapshot;
        if (!cancelled) {
          setSnap(data);
          setMode("fixture");
        }
      } catch {
        if (!cancelled) {
          setSnap(localAgentFixture());
          setMode("unavailable");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const alerts = useMemo(() => {
    if (!snap) return [];
    const mapped = dedupe(snap.events).filter((event) => event.event_type in ALERT_TYPES);
    const extra: ObservabilityEvent[] = [];
    if (snap.heartbeat_stale || snap.agent_status === "OFFLINE" || snap.agent_status === "UNKNOWN") {
      extra.push({
        schema_version: snap.schema_version,
        event_id: `heartbeat:${snap.generated_at}`,
        event_type: "agent.error",
        occurred_at: snap.heartbeat_at ?? snap.generated_at,
        env_scope: snap.execution_mode,
        execution_mode: snap.execution_mode,
        message:
          snap.agent_status === "UNKNOWN"
            ? "Agent heartbeat is absent. Status is UNKNOWN."
            : "Agent heartbeat is stale or offline.",
        payload: {},
      });
    }
    return [...extra, ...mapped].sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1));
  }, [snap]);

  if (!snap) {
    return <LogoLoader fullScreen label="Loading notifications…" />;
  }

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Agent, risk, and reconciliation alerts derived from the current snapshot. Duplicate event IDs are dropped."
      />
      <DataModeBanner
        mode={mode}
        notes={[
          snap.data_mode === "live"
            ? "Live private streams stay disabled."
            : "Alerts come from the labeled SAMPLE snapshot, not a private user stream.",
        ]}
      />
      {alerts.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No alerts</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            The current snapshot has no error, halt, blocked-signal, or reconciliation events.
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {alerts.map((event) => {
            const meta = ALERT_TYPES[event.event_type] ?? {
              title: event.event_type,
              severity: "info" as const,
            };
            return (
              <Card key={event.event_id}>
                <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0 pb-2">
                  <CardTitle className="text-base">{meta.title}</CardTitle>
                  <Badge variant={severityVariant(meta.severity)}>{meta.severity}</Badge>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p>{event.message}</p>
                  <p className="font-mono text-xs text-muted-foreground">{formatLocal(event.occurred_at)}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{event.event_id}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
