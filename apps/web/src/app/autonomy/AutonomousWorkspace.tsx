"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, ArrowRight, Bot, CircleStop, Clock3, LockKeyhole, Pause, Play, Radio, RefreshCw, ShieldCheck, ShieldOff } from "lucide-react";

import { MetricGrid, MetricTile, SectionPanel } from "@/components/command-center";
import { OperationsTemplate } from "@/components/design-system/templates";
import { StatusBadge } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  allowedCommands, finiteNumber, formatMoney, formatTime, SESSION_INTERVALS,
  sessionProgress, validateAuthorization, workerHealth,
  type PaperJournalReport, type SessionAuthorization, type SupervisorCommand, type SupervisorStatus,
} from "@/lib/orchestrator/autonomy";
import { cn } from "@/lib/utils";

import { DecisionPanel, JournalPanels } from "./TradingPanels";

const DEFAULT_AUTH: SessionAuthorization = {
  symbol: "BTCUSDT", category: "linear", interval: "15", capital_usdt: "1000", risk_fraction: "0.01", duration_hours: 48,
};
const INPUT_CLASS = "h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-brand/50 disabled:opacity-50";

function errorMessage(error: unknown): string {
  const key = error instanceof Error ? error.message : "request_failed";
  const messages: Record<string, string> = {
    operator_local_proxy_disabled: "Local operator access is disabled. Enable OPERATOR_LOCAL_BROWSER_PROXY_ENABLED in the web server configuration and restart the web server.",
    supervisor_disabled: "The paper supervisor is disabled. Enable CRYPTONOVA_PAPER_SUPERVISOR in the API configuration and restart the API.",
    operator_local_only: "Open this console on localhost. Autonomous controls are restricted to a local operator.",
    operator_forwarded_request_rejected: "Autonomous controls require a direct local connection. Forwarded remote requests are blocked.",
    operator_controls_disabled_in_production: "Local operator controls are unavailable in production.",
    api_unreachable: "The trading API is unavailable. Check that the API is running, then refresh.",
    command_not_allowed: "The session changed state. Refresh and choose a command available in its current state.",
    invalid_json: "The API returned an invalid response. The previous snapshot has been kept.",
  };
  return messages[key] || key.replace(/_/g, " ");
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...options });
  const body = await response.json().catch(() => { throw new Error("invalid_json"); });
  if (!response.ok || body.error) {
    const detail = typeof body.detail === "string" ? body.detail : body.error || `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export function AutonomousWorkspace() {
  const [status, setStatus] = useState<SupervisorStatus | null>(null);
  const [report, setReport] = useState<PaperJournalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [commandError, setCommandError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState<SupervisorCommand | null>(null);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [form, setForm] = useState<SessionAuthorization>(DEFAULT_AUTH);
  const [riskPercent, setRiskPercent] = useState("1");
  const requestId = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const commandBusy = useRef(false);
  const mounted = useRef(true);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setRefreshing(true);
    try {
      const statusResult = await requestJson<SupervisorStatus>("/api/orchestrator/status", { signal: controller.signal });
      if (!mounted.current || id !== requestId.current) return;
      if (typeof statusResult.state !== "string" || typeof statusResult.enabled !== "boolean") throw new Error("invalid_json");
      setStatus(statusResult);
      setUpdatedAt(Date.now());
      setLoadError(null);
      try {
        const nextReport = await requestJson<PaperJournalReport>("/api/orchestrator/report", { signal: controller.signal });
        if (!mounted.current || id !== requestId.current) return;
        setReport(nextReport);
        if (nextReport && (nextReport as { report_error?: string }).report_error) {
          setLoadError(`Journal: ${String((nextReport as { report_error?: string }).report_error).replace(/_/g, " ")}`);
        }
      } catch (reportError) {
        if (controller.signal.aborted || !mounted.current || id !== requestId.current) return;
        // Keep supervisor controls usable even when the journal snapshot fails.
        setLoadError(errorMessage(reportError));
      }
    } catch (error) {
      if (controller.signal.aborted || !mounted.current || id !== requestId.current) return;
      setLoadError(errorMessage(error));
    } finally {
      if (mounted.current && id === requestId.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    const poll = window.setInterval(() => {
      setNow(Date.now());
      if (!document.hidden && !commandBusy.current) void load();
    }, 8_000);
    return () => { mounted.current = false; abort.current?.abort(); window.clearInterval(poll); };
  }, [load]);

  async function command(name: SupervisorCommand) {
    if (commandBusy.current) return;
    const authorization = { ...form, risk_fraction: String(Number(riskPercent) / 100) };
    if (name === "start") {
      const validation = validateAuthorization(authorization);
      if (validation) { setCommandError(validation); return; }
    }
    commandBusy.current = true;
    ++requestId.current;
    abort.current?.abort();
    setPending(name);
    setCommandError(null);
    setNotice(null);
    try {
      await requestJson<SupervisorStatus>("/api/orchestrator/command", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: name, ...(name === "start" ? { authorization } : {}) }),
      });
      if (!mounted.current) return;
      setNotice({ start: "Paper session authorized. The worker manages entries and exits within these limits.", pause: "New entries paused. Existing positions continue protective monitoring.", resume: "New entries resumed under the same session limits.", halt: "Emergency halt requested. New exposure is blocked; protective exits continue.", stop: "Session stop requested. Check the lifecycle below until open positions are closed." }[name]);
      await load();
    } catch (error) {
      if (mounted.current) setCommandError(errorMessage(error));
    } finally {
      commandBusy.current = false;
      if (mounted.current) { setPending(null); setRefreshing(false); }
    }
  }

  const state = status?.state || "UNKNOWN";
  const available = allowedCommands(state);
  const canControl = !!status?.enabled && !pending && !loadError;
  const auth = status?.authorization;
  const health = workerHealth(status, now);
  const progress = sessionProgress(auth, now);
  const realized = finiteNumber(report?.realized_pnl);
  const riskBudget = finiteNumber(form.capital_usdt) !== null && finiteNumber(riskPercent) !== null
    ? Number(form.capital_usdt) * Number(riskPercent) / 100 : null;
  const startVisible = state === "STOPPED" || state === "UNKNOWN";

  return (
    <OperationsTemplate
      eyebrow="Autonomous operations" title="Trading control center"
      description="Authorize a bounded paper session. Follow the agents, inspect each decision, and track every position through its exit."
      modes={["paper"]}
      actions={<><Button variant="outline" size="sm" disabled={refreshing || !!pending} onClick={() => void load()}><RefreshCw className={cn("mr-2 size-3.5", refreshing && "animate-spin")} />Refresh</Button><Button variant="outline" size="sm" asChild><Link href="/orchestrator"><Bot className="mr-2 size-3.5" />Open chat</Link></Button></>}
    >
      <div role="status" aria-live="polite" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border bg-muted/30 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <span className={cn("size-2 rounded-full", health === "healthy" && !loadError ? "bg-profit" : "bg-muted-foreground")} />
          <span className="font-medium">{loadError ? "Snapshot unavailable" : health === "healthy" ? "Worker connected" : health === "stale" ? "Worker heartbeat stale" : health === "waiting" ? "Waiting for worker heartbeat" : "Worker offline"}</span>
          <span className="text-muted-foreground">Refreshes every 8s · {updatedAt ? `last received ${formatTime(updatedAt)}` : "awaiting first snapshot"}</span>
          <StatusBadge label="PAPER" tone="paper" />
          <StatusBadge label="TESTNET gated" tone="neutral" />
          <StatusBadge label="LIVE gated" tone="live" />
        </div>
        <StatusBadge label={status ? state : "CONNECTING"} tone={state === "RUNNING" ? "ok" : state === "HALTED" || state === "ERROR" ? "danger" : "neutral"} />
      </div>

      {(loadError || commandError) && <div role="alert" className="rounded-2xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{commandError || loadError}{loadError && updatedAt ? <p className="mt-1 text-xs">Showing the last successful snapshot. Controls are disabled until refreshed.</p> : null}</div>}
      {notice && <div role="status" className="rounded-2xl border border-profit/25 bg-profit/5 px-4 py-3 text-sm">{notice}</div>}
      {status && !status.enabled && <div className="rounded-2xl border border-warning/30 bg-warning/5 p-4 text-sm"><p className="font-medium">Paper supervisor is disabled</p><p className="mt-1 text-muted-foreground">Enable CRYPTONOVA_PAPER_SUPERVISOR in the API configuration and restart the API to authorize a session. No session is running.</p></div>}

      {loading ? <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-64 rounded-2xl" /><Skeleton className="h-64 rounded-2xl" /></div> : <>
        <MetricGrid>
          <MetricTile label="Paper equity" hint="Simulated journal balance" accent><span className="font-mono">{formatMoney(report?.equity)}</span> <span className="text-xs text-muted-foreground">USDT</span></MetricTile>
          <MetricTile label="Realized PnL" hint={`Fees recorded: ${formatMoney(report?.fees_paid)} USDT`}><span className={cn("font-mono", realized !== null && (realized < 0 ? "text-destructive" : realized > 0 ? "text-profit" : ""))}>{formatMoney(report?.realized_pnl)}</span> <span className="text-xs text-muted-foreground">USDT</span></MetricTile>
          <MetricTile label="Open positions" hint={`Unrealized PnL: ${formatMoney(report?.unrealized_pnl)} USDT`}><span className="font-mono">{report?.open_positions ?? "—"}</span></MetricTile>
          <MetricTile label="Completed trades" hint={`Drawdown from initial balance: ${formatMoney(report?.drawdown)} USDT`}><span className="font-mono">{report?.closed_trades ?? "—"}</span></MetricTile>
        </MetricGrid>

        <div className="grid items-start gap-4 xl:grid-cols-[minmax(19rem,0.85fr)_minmax(0,1.5fr)]">
          <SectionPanel title={startVisible ? "Authorize paper trading" : "Session controls"} description={startVisible ? "Set the limits the supervisor must respect." : "One authorization covers every eligible paper trade."}>
            {startVisible ? <form onSubmit={(event) => { event.preventDefault(); void command("start"); }} className="space-y-4">
              <fieldset disabled={!canControl || !available.includes("start")} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-2">
                <FormField label="Symbol"><input aria-label="Trading symbol" value={form.symbol} maxLength={24} onChange={(event) => setForm({ ...form, symbol: event.target.value.toUpperCase().replace(/\s/g, "") })} className={INPUT_CLASS} /></FormField>
                <FormField label="Market"><select aria-label="Market category" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value as "spot" | "linear" })} className={INPUT_CLASS}><option value="linear">Linear · long only</option><option value="spot">Spot</option></select></FormField>
                <FormField label="Paper capital · USDT"><input aria-label="Paper capital in USDT" type="number" min="1" max="1000000" step="0.01" required value={form.capital_usdt} onChange={(event) => setForm({ ...form, capital_usdt: event.target.value })} className={INPUT_CLASS} /></FormField>
                <FormField label="Risk per trade · %"><input aria-label="Risk per trade percent" type="number" min="0.01" max="2" step="0.01" required value={riskPercent} onChange={(event) => setRiskPercent(event.target.value)} className={INPUT_CLASS} /></FormField>
                <FormField label="Candle interval"><select aria-label="Candle interval" value={form.interval} onChange={(event) => setForm({ ...form, interval: event.target.value })} className={INPUT_CLASS}>{SESSION_INTERVALS.map((interval) => <option key={interval} value={interval}>{interval === "D" ? "1 day" : Number(interval) >= 60 ? `${Number(interval) / 60} hours` : `${interval} minutes`}</option>)}</select></FormField>
                <FormField label="Duration · hours"><input aria-label="Session duration in hours" type="number" min="1" max="168" step="1" required value={form.duration_hours} onChange={(event) => setForm({ ...form, duration_hours: Number(event.target.value) })} className={INPUT_CLASS} /></FormField>
              </fieldset>
              <div className="rounded-xl bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground"><ShieldCheck className="mb-1 size-4 text-brand" />Planned loss budget: <span className="font-mono text-foreground">{formatMoney(riskBudget)} USDT</span> per trade. Sizing remains subject to fees, available capital and the risk agent. Market gaps may exceed a planned stop.</div>
              <Button type="submit" className="w-full" disabled={!canControl || !available.includes("start")}><Play className="mr-2 size-4" />{pending === "start" ? "Authorizing…" : "Start autonomous paper session"}</Button>
              <p className="text-[11px] leading-relaxed text-muted-foreground">Starting authorizes simulated entries and exits for this session. No real funds are used. Linear simulation currently supports long positions only; funding and liquidation are not modeled.</p>
            </form> : <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-3">
                <SessionFact label="Market" value={`${auth?.symbol || "—"} · ${auth?.category || "—"}`} />
                <SessionFact label="Authorized capital" value={`${formatMoney(auth?.capital_usdt)} USDT`} />
                <SessionFact label="Risk budget" value={`${formatMoney(auth?.risk_budget_usdt ?? (auth ? Number(auth.capital_usdt) * Number(auth.risk_fraction) : null))} USDT / trade`} />
                <SessionFact label="New entries" value={state === "RUNNING" && !status?.block_new_exposure ? "Eligible after risk checks" : "Blocked"} />
              </dl>
              {progress !== null && <div><div className="mb-2 flex justify-between text-xs text-muted-foreground"><span className="flex items-center gap-1"><Clock3 className="size-3" />Session window</span><span>{Math.round(progress)}% elapsed</span></div><div role="progressbar" aria-label="Session elapsed" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100} className="h-1.5 overflow-hidden rounded-full bg-muted"><div style={{ width: `${progress}%` }} className="h-full rounded-full bg-brand" /></div><p className="mt-2 text-[11px] text-muted-foreground">Entry authorization expires {formatTime(auth?.expires_at_ms)}</p></div>}
              <div className="grid grid-cols-2 gap-2">
                {available.includes("pause") && <Button variant="outline" disabled={!canControl} onClick={() => void command("pause")}><Pause className="mr-2 size-3.5" />Pause entries</Button>}
                {available.includes("resume") && <Button variant="outline" disabled={!canControl} onClick={() => void command("resume")}><Play className="mr-2 size-3.5" />Resume entries</Button>}
                {available.includes("stop") && <Button variant="outline" disabled={!canControl} onClick={() => void command("stop")}><CircleStop className="mr-2 size-3.5" />Stop & close</Button>}
                {available.includes("halt") && <Button variant="destructive" className="col-span-2" disabled={!canControl} onClick={() => void command("halt")}><ShieldOff className="mr-2 size-3.5" />{pending === "halt" ? "Halting…" : "Emergency halt"}</Button>}
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">Pause and halt block new entries while protective exits remain monitored. Stop requests closure on the next eligible candle; it is not an immediate market fill.</p>
            </div>}
          </SectionPanel>

          <div className="min-w-0 space-y-4">
            <section className="relative overflow-hidden rounded-2xl border border-brand/20 bg-gradient-to-br from-brand/10 via-background to-background p-5">
              <div className="mb-5 flex flex-wrap items-start justify-between gap-3"><div><p className="text-[11px] font-medium uppercase tracking-[0.16em] text-brand">Observe → decide → execute → review</p><h2 className="mt-1 text-lg font-medium">Autonomous trade lifecycle</h2></div><LockKeyhole className="size-5 text-brand" /></div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <LifecycleStep icon={Radio} label="Market" detail={status?.latest_decision?.market?.data_fresh ? "Fresh confirmed bars" : "Awaiting fresh decision"} active={!!status?.latest_decision?.market?.data_fresh && !loadError} />
                <LifecycleStep icon={Bot} label="Agents" detail={status?.last_action ? `Last action: ${status.last_action}` : "Awaiting evaluation"} active={!!status?.latest_decision && !loadError} />
                <LifecycleStep icon={ShieldCheck} label="Risk & entry" detail={status?.block_new_exposure || state !== "RUNNING" ? "New entries blocked" : "Deterministic risk gate"} active={state === "RUNNING" && !status?.block_new_exposure && !loadError} />
                <LifecycleStep icon={Activity} label="Monitor & exit" detail={status?.protective_monitoring ? "Protection monitored" : "No active monitoring"} active={!!status?.protective_monitoring && !loadError} />
              </div>
              <div className="mt-4 border-t border-border/50 pt-3 text-xs text-muted-foreground"><span className="font-medium text-foreground">Latest outcome: </span>{status?.last_reason?.replace(/_/g, " ") || "The worker has not reported a cycle yet."}{status?.last_error && <p className="mt-1 text-destructive">{status.last_error.replace(/_/g, " ")}</p>}</div>
            </section>
            <DecisionPanel decision={status?.latest_decision ?? null} />
          </div>
        </div>

        <JournalPanels report={report} />

        <SectionPanel title="Runtime & limits" description="Observed timestamps and explicit automation boundaries.">
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><SessionFact label="Worker heartbeat" value={formatTime(status?.heartbeat_ms)} /><SessionFact label="Last evaluated candle" value={formatTime(status?.last_candle_start)} /><SessionFact label="Protective monitoring" value={status?.protective_monitoring ? "Enabled" : "Inactive"} /><SessionFact label="Execution environment" value="Paper · exchange orders locked" /></dl>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4"><p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">Signals and consensus scores express model agreement, not a calibrated chance of profit. Paper results exclude unsupported futures mechanics. Validate on unseen market data and realistic costs before considering live execution.</p><Link href="/backtesting" className="inline-flex items-center gap-1.5 text-xs font-medium text-brand">Validate strategies<ArrowRight className="size-3.5" /></Link></div>
        </SectionPanel>
      </>}
    </OperationsTemplate>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="space-y-1.5"><span className="block text-xs text-muted-foreground">{label}</span>{children}</label>;
}

function SessionFact({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><dt className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</dt><dd className="mt-1 break-words text-sm font-medium">{value}</dd></div>;
}

function LifecycleStep({ icon: Icon, label, detail, active }: { icon: typeof Radio; label: string; detail: string; active: boolean }) {
  return <div className={cn("rounded-xl border p-3", active ? "border-brand/25 bg-brand/5" : "border-border bg-background/60")}><Icon className={cn("mb-2 size-4", active ? "text-brand" : "text-muted-foreground")} /><p className="text-xs font-medium">{label}</p><p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{detail}</p></div>;
}
