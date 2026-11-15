"use client";

import Link from "next/link";
import { useState } from "react";
import { Activity, AlertTriangle, History } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { DataTable, FinancialValue, ResearchTemplate, StatusBadge, StatusIndicator, type DataTableColumn } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SignalsPanel } from "@/features/agent-studio/components/SignalsPanel";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { getJson } from "@/lib/api/client";
import type { BacktestRunSummary } from "@/lib/backtest/types";
import { formatDateTime } from "@/lib/formatting/time";
import { STRATEGY_CATALOG, versionMatches, type StrategyEntry } from "@/lib/strategy/catalog";
import { cn } from "@/lib/utils";

type SignalStatus = { strategy_version?: string; mode?: string; auto_engine?: { state?: string; configured_symbols?: string[]; configured_interval?: string } };

function datasetKind(run: BacktestRunSummary): "Synthetic" | "Historical" | "Offline" {
  if (run.dataset_label?.includes("SYNTHETIC")) return "Synthetic";
  if (run.dataset_label?.includes("HISTORICAL")) return "Historical";
  return "Offline";
}

const RUN_COLUMNS: DataTableColumn<BacktestRunSummary>[] = [
  { id: "created", header: "Run", cell: (r) => <span className="text-muted-foreground">{formatDateTime(r.created_ms)}</span>, accessor: (r) => r.created_ms ?? 0 },
  { id: "symbol", header: "Symbol", cell: (r) => <span className="font-medium text-foreground">{r.symbol ?? "—"} · {r.interval ?? "—"}m</span>, accessor: (r) => r.symbol ?? "" },
  { id: "dataset", header: "Dataset", cell: (r) => <StatusBadge label={datasetKind(r)} tone={datasetKind(r) === "Synthetic" ? "warn" : "info"} />, accessor: (r) => datasetKind(r) },
  { id: "pipeline", header: "Pipeline", cell: (r) => <span className="font-mono text-muted-foreground">{r.pipeline_version ?? r.engine_version ?? "—"}</span>, accessor: (r) => r.pipeline_version ?? "", hideBelow: "md" },
  { id: "candles", header: "Candles", align: "right", cell: (r) => <span className="font-mono">{r.candle_count ?? "—"}</span>, accessor: (r) => r.candle_count ?? 0, hideBelow: "lg" },
  { id: "trades", header: "Closed trades", align: "right", cell: (r) => <span className="font-mono">{r.closed_trades ?? "—"}</span>, accessor: (r) => r.closed_trades ?? 0 },
  { id: "pnl", header: "Net realized", align: "right", cell: (r) => <FinancialValue value={r.net_realized_pnl} digits={2} signed showPlus size="xs" />, accessor: (r) => r.net_realized_pnl ?? "" },
  { id: "status", header: "Status", cell: (r) => <StatusIndicator status={r.status === "completed" ? "OK" : r.status} label={r.status} />, accessor: (r) => r.status },
];

function ParamList({ title, params }: { title: string; params: StrategyEntry["risk"] }) {
  if (params.length === 0) return null;
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      <dl className="space-y-1.5">
        {params.map((p) => (
          <div key={p.label} className="flex items-start justify-between gap-3 rounded-lg border border-border bg-muted/40 px-3 py-1.5 text-xs">
            <dt className="text-muted-foreground">{p.label}{p.note ? <span className="block text-[10px] opacity-80">{p.note}</span> : null}</dt>
            <dd className="shrink-0 text-right font-mono text-foreground">{p.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default function StrategyResearchPage() {
  const status = usePolledResource((init) => getJson<SignalStatus>("/api/signals/status", init), { intervalMs: 0 });
  const runs = usePolledResource((init) => getJson<{ items: BacktestRunSummary[] }>("/api/backtests/runs?limit=50&offset=0", init), { intervalMs: 0 });
  const [selectedId, setSelectedId] = useState(STRATEGY_CATALOG[0].id);
  const selected = STRATEGY_CATALOG.find((s) => s.id === selectedId) ?? STRATEGY_CATALOG[0];
  const liveVersion = status.data?.strategy_version ?? null;
  const match = versionMatches(selected, liveVersion);
  const runRows = runs.data?.items ?? [];

  return (
    <ResearchTemplate
      title="Strategy Research"
      description="What each strategy does, which markets it supports, its indicator and risk configuration, and the backtest runs recorded for it. Signals are research output, never orders."
      modes={["readonly", "paper"]}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm" className="rounded-full">
            <Link href="/agents/live"><Activity className="mr-1.5 h-3.5 w-3.5" aria-hidden />Live analysis</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="rounded-full">
            <Link href="/backtesting"><History className="mr-1.5 h-3.5 w-3.5" aria-hidden />Backtesting</Link>
          </Button>
        </div>
      }
    >
      <div className="grid min-w-0 gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <SectionPanel title="Catalog" className="p-4">
          <ul className="space-y-1.5" aria-label="Strategies">
            {STRATEGY_CATALOG.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(s.id)}
                  aria-current={s.id === selected.id ? "true" : undefined}
                  className={cn("w-full rounded-xl border px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", s.id === selected.id ? "border-brand/50 bg-brand/10" : "border-border bg-muted/30 hover:bg-muted/60")}
                >
                  <p className="text-sm font-medium text-foreground">{s.name}</p>
                  <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <span className="font-mono">{s.version}</span>
                    <StatusBadge label={s.status === "product" ? "Product path" : "Legacy"} tone={s.status === "product" ? "ok" : "neutral"} className="px-1.5 py-0 text-[10px]" />
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </SectionPanel>

        <div className="min-w-0 space-y-4">
          <SectionPanel title={selected.name} description={selected.summary}>
            <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="font-mono">source: {selected.source}</span>
              {status.loading ? <Skeleton className="h-5 w-32 rounded-full" /> : liveVersion ? (
                <StatusBadge label={`backend strategy_version ${liveVersion}`} tone={match === false ? "warn" : "neutral"} />
              ) : (
                <StatusBadge label="backend version unavailable" tone="stale" />
              )}
              {status.data?.auto_engine?.state ? <StatusIndicator status={status.data.auto_engine.state === "running" ? "RUNNING" : "STOPPED"} label={`Auto signal engine ${status.data.auto_engine.state}`} /> : null}
            </div>
            {match === false ? (
              <p className="mb-4 flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-foreground" role="alert">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
                This catalog describes {selected.version}, but the backend reports {liveVersion}. Parameters below may be out of date — check {selected.source}.
              </p>
            ) : null}
            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Supported markets</p>
                <p className="mt-1 text-foreground">{selected.markets.join(" · ")}</p>
              </div>
              <div className="rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Intervals</p>
                <p className="mt-1 font-mono text-foreground">{selected.intervals.join(" · ")}</p>
              </div>
            </div>
            {selected.agents.length > 0 ? (
              <div className="mb-4">
                <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Indicator agents</p>
                <div className="cn-thin-scroll overflow-x-auto rounded-xl border border-border">
                  <table className="w-full min-w-[32rem] text-xs">
                    <caption className="sr-only">Indicator agents and weights</caption>
                    <thead className="bg-muted/40">
                      <tr className="border-b border-border text-left text-muted-foreground">
                        <th scope="col" className="px-3 py-2 font-medium">Agent</th>
                        <th scope="col" className="px-3 py-2 text-right font-medium">Weight</th>
                        <th scope="col" className="px-3 py-2 font-medium">Rule</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.agents.map((a) => (
                        <tr key={a.id} className="border-b border-border/60 last:border-0">
                          <td className="px-3 py-2 font-medium text-foreground">{a.name}</td>
                          <td className="px-3 py-2 text-right font-mono">{a.weight ?? "gate"}</td>
                          <td className="px-3 py-2 text-muted-foreground">{a.rule}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
            <div className="grid gap-4 lg:grid-cols-3">
              <ParamList title="Decision rules" params={selected.decision} />
              <ParamList title="Risk constraints" params={selected.risk} />
              <ParamList title="Regime gate" params={selected.regime} />
            </div>
            <ul className="mt-4 space-y-1 text-[11px] text-muted-foreground">
              {selected.limits.map((l) => <li key={l}>• {l}</li>)}
            </ul>
          </SectionPanel>

          <SectionPanel title="Historical results" description="Backtest runs recorded by the backtest API. Synthetic fixtures are labelled and say nothing about live markets.">
            {runs.loading ? (
              <Skeleton className="h-40 rounded-xl" />
            ) : runs.error ? (
              <p className="text-xs text-muted-foreground">Backtest runs unavailable ({runs.error.code}). Enable BACKTEST_READ_API_ENABLED on the API to list them.</p>
            ) : (
              <DataTable rows={runRows} columns={RUN_COLUMNS} rowKey={(r) => r.run_id} caption="Backtest runs" initialSort={{ id: "created", desc: true }} pageSize={10} emptyState="No backtest runs recorded." />
            )}
          </SectionPanel>
        </div>
      </div>

      <SectionPanel title="Signal engine" description="Evaluate and browse closed-candle signal history through the existing 4B/4C adapters. No trading permissions.">
        <SignalsPanel symbol="BTCUSDT" category="linear" interval="15" />
      </SectionPanel>
    </ResearchTemplate>
  );
}
