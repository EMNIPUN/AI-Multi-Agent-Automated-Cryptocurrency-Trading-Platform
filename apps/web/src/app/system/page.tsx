"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { DataFreshness, ErrorState, ExecutionMode, MetricCard, MetricCardGrid, OverviewTemplate, StatusIndicator } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { getJson, type ApiResult } from "@/lib/api/client";
import { fetchDiagnostics, fetchOrchestratorStatus } from "@/lib/api/orchestrator";
import { useExecutionState } from "@/providers/ExecutionStateProvider";
import { cn } from "@/lib/utils";

type Probe = { id: string; label: string; href: string; status: "ok" | "off" | "gated" | "down"; detail: string; at: number };

async function probeAll(init: RequestInit): Promise<ApiResult<Probe[]>> {
  const targets: { id: string; label: string; href: string; path: string; enabledKey?: string; storageKey?: string }[] = [
    { id: "orch", label: "Orchestrator API", href: "/orchestrator", path: "/api/orchestrator/status", enabledKey: "enabled" },
    { id: "paper", label: "Paper read API", href: "/paper", path: "/api/paper/status", enabledKey: "paper_read_api_enabled" },
    { id: "backtest", label: "Backtest API", href: "/backtesting", path: "/api/backtests/status", enabledKey: "enabled" },
    { id: "news", label: "News intelligence", href: "/news", path: "/api/news/status", enabledKey: "enabled", storageKey: "storage_available" },
    { id: "llm", label: "LLM advisory", href: "/llm", path: "/api/llm/status", enabledKey: "enabled", storageKey: "storage_available" },
    { id: "market", label: "Public market data", href: "/markets", path: "/api/market/status" },
    { id: "wallet", label: "Exchange wallet read", href: "/portfolio", path: "/api/exchange/wallet" },
    { id: "signals", label: "Signal engine", href: "/strategy", path: "/api/signals/status" },
  ];
  const results = await Promise.all(targets.map((t) => getJson<Record<string, unknown>>(t.path, init)));
  if (results.some((r) => !r.ok && r.code === "aborted")) return { ok: false, status: 0, code: "aborted", message: "cancelled", at: Date.now() };
  const probes = targets.map<Probe>((t, i) => {
    const r = results[i];
    if (!r.ok) {
      if (t.id === "wallet" && (r.status === 401 || r.status === 403)) return { ...t, status: "gated", detail: `gated · ${r.code}`, at: r.at };
      return { ...t, status: "down", detail: r.status === 0 ? "unreachable" : `http ${r.status} · ${r.code}`, at: r.at };
    }
    const enabled = t.enabledKey ? r.data[t.enabledKey] : true;
    const storage = t.storageKey ? r.data[t.storageKey] : undefined;
    const detailParts = [enabled === false ? "feature off" : "enabled", storage === undefined ? null : storage ? "storage ok" : "storage unavailable"].filter(Boolean);
    return { ...t, status: enabled === false ? "off" : "ok", detail: detailParts.join(" · "), at: r.at };
  });
  return { ok: true, status: 200, at: Date.now(), data: probes };
}

export default function SystemHealthPage() {
  const exec = useExecutionState();
  const probes = usePolledResource(probeAll, { intervalMs: 30_000 });
  const status = usePolledResource(fetchOrchestratorStatus, { intervalMs: 15_000 });
  const diag = usePolledResource(fetchDiagnostics, { intervalMs: 60_000 });
  const list = probes.data ?? [];
  const healthy = list.filter((p) => p.status === "ok" || p.status === "gated").length;
  const openai = diag.data?.openai ?? null;

  return (
    <OverviewTemplate
      title="System Health"
      description="Reachability and feature gates of every backend adapter, worker heartbeat, storage and model status. Read-only; nothing here changes configuration."
      modes={["readonly"]}
      actions={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => { void probes.refresh(); void status.refresh(); void exec.refresh(); }} disabled={probes.refreshing}>
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", probes.refreshing && "animate-spin")} aria-hidden />
          Refresh
        </Button>
      }
    >
      <MetricCardGrid>
        <MetricCard label="Adapters reachable" accent loading={probes.loading} value={<span className="font-mono">{list.length ? `${healthy}/${list.length}` : "—"}</span>} hint={probes.updatedAt ? `probed ${new Date(probes.updatedAt).toLocaleTimeString()}` : undefined} />
        <MetricCard label="Execution lanes" loading={exec.loading} value={<div className="flex flex-wrap gap-1.5"><ExecutionMode mode="paper" /><ExecutionMode mode="testnet" armed={exec.data?.testnet === "armed"} /><ExecutionMode mode="live" armed={exec.data?.live === "armed_approve_required"} /></div>} hint={exec.data ? `Bybit env ${exec.data.bybitEnv} · from /api/automation/status` : "reading gates…"} />
        <MetricCard label="Paper worker" loading={status.loading} value={<StatusIndicator status={status.data?.worker_running ? "RUNNING" : status.data ? "STOPPED" : "UNKNOWN"} label={status.data?.worker_running ? "Running" : status.data ? "Offline" : "Unknown"} size="md" />} hint={<DataFreshness at={status.data?.heartbeat_ms ?? null} staleAfterMs={180_000} label="heartbeat" missingLabel="No heartbeat" />} />
        <MetricCard label="OpenAI orchestrator" loading={diag.loading} value={<StatusIndicator status={openai ? (openai.gates_open ? "RUNNING" : "STOPPED") : "UNKNOWN"} label={openai ? (openai.gates_open ? `Gates open · ${openai.model ?? "model"}` : "Paid calls off") : "Unknown"} size="md" />} hint={openai ? `$${openai.spent_usd_24h.toFixed(4)} / $${openai.daily_budget_usd.toFixed(2)} today · $${openai.remaining_usd_total.toFixed(2)} left` : undefined} />
      </MetricCardGrid>

      {probes.error && !probes.data ? <ErrorState title="Probes failed" code={probes.error.code} at={probes.error.at} onRetry={() => void probes.refresh()} /> : null}

      <SectionPanel title="Adapter status" description="Status comes from each adapter's own status endpoint. 'Gated' means reachable but requires a verified session or server flag.">
        {probes.loading && !probes.data ? (
          <div className="grid gap-3 md:grid-cols-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-2xl" />)}</div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {list.map((p) => (
              <div key={p.id} className="flex min-w-0 items-center justify-between gap-3 rounded-2xl border border-border bg-muted/50 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{p.label}</p>
                  <p className="mt-1 font-mono text-xs text-muted-foreground">{p.detail}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <StatusIndicator status={p.status === "ok" ? "OK" : p.status === "off" ? "STOPPED" : p.status === "gated" ? "BLOCKED" : "FAILED"} label={p.status === "ok" ? "OK" : p.status === "off" ? "Feature off" : p.status === "gated" ? "Gated" : "Down"} />
                  <Button asChild size="sm" variant="ghost" className="rounded-full"><Link href={p.href}>Open</Link></Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionPanel>

      <SectionPanel title="Runtime facts" description="Facts the backend reports; nothing is inferred from the browser.">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
          {[
            ["Supervisor state", status.data?.state ?? "—"],
            ["Session id", status.data?.session_id ?? "none"],
            ["Risk halt", exec.data ? (exec.data.riskHalted ? `yes · ${exec.data.riskHaltReason ?? ""}` : "no") : "—"],
            ["Market connection", exec.data ? `${exec.data.marketConnection}${exec.data.marketStale ? " · stale" : ""}` : "—"],
            ["Live mutate allowed", status.data ? String(Boolean(status.data.live_mutate_allowed)) : "—"],
            ["Bybit mainnet", status.data ? String(Boolean(status.data.bybit_mainnet)) : "—"],
            ["Sources answering", exec.data ? Object.entries(exec.data.sources).filter(([, v]) => v).map(([k]) => k).join(", ") || "none" : "—"],
            ["Client secrets", "none in bundle · keys stay on the API server"],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl border border-border bg-muted/40 px-3 py-2">
              <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{k}</dt>
              <dd className="mt-0.5 truncate font-mono text-xs text-foreground" title={String(v)}>{v}</dd>
            </div>
          ))}
        </dl>
      </SectionPanel>
    </OverviewTemplate>
  );
}
