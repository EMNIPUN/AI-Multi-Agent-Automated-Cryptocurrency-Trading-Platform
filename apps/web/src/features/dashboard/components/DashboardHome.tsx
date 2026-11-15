"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo } from "react";
import { Activity, ArrowRight, Bot, Radio, RefreshCw, ShieldCheck, Sparkles, Wallet } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import {
  DataFreshness,
  EmptyState,
  ErrorState,
  ExecutionMode,
  FinancialValue,
  MetricCard,
  MetricCardGrid,
  OverviewTemplate,
  ReasonList,
  StatusIndicator,
} from "@/components/design-system";
import { NewsAlertStrip } from "@/components/news/NewsAlertStrip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { realizedEquitySeries } from "@/features/dashboard/lib/equity-series";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { fetchAutonomySnapshot, fetchDiagnostics, fetchPaperReport } from "@/lib/api/orchestrator";
import { formatFractionPercent, toNumber } from "@/lib/formatting/decimal";
import { formatDateTime, formatRelative } from "@/lib/formatting/time";
import { useExecutionState } from "@/providers/ExecutionStateProvider";
import { cn } from "@/lib/utils";

const EquityCurveChart = dynamic(
  () => import("@/components/charts/EquityCurveChart").then((m) => m.EquityCurveChart),
  { ssr: false, loading: () => <Skeleton className="h-[240px] w-full rounded-xl" /> },
);

const QUICK_LINKS = [
  { href: "/orchestrator", title: "AI Orchestrator", detail: "Chat control plane · explain decisions", icon: Bot },
  { href: "/autonomy", title: "Autonomous Trading", detail: "Session controls & lifecycle", icon: ShieldCheck },
  { href: "/agents", title: "Agent Workspace", detail: "Pipeline graph & per-agent evidence", icon: Activity },
  { href: "/markets", title: "Markets", detail: "Public candles, book & tape", icon: Radio },
  { href: "/portfolio", title: "Portfolio", detail: "Paper journal vs exchange wallet", icon: Wallet },
  { href: "/llm", title: "LLM Intelligence", detail: "Advisory evaluations only", icon: Sparkles },
] as const;

export function DashboardHome() {
  const exec = useExecutionState();
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 15_000 });
  const report = usePolledResource(fetchPaperReport, { intervalMs: 30_000 });
  const diag = usePolledResource(fetchDiagnostics, { intervalMs: 60_000 });

  const snap = autonomy.data;
  const session = snap?.session;
  const journal = snap?.journal;
  const risk = snap?.risk;
  const latest = snap?.latest_decision ?? null;
  const agents = snap?.agents?.agents ?? [];
  const openai = diag.data?.openai ?? null;

  const equityPoints = useMemo(() => realizedEquitySeries(report.data), [report.data]);
  const initialBalance = toNumber(report.data?.initial_balance);
  const realized = toNumber(journal?.realized_pnl);
  const unrealized = toNumber(journal?.unrealized_pnl);
  const dailyLoss = toNumber(risk?.daily_loss_fraction);
  const dailyLimit = toNumber(risk?.daily_loss_limit_fraction) ?? 0.03;
  const drawdown = toNumber(risk?.drawdown_fraction);
  const drawdownLimit = toNumber(risk?.drawdown_limit_fraction) ?? 0.1;
  const utilization = dailyLoss !== null && dailyLimit > 0 ? Math.min(1, dailyLoss / dailyLimit) : null;

  const decisions = snap?.decision_queue ?? [];
  const vetoes = decisions.filter((d) => d.action === "BLOCKED" || (d.risk_verdict && d.risk_verdict !== "APPROVED"));
  const protective = snap?.protective_events ?? [];
  const loading = autonomy.loading;
  const unavailable = !loading && !snap;

  return (
    <OverviewTemplate
      title="Overview"
      description="What the markets, agents, orchestrator, risk engine and paper journal report right now. Nothing on this page submits an order."
      modes={["paper", "readonly"]}
      actions={
        <>
          <Button variant="outline" size="sm" className="rounded-full" onClick={() => void autonomy.refresh()} disabled={autonomy.refreshing}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", autonomy.refreshing && "animate-spin")} aria-hidden />
            Refresh
          </Button>
          <Button asChild className="rounded-full" variant="secondary">
            <Link href="/orchestrator">
              Open Orchestrator
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" aria-hidden />
            </Link>
          </Button>
        </>
      }
    >
      <NewsAlertStrip />

      {autonomy.error && !snap ? (
        <ErrorState
          title="Supervisor snapshot unavailable"
          code={autonomy.error.code}
          at={autonomy.error.at}
          onRetry={() => void autonomy.refresh()}
          retrying={autonomy.refreshing}
        />
      ) : null}

      {/* Section 1 — Operational status */}
      <SectionPanel title="Operational status" description="Each tile reads one backend fact. Unknown stays unknown.">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatusTile label="Execution mode">
            <div className="flex flex-wrap gap-1.5">
              <ExecutionMode mode="paper" />
              <ExecutionMode mode="live" armed={exec.data?.live === "armed_approve_required"} />
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              {exec.data ? `Bybit ${exec.data.bybitEnv} · testnet ${exec.data.testnet}` : "Reading gates…"}
            </p>
          </StatusTile>
          <StatusTile label="OpenAI Orchestrator">
            <StatusIndicator
              status={diag.loading ? "UNKNOWN" : openai?.gates_open ? "RUNNING" : "STOPPED"}
              label={diag.loading ? "Checking" : openai?.gates_open ? `OpenAI · ${openai?.model ?? "model"}` : "LocalPlanner only"}
            />
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              {openai ? `$${openai.spent_usd_24h.toFixed(4)} / $${openai.daily_budget_usd.toFixed(2)} today` : "spend unavailable"}
            </p>
          </StatusTile>
          <StatusTile label="Agent supervisor">
            <StatusIndicator status={loading ? "UNKNOWN" : session?.state ?? "STOPPED"} pulse detail={session?.worker_running ? "· worker" : undefined} />
            <div className="mt-2">
              <DataFreshness at={session?.heartbeat_ms ?? null} staleAfterMs={180_000} label="heartbeat" missingLabel="No heartbeat" />
            </div>
          </StatusTile>
          <StatusTile label="Risk engine">
            <StatusIndicator
              status={loading ? "UNKNOWN" : risk?.halted ? "HALTED" : risk?.block_new_exposure ? "BLOCKED" : "OK"}
              label={loading ? "Checking" : risk?.halted ? "Halted" : risk?.block_new_exposure ? "Entries blocked" : "Within limits"}
            />
            <p className="mt-2 text-[11px] text-muted-foreground">
              {risk?.halt_reason ? String(risk.halt_reason).replace(/_/g, " ") : "Deterministic veto authority"}
            </p>
          </StatusTile>
          <StatusTile label="Market data">
            <StatusIndicator
              status={exec.loading ? "UNKNOWN" : exec.data?.marketStale ? "STALE" : exec.data?.marketConnection ?? "UNKNOWN"}
              label={exec.data ? exec.data.marketConnection.replace(/_/g, " ") : "Checking"}
            />
            <p className="mt-2 text-[11px] text-muted-foreground">Public Bybit REST/WS · not account connectivity</p>
          </StatusTile>
        </div>
      </SectionPanel>

      {/* Section 2 — Primary KPIs */}
      <MetricCardGrid>
        <MetricCard
          label="Paper equity"
          accent
          loading={loading}
          value={<FinancialValue value={journal?.equity} digits={2} unit="USDT" size="lg" />}
          hint={journal?.available ? `Journal · ${snap?.session.session_id ?? "no session"}` : "Journal unavailable"}
          muted={!journal?.available}
        />
        <MetricCard
          label="Realized / unrealized PnL"
          loading={loading}
          value={
            <span className="flex flex-wrap items-baseline gap-x-2">
              <FinancialValue value={journal?.realized_pnl} digits={2} signed showPlus size="lg" />
              <FinancialValue value={journal?.unrealized_pnl} digits={2} signed showPlus size="sm" prefix={<span className="text-muted-foreground">/</span>} />
            </span>
          }
          hint={`Fees ${journal?.fees_paid ?? "—"} · ${journal?.closed_trades ?? 0} closed`}
        />
        <MetricCard
          label="Active positions"
          loading={loading}
          value={<span className="font-mono">{snap ? (snap.open_position ? 1 : 0) : "—"}</span>}
          hint={snap?.open_position ? `${snap.open_position.symbol} · ${snap.open_position.quantity}` : "No open paper exposure"}
        />
        <MetricCard
          label="Risk utilization"
          loading={loading}
          value={<span className="font-mono">{utilization === null ? "—" : `${Math.round(utilization * 100)}%`}</span>}
          hint={`Daily loss ${formatFractionPercent(dailyLoss)} of ${formatFractionPercent(dailyLimit)} · drawdown ${formatFractionPercent(drawdown)} of ${formatFractionPercent(drawdownLimit)}`}
        />
      </MetricCardGrid>

      {/* Section 3 — Main analytical area */}
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.75fr)]">
        <SectionPanel
          title="Realized paper equity"
          description="Initial balance plus each closed trade, in close order. Open-position mark-to-market is not in this line."
        >
          {report.loading ? (
            <Skeleton className="h-[240px] w-full rounded-xl" />
          ) : equityPoints.length > 0 ? (
            <EquityCurveChart points={equityPoints} currency={report.data?.currency ?? "USDT"} baseline={initialBalance} />
          ) : (
            <EmptyState
              title="No closed paper trades yet"
              badge="Empty"
              description="The curve appears after the first closed trade. HOLD and BLOCKED decisions do not move equity."
              className="min-h-[200px]"
            />
          )}
          <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span>Initial <FinancialValue value={report.data?.initial_balance} digits={2} size="xs" /></span>
            <span>Realized <FinancialValue value={realized} digits={2} signed showPlus size="xs" /></span>
            <span>Unrealized <FinancialValue value={unrealized} digits={2} signed showPlus size="xs" /></span>
          </p>
        </SectionPanel>

        <div className="flex min-w-0 flex-col gap-4">
          <SectionPanel title="Agent activity" description="Per-agent evidence from the latest pipeline run. No contribution means idle.">
            {loading ? (
              <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9 w-full rounded-xl" />)}</div>
            ) : agents.length === 0 ? (
              <EmptyState title="No agent runtime" badge="Unavailable" description="Agent status appears when the supervisor reports a decision." className="p-5" />
            ) : (
              <ul className="space-y-1.5">
                {agents.slice(0, 8).map((a) => (
                  <li key={a.agent_id} className="flex items-center justify-between gap-2 rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
                    <span className="min-w-0 truncate text-foreground">{a.label}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      {a.bias ? <span className="font-mono text-[10px] text-muted-foreground">{a.bias}{a.confidence != null ? ` · ${Math.round(a.confidence * 100)}%` : ""}</span> : null}
                      <StatusIndicator status={a.status} size="sm" />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Button asChild variant="ghost" size="sm" className="mt-3 rounded-full">
              <Link href="/agents">Open agent workspace<ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden /></Link>
            </Button>
          </SectionPanel>

          <SectionPanel title="Current market analysis" description="Latest supervisor decision on confirmed candles.">
            {loading ? (
              <Skeleton className="h-28 w-full rounded-xl" />
            ) : !latest ? (
              <EmptyState title="No decision yet" badge="Waiting" description="Start a paper session or ask the Orchestrator to analyze a symbol." className="p-5" />
            ) : (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusIndicator status={latest.action === "BUY" || latest.action === "SELL" ? "OK" : latest.action} label={latest.action} size="md" />
                  <span className="font-mono text-xs text-muted-foreground">
                    {session?.authorization?.symbol ?? "—"} · {session?.authorization?.interval ?? "—"}m
                  </span>
                  <DataFreshness at={latest.timestamp_ms} staleAfterMs={30 * 60_000} />
                </div>
                <p className="text-sm text-foreground">{latest.explanation}</p>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <Fact label="Signal strength" value={latest.signal_strength != null ? `${Math.round(latest.signal_strength * 100)}/100` : "—"} />
                  <Fact label="Market quality" value={latest.market_quality != null ? `${Math.round(latest.market_quality * 100)}/100` : "—"} />
                  <Fact label="Risk verdict" value={latest.risk?.verdict ?? "—"} />
                </div>
                <ReasonList codes={latest.reason_codes} compact max={3} />
              </div>
            )}
          </SectionPanel>
        </div>
      </div>

      {/* Section 4 — Operational events */}
      <div className="grid min-w-0 gap-4 lg:grid-cols-3">
        <SectionPanel title="Latest strategy signals" description="Decision ring from the supervisor.">
          <EventList
            empty="No decisions recorded in this session."
            loading={loading}
            items={decisions.slice(-6).reverse().map((d) => ({
              id: d.decision_id,
              title: `${d.action} · ${d.symbol}`,
              detail: d.explanation,
              at: d.timestamp_ms,
              tone: d.action === "BLOCKED" ? "block" : d.action === "HOLD" ? "info" : "ok",
            }))}
          />
        </SectionPanel>
        <SectionPanel title="Risk vetoes & blocks" description="Why entries did not happen.">
          <EventList
            empty="No vetoes in the decision ring."
            loading={loading}
            items={vetoes.slice(-6).reverse().map((d) => ({
              id: `veto-${d.decision_id}`,
              title: d.risk_verdict ? `${d.risk_verdict} · ${d.symbol}` : `${d.action} · ${d.symbol}`,
              detail: (d.reason_codes || []).slice(0, 3).join(" · ") || d.explanation,
              at: d.timestamp_ms,
              tone: "block",
            }))}
          />
        </SectionPanel>
        <SectionPanel title="Recent paper activity" description="Fills and protective exits from the journal.">
          <EventList
            empty="No fills or protective exits yet."
            loading={loading}
            items={protective.slice(-6).reverse().map((e) => ({
              id: e.event_id,
              title: `${String(e.event_type).replace(/_/g, " ")}${e.exit_reason ? ` · ${e.exit_reason}` : ""}`,
              detail: typeof e.payload?.symbol === "string" ? String(e.payload.symbol) : "",
              at: e.created_ms,
              tone: e.protective ? "info" : "ok",
            }))}
          />
        </SectionPanel>
      </div>

      {unavailable ? null : (
        <SectionPanel title="Jump to workspace" description="Agent-first tools first, then trading desk and research.">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {QUICK_LINKS.map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} className="group rounded-2xl border border-border bg-muted/30 p-4 transition-colors hover:border-border-strong hover:bg-muted/40">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-muted/70">
                      <Icon className="h-4 w-4 text-brand" aria-hidden />
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden />
                  </div>
                  <p className="mt-3 text-sm font-medium text-foreground">{item.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{item.detail}</p>
                </Link>
              );
            })}
          </div>
        </SectionPanel>
      )}
    </OverviewTemplate>
  );
}

function StatusTile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-muted/40 p-3">
      <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      {children}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/40 px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-xs text-foreground">{value}</p>
    </div>
  );
}

function EventList({
  items,
  empty,
  loading,
}: {
  items: { id: string; title: string; detail: string; at: number | null | undefined; tone: "ok" | "info" | "block" }[];
  empty: string;
  loading: boolean;
}) {
  if (loading) {
    return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-xl" />)}</div>;
  }
  if (items.length === 0) return <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">{empty}</p>;
  return (
    <ol className="space-y-2">
      {items.map((item) => (
        <li key={item.id} className="flex gap-2.5 rounded-xl border border-border bg-muted/30 px-3 py-2">
          <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", item.tone === "block" ? "bg-loss" : item.tone === "ok" ? "bg-profit" : "bg-brand")} aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-foreground">{item.title}</p>
            {item.detail ? <p className="truncate text-[11px] text-muted-foreground">{item.detail}</p> : null}
            <p className="mt-0.5 text-[10px] text-muted-foreground" title={formatDateTime(item.at)}>{formatRelative(item.at)}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
