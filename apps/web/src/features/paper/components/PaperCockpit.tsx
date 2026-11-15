"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, CircleStop, Pause, Play, RefreshCw, ShieldOff } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import {
  DataFreshness,
  DataTable,
  EmptyState,
  ErrorState,
  ExecutionMode,
  FinancialValue,
  MetricCard,
  MetricCardGrid,
  OperationsTemplate,
  ReasonList,
  StatusBadge,
  StatusIndicator,
  type DataTableColumn,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { realizedEquitySeries } from "@/features/dashboard/lib/equity-series";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { fetchAutonomySnapshot, fetchOrchestratorStatus, fetchPaperReport, sendSupervisorCommand } from "@/lib/api/orchestrator";
import { allowedCommands, type PaperClosedTrade, type SupervisorCommand } from "@/lib/orchestrator/autonomy";
import { toNumber } from "@/lib/formatting/decimal";
import { formatDateTime, formatDuration, formatRelative } from "@/lib/formatting/time";
import { cn } from "@/lib/utils";

const EquityCurveChart = dynamic(() => import("@/components/charts/EquityCurveChart").then((m) => m.EquityCurveChart), {
  ssr: false,
  loading: () => <Skeleton className="h-[220px] w-full rounded-xl" />,
});

const TRADE_COLUMNS: DataTableColumn<PaperClosedTrade>[] = [
  { id: "closed", header: "Closed", cell: (t) => <span className="text-muted-foreground" title={formatDateTime(t.closed_ms)}>{formatRelative(t.closed_ms)}</span>, accessor: (t) => t.closed_ms },
  { id: "symbol", header: "Symbol", cell: (t) => <span className="font-medium text-foreground">{t.symbol}</span>, accessor: (t) => t.symbol },
  { id: "qty", header: "Qty", align: "right", cell: (t) => <FinancialValue value={t.quantity} maxDigits={8} size="xs" />, accessor: (t) => t.quantity },
  { id: "entry", header: "Entry", align: "right", cell: (t) => <FinancialValue value={t.entry_price} maxDigits={6} size="xs" />, accessor: (t) => t.entry_price },
  { id: "exit", header: "Exit", align: "right", cell: (t) => <FinancialValue value={t.exit_price} maxDigits={6} size="xs" />, accessor: (t) => t.exit_price },
  { id: "pnl", header: "Realized PnL", align: "right", cell: (t) => <FinancialValue value={t.realized_pnl} digits={2} signed showPlus size="xs" />, accessor: (t) => t.realized_pnl },
  { id: "reason", header: "Exit reason", cell: (t) => <span className="font-mono text-muted-foreground">{t.exit_reason || "—"}</span>, accessor: (t) => t.exit_reason, hideBelow: "md" },
  { id: "held", header: "Held", cell: (t) => <span className="text-muted-foreground">{formatDuration(t.closed_ms - t.opened_ms)}</span>, accessor: (t) => t.closed_ms - t.opened_ms, hideBelow: "lg" },
];

const COMMAND_META: Record<SupervisorCommand, { label: string; icon: typeof Play; variant: "default" | "outline" | "destructive"; confirm?: string }> = {
  start: { label: "Start", icon: Play, variant: "default" },
  pause: { label: "Pause entries", icon: Pause, variant: "outline" },
  resume: { label: "Resume entries", icon: Play, variant: "outline" },
  stop: { label: "Stop & close", icon: CircleStop, variant: "outline", confirm: "Stop requests closure of open paper positions on the next eligible candle." },
  halt: { label: "Emergency halt", icon: ShieldOff, variant: "destructive", confirm: "Halt blocks new paper entries immediately; protective exits keep running." },
};

export function PaperCockpit() {
  const status = usePolledResource(fetchOrchestratorStatus, { intervalMs: 8_000 });
  const report = usePolledResource(fetchPaperReport, { intervalMs: 15_000 });
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 15_000 });
  const [pending, setPending] = useState<SupervisorCommand | null>(null);
  const [confirming, setConfirming] = useState<SupervisorCommand | null>(null);
  const [commandError, setCommandError] = useState<{ code: string; at: number } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const st = status.data;
  const rp = report.data;
  const snap = autonomy.data;
  const state = String(st?.state ?? "UNKNOWN").toUpperCase();
  const available = allowedCommands(state).filter((c) => c !== "start");
  const auth = st?.authorization ?? null;
  const equityPoints = useMemo(() => realizedEquitySeries(rp), [rp]);
  const initial = toNumber(rp?.initial_balance);
  const equity = toNumber(rp?.equity);
  const drawdownPct = initial && equity !== null && initial > 0 ? Math.max(0, ((initial - equity) / initial) * 100) : null;
  const duration = auth?.started_at_ms ? Date.now() - auth.started_at_ms : null;
  const trades = rp?.recent_trades ?? [];
  const latest = st?.latest_decision ?? snap?.latest_decision ?? null;
  const canControl = Boolean(st?.enabled) && !pending && !status.error;

  async function run(command: SupervisorCommand) {
    if (pending) return;
    const meta = COMMAND_META[command];
    if (meta.confirm && confirming !== command) {
      setConfirming(command);
      return;
    }
    setConfirming(null);
    setPending(command);
    setCommandError(null);
    setNotice(null);
    const result = await sendSupervisorCommand(command);
    if (!result.ok) {
      setCommandError({ code: result.code, at: result.at });
    } else {
      setNotice(
        {
          start: "Paper session authorized.",
          pause: "New entries paused. Open positions stay under protective monitoring.",
          resume: "New entries resumed under the same session limits.",
          stop: "Stop acknowledged. Open positions close on the next eligible candle.",
          halt: "Emergency halt acknowledged. New exposure is blocked; protective exits continue.",
        }[command],
      );
    }
    setPending(null);
    void status.refresh();
    void report.refresh();
    void autonomy.refresh();
  }

  return (
    <OperationsTemplate
      title="Autonomous Paper Trading"
      description="The paper supervisor's live cockpit: equity, PnL, drawdown, positions and the decisions behind them. Controls act only on the PAPER journal — nothing here reaches Bybit."
      modes={["paper"]}
      actions={
        <>
          <Button variant="outline" size="sm" className="rounded-full" onClick={() => { void status.refresh(); void report.refresh(); void autonomy.refresh(); }} disabled={status.refreshing || report.refreshing}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", (status.refreshing || report.refreshing) && "animate-spin")} aria-hidden />
            Refresh
          </Button>
          <Button asChild variant="secondary" size="sm" className="rounded-full">
            <Link href="/autonomy">Authorize / configure<ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden /></Link>
          </Button>
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-2" role="status" aria-live="polite">
        <ExecutionMode mode="paper" />
        <StatusIndicator status={status.loading ? "UNKNOWN" : state} pulse size="md" />
        <StatusBadge label={st?.enabled ? "supervisor feature on" : "supervisor feature off"} tone={st?.enabled ? "ok" : "neutral"} />
        <StatusIndicator status={st?.worker_running ? "RUNNING" : st ? "STOPPED" : "UNKNOWN"} label={st?.worker_running ? "Worker running" : "Worker offline"} variant="inline" />
        <DataFreshness at={st?.heartbeat_ms ?? null} staleAfterMs={180_000} label="heartbeat" missingLabel="No heartbeat" />
        <DataFreshness at={st?.last_candle_start ?? null} staleAfterMs={3 * (Number(auth?.interval) || 15) * 60_000} label="last candle" missingLabel="No candle evaluated" />
      </div>

      {status.error && !st ? <ErrorState title="Supervisor unavailable" code={status.error.code} at={status.error.at} onRetry={() => void status.refresh()} /> : null}
      {commandError ? <ErrorState title="Command not applied" code={commandError.code} at={commandError.at} compact onRetry={() => setCommandError(null)} /> : null}
      {notice ? <p role="status" className="rounded-2xl border border-profit/25 bg-profit/5 px-4 py-3 text-sm text-foreground">{notice}</p> : null}
      {st && !st.enabled ? (
        <div className="rounded-2xl border border-warning/30 bg-warning/5 p-4 text-sm">
          <p className="font-medium text-foreground">Paper supervisor is disabled</p>
          <p className="mt-1 text-muted-foreground">Enable CRYPTONOVA_PAPER_SUPERVISOR on the API and restart it. No session is running and no controls are available.</p>
        </div>
      ) : null}

      <MetricCardGrid>
        <MetricCard label="Starting equity" loading={report.loading} value={<FinancialValue value={rp?.initial_balance} digits={2} unit={rp?.currency ?? "USDT"} size="lg" />} hint={auth ? `${auth.symbol} · ${auth.category} · ${auth.interval}m` : "No session"} />
        <MetricCard label="Current equity" accent loading={report.loading} value={<FinancialValue value={rp?.equity} digits={2} unit={rp?.currency ?? "USDT"} size="lg" />} hint={rp?.available ? "Journal · exchange equity excluded" : "Journal unavailable"} muted={rp ? !rp.available : false} />
        <MetricCard label="Realized / unrealized" loading={report.loading} value={<span className="flex flex-wrap items-baseline gap-x-2"><FinancialValue value={rp?.realized_pnl} digits={2} signed showPlus size="lg" /><FinancialValue value={rp?.unrealized_pnl} digits={2} signed showPlus size="sm" prefix={<span className="text-muted-foreground">/</span>} /></span>} hint={`fees ${rp?.fees_paid ?? "—"}`} />
        <MetricCard label="Drawdown" loading={report.loading} value={<span className="font-mono">{drawdownPct === null ? "—" : `${drawdownPct.toFixed(2)}%`}</span>} hint={`${rp?.drawdown ?? "—"} ${rp?.currency ?? "USDT"} from peak · limit 10%`} />
        <MetricCard label="Active positions" loading={report.loading} value={<span className="font-mono">{rp?.open_positions ?? "—"}</span>} hint={st?.block_new_exposure ? "New entries blocked" : "Entries eligible after risk checks"} />
        <MetricCard label="Trades" loading={report.loading} value={<span className="font-mono">{rp?.closed_trades ?? 0}</span>} hint={rp?.win_rate != null ? `win rate ${(rp.win_rate * 100).toFixed(0)}% · ${rp.winning_trades ?? 0} winners` : "no closed trades"} />
        <MetricCard label="Session duration" loading={status.loading} value={<span className="font-mono">{formatDuration(duration)}</span>} hint={auth?.expires_at_ms ? `expires ${formatRelative(auth.expires_at_ms)}` : "no active window"} />
        <MetricCard label="Journal activity" loading={report.loading} value={<span className="font-mono">{rp?.recent_events?.length ?? 0} events</span>} hint={rp?.pending_orders?.length ? `${rp.pending_orders.length} pending order(s)` : "no pending orders"} />
      </MetricCardGrid>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.9fr)]">
        <SectionPanel title="Realized paper equity" description="Initial balance plus each closed trade in close order. Mark-to-market of open positions is excluded.">
          {report.loading ? <Skeleton className="h-[220px] rounded-xl" /> : equityPoints.length ? <EquityCurveChart points={equityPoints} currency={rp?.currency ?? "USDT"} baseline={initial} height={220} /> : <EmptyState title="No closed paper trades yet" badge="Empty" description="The curve starts after the first closed trade." className="min-h-[180px]" />}
        </SectionPanel>

        <SectionPanel title="Session controls" description="Server acknowledgement is required before any state is shown as changed.">
          {available.length === 0 ? (
            <p className="text-xs text-muted-foreground">{state === "STOPPED" || state === "UNKNOWN" ? "No session is running. Authorize one from the Autonomy desk." : `No commands available in state ${state}.`}</p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {available.map((c) => {
                const meta = COMMAND_META[c];
                const Icon = meta.icon;
                return (
                  <Button key={c} variant={meta.variant} className={cn(c === "halt" && "col-span-2")} disabled={!canControl} onClick={() => void run(c)} aria-busy={pending === c}>
                    <Icon className="mr-2 size-3.5" aria-hidden />
                    {pending === c ? "Sending…" : confirming === c ? `Confirm ${meta.label.toLowerCase()}` : meta.label}
                  </Button>
                );
              })}
            </div>
          )}
          {confirming ? (
            <div className="mt-3 rounded-xl border border-warning/30 bg-warning/5 p-3 text-xs">
              <p className="text-foreground">{COMMAND_META[confirming].confirm}</p>
              <div className="mt-2 flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setConfirming(null)}>Cancel</Button>
              </div>
            </div>
          ) : null}
          {state === "STOPPED" || state === "UNKNOWN" ? (
            <Button asChild className="mt-3 w-full" variant="secondary">
              <Link href="/autonomy"><Play className="mr-2 size-4" aria-hidden />Authorize a paper session</Link>
            </Button>
          ) : null}
          <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">Pause and halt block new entries while protective exits remain monitored. Stop requests closure on the next eligible candle. If the Risk Engine rejects a position because the capital is too small, the decision below shows the blocker; risk is never loosened to force activity.</p>
        </SectionPanel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionPanel title="Latest agent decision" description="Why the last cycle did or did not open a position.">
          {!latest ? (
            <EmptyState title="Waiting for the first decision" badge="Waiting" description="Appears after the worker evaluates a confirmed candle." className="p-5" />
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <StatusIndicator status={latest.action === "BUY" || latest.action === "SELL" ? "OK" : latest.action} label={latest.action} size="md" />
                <StatusBadge label={`Risk ${latest.risk?.verdict ?? "—"}`} tone={latest.risk?.verdict === "APPROVED" ? "ok" : "danger"} />
                <span className="text-[11px] text-muted-foreground">{formatRelative(latest.timestamp_ms)}</span>
                {st?.last_reason ? <StatusBadge label={st.last_reason} tone="neutral" /> : null}
              </div>
              <p className="text-sm text-foreground">{latest.explanation}</p>
              <ReasonList codes={[...(latest.reason_codes || []), ...(st?.last_reason && !latest.reason_codes?.includes(st.last_reason) ? [st.last_reason] : [])]} max={5} />
            </div>
          )}
        </SectionPanel>
        <SectionPanel title="Open positions" description="Marked paper positions with protection levels.">
          {!rp?.positions?.length ? (
            <EmptyState title="No open positions" badge="Flat" description="The supervisor stays flat when agents disagree, risk vetoes an entry, or the market does not qualify." className="p-5" />
          ) : (
            <ul className="space-y-2">
              {rp.positions.map((p) => (
                <li key={p.position_id} className="rounded-xl border border-border bg-muted/40 p-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{p.symbol} · long · <FinancialValue value={p.quantity} maxDigits={8} size="xs" /></span>
                    <FinancialValue value={p.unrealized_pnl} digits={2} signed showPlus size="sm" />
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <div><dt className="text-muted-foreground">Entry</dt><dd><FinancialValue value={p.entry_price} maxDigits={6} size="xs" /></dd></div>
                    <div><dt className="text-muted-foreground">Mark</dt><dd><FinancialValue value={p.mark_price} maxDigits={6} size="xs" fallback="unavailable" /></dd></div>
                    <div><dt className="text-muted-foreground">Stop</dt><dd><FinancialValue value={p.stop_loss} maxDigits={6} size="xs" /></dd></div>
                    <div><dt className="text-muted-foreground">Target</dt><dd><FinancialValue value={p.take_profit} maxDigits={6} size="xs" /></dd></div>
                  </dl>
                  <p className="mt-2 text-[10px] text-muted-foreground">Opened {formatDateTime(p.opened_ms)}</p>
                </li>
              ))}
            </ul>
          )}
        </SectionPanel>
      </div>

      <SectionPanel title="Closed trades" description="Values in USDT. Paper outcomes do not establish live profitability.">
        {report.loading ? <Skeleton className="h-40 rounded-xl" /> : (
          <DataTable rows={trades} columns={TRADE_COLUMNS} rowKey={(t) => t.position_id} caption="Closed paper trades" initialSort={{ id: "closed", desc: true }} pageSize={15} emptyState="No completed trades yet." />
        )}
      </SectionPanel>
    </OperationsTemplate>
  );
}
