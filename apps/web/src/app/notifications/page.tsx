"use client";

import { useMemo, useState } from "react";
import { BellOff, RefreshCw } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { EmptyState, ErrorState, ReasonList, SettingsTemplate, StatusBadge, StatusIndicator } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { getJson } from "@/lib/api/client";
import { fetchAutonomySnapshot } from "@/lib/api/orchestrator";
import { formatDateTime, formatRelative } from "@/lib/formatting/time";
import { useExecutionState } from "@/providers/ExecutionStateProvider";
import { cn } from "@/lib/utils";

type Severity = "info" | "warning" | "critical";
type Category = "risk" | "supervisor" | "news" | "system";
type Notification = { id: string; at: number | null; severity: Severity; category: Category; title: string; detail: string | null; codes: string[] };

type NewsAlert = { alert_id: string; headline?: string; severity?: string; symbols?: string[]; detected_at_ms?: number | null; status?: string; explanation?: string };

const TONE: Record<Severity, "info" | "warn" | "danger"> = { info: "info", warning: "warn", critical: "danger" };

export default function NotificationsPage() {
  const exec = useExecutionState();
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 20_000 });
  const alerts = usePolledResource((init) => getJson<{ enabled: boolean; items: NewsAlert[] }>("/api/news/alerts?limit=25", init), { intervalMs: 60_000 });
  const [filter, setFilter] = useState<"all" | Category>("all");

  const items = useMemo<Notification[]>(() => {
    const out: Notification[] = [];
    const snap = autonomy.data;
    if (snap) {
      if (snap.risk.halted) out.push({ id: "risk-halt", at: snap.session.heartbeat_ms, severity: "critical", category: "risk", title: "Paper risk halt is active", detail: null, codes: [snap.risk.halt_reason ?? "HALTED"] });
      else if (snap.risk.block_new_exposure) out.push({ id: "risk-block", at: snap.session.heartbeat_ms, severity: "warning", category: "risk", title: "New paper entries are blocked", detail: null, codes: [snap.risk.halt_reason ?? "block_new_exposure"] });
      if (snap.session.last_error) out.push({ id: "sup-error", at: snap.session.heartbeat_ms, severity: "critical", category: "supervisor", title: "Supervisor reported an error", detail: null, codes: [snap.session.last_error] });
      if (snap.enabled && !snap.worker_running) out.push({ id: "worker-off", at: snap.session.heartbeat_ms, severity: "warning", category: "supervisor", title: "Paper worker is offline", detail: "The supervisor feature is on but no worker loop is running.", codes: [] });
      for (const d of snap.decision_queue.filter((d) => d.action === "BLOCKED" || (d.risk_verdict && d.risk_verdict !== "APPROVED")).slice(-10)) {
        out.push({ id: `veto-${d.decision_id}`, at: d.timestamp_ms, severity: "info", category: "risk", title: `Entry vetoed · ${d.symbol} ${d.action}`, detail: d.explanation, codes: d.reason_codes || [] });
      }
      for (const e of snap.protective_events.filter((e) => e.protective).slice(-10)) {
        out.push({ id: `prot-${e.event_id}`, at: e.created_ms, severity: "warning", category: "supervisor", title: `Protective exit · ${e.exit_reason ?? e.event_type}`, detail: typeof e.payload?.symbol === "string" ? String(e.payload.symbol) : null, codes: [] });
      }
    }
    if (exec.data) {
      if (exec.data.marketStale) out.push({ id: "market-stale", at: exec.data.fetchedAt, severity: "warning", category: "system", title: "Public market data is stale", detail: null, codes: ["STALE_DATA"] });
      if (exec.data.live === "armed_approve_required") out.push({ id: "live-armed", at: exec.data.fetchedAt, severity: "critical", category: "system", title: `LIVE lane armed on Bybit ${exec.data.bybitEnv}`, detail: "Every live order still requires an explicit Approve in the Orchestrator chat. Revoke by clearing AGENT_ALLOW_LIVE / MAINNET_TRADING_ENABLED.", codes: [] });
    }
    for (const a of alerts.data?.items ?? []) {
      const sev = String(a.severity || "").toUpperCase();
      out.push({ id: `news-${a.alert_id}`, at: a.detected_at_ms ?? null, severity: sev === "CRITICAL" ? "critical" : sev === "HIGH" ? "warning" : "info", category: "news", title: a.headline || "News alert", detail: [a.symbols?.join(", "), a.explanation].filter(Boolean).join(" · ") || null, codes: [] });
    }
    const filtered = filter === "all" ? out : out.filter((n) => n.category === filter);
    return filtered.sort((a, b) => (b.at ?? 0) - (a.at ?? 0));
  }, [autonomy.data, alerts.data, exec.data, filter]);

  const loading = autonomy.loading && exec.loading;

  return (
    <SettingsTemplate
      title="Notifications"
      description="Risk halts, supervisor errors, protective exits, vetoes, news alerts and system warnings, from backend facts only. Nothing here is sample data."
      modes={["readonly"]}
      actions={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => { void autonomy.refresh(); void alerts.refresh(); }} disabled={autonomy.refreshing}>
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", autonomy.refreshing && "animate-spin")} aria-hidden />
          Refresh
        </Button>
      }
      toolbar={
        <Tabs value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
          <TabsList className="w-auto" aria-label="Notification category">
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="risk">Risk</TabsTrigger>
            <TabsTrigger value="supervisor">Supervisor</TabsTrigger>
            <TabsTrigger value="news">News</TabsTrigger>
            <TabsTrigger value="system">System</TabsTrigger>
          </TabsList>
        </Tabs>
      }
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <StatusIndicator status={alerts.data ? (alerts.data.enabled ? "RUNNING" : "STOPPED") : "UNKNOWN"} label={alerts.data ? (alerts.data.enabled ? "News alert engine on" : "News alert engine off") : "News alerts unknown"} />
        <span>· Telegram and auto-collection follow the API configuration.</span>
      </div>
      {autonomy.error && !autonomy.data ? <ErrorState title="Supervisor feed unavailable" code={autonomy.error.code} at={autonomy.error.at} onRetry={() => void autonomy.refresh()} compact /> : null}

      <SectionPanel title={`${items.length} notification${items.length === 1 ? "" : "s"}`} description="Newest first. Duplicates are collapsed by id.">
        {loading ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}</div>
        ) : items.length === 0 ? (
          <EmptyState title="No notifications" badge="Clear" icon={<BellOff className="h-4 w-4 text-muted-foreground" aria-hidden />} description="No halts, errors, vetoes, protective exits or alerts are reported right now." />
        ) : (
          <ol className="space-y-2">
            {items.map((n) => (
              <li key={n.id} className="rounded-2xl border border-border bg-muted/30 px-4 py-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{n.title}</p>
                    {n.detail ? <p className="mt-1 text-xs text-muted-foreground">{n.detail}</p> : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <StatusBadge label={n.severity} tone={TONE[n.severity]} />
                    <StatusBadge label={n.category} tone="neutral" />
                  </div>
                </div>
                {n.codes.length ? <ReasonList codes={n.codes} compact max={3} className="mt-2" /> : null}
                <p className="mt-2 font-mono text-[10px] text-muted-foreground" title={formatDateTime(n.at)}>{formatRelative(n.at)} · {n.id}</p>
              </li>
            ))}
          </ol>
        )}
      </SectionPanel>
    </SettingsTemplate>
  );
}
