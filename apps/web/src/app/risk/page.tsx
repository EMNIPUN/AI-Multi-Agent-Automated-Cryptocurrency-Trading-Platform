"use client";

import Link from "next/link";
import { ArrowRight, RefreshCw } from "lucide-react";

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
  RiskIndicator,
  StatusBadge,
  StatusIndicator,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { fetchAutonomySnapshot } from "@/lib/api/orchestrator";
import { formatFractionPercent, toNumber } from "@/lib/formatting/decimal";
import { formatDateTime, formatRelative } from "@/lib/formatting/time";
import { useExecutionState } from "@/providers/ExecutionStateProvider";
import { cn } from "@/lib/utils";

function Budget({ label, used, limit, hint }: { label: string; used: number | null; limit: number; hint: string }) {
  const ratio = used === null || limit <= 0 ? null : Math.min(1, Math.max(0, used / limit));
  const pct = ratio === null ? null : Math.round(ratio * 100);
  const tone = ratio === null ? "bg-muted-foreground" : ratio >= 1 ? "bg-loss" : ratio >= 0.66 ? "bg-warning" : "bg-profit";
  return (
    <div className="rounded-xl border border-border bg-muted/40 p-3">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono text-foreground">{formatFractionPercent(used)} / {formatFractionPercent(limit)}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label={label} aria-valuenow={pct ?? 0} aria-valuemin={0} aria-valuemax={100} aria-valuetext={pct === null ? "unknown" : `${pct}% of limit used`}>
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${pct ?? 0}%` }} />
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">{pct === null ? "Not reported yet." : `${pct}% of limit used. `}{hint}</p>
    </div>
  );
}

export default function RiskPage() {
  const exec = useExecutionState();
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 15_000 });
  const snap = autonomy.data;
  const risk = snap?.risk ?? null;
  const latest = snap?.latest_decision ?? null;
  const auth = snap?.session.authorization ?? null;
  const dailyLoss = toNumber(risk?.daily_loss_fraction);
  const dailyLimit = toNumber(risk?.daily_loss_limit_fraction) ?? 0.03;
  const drawdown = toNumber(risk?.drawdown_fraction);
  const drawdownLimit = toNumber(risk?.drawdown_limit_fraction) ?? 0.1;
  const capital = toNumber(auth?.capital_usdt);
  const riskFraction = toNumber(auth?.risk_fraction);
  const riskBudget = capital !== null && riskFraction !== null ? capital * riskFraction : null;
  const halted = Boolean(risk?.halted);
  const blocked = Boolean(risk?.block_new_exposure);
  const vetoes = (snap?.decision_queue ?? []).filter((d) => d.action === "BLOCKED" || (d.risk_verdict && d.risk_verdict !== "APPROVED")).slice(-10).reverse();
  const protective = (snap?.protective_events ?? []).filter((e) => e.protective).slice(-10).reverse();
  const positions = snap?.position_timeline.filter((p) => p.timeline_kind === "open") ?? [];

  return (
    <OverviewTemplate
      title="Risk Center"
      description="Deterministic risk facts from the paper supervisor: budgets, halts, vetoes and position-level protection. The Risk Engine's verdicts cannot be changed from this page."
      modes={["paper", "readonly"]}
      actions={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => void autonomy.refresh()} disabled={autonomy.refreshing}>
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", autonomy.refreshing && "animate-spin")} aria-hidden />
          Refresh
        </Button>
      }
    >
      {autonomy.error && !snap ? <ErrorState title="Risk feed unavailable" description="Fail closed: without the feed the UI assumes nothing is permitted." code={autonomy.error.code} at={autonomy.error.at} onRetry={() => void autonomy.refresh()} /> : null}

      <div className="flex flex-wrap items-center gap-2">
        <RiskIndicator state={autonomy.loading ? "unknown" : halted ? "halted" : blocked ? "blocked" : "ok"} reason={halted || blocked ? `Reason: ${String(risk?.halt_reason ?? "block_new_exposure").replace(/_/g, " ")}` : undefined} />
        <ExecutionMode mode="paper" />
        <ExecutionMode mode="live" armed={exec.data?.live === "armed_approve_required"} />
        <StatusIndicator status={snap?.session.state ?? "UNKNOWN"} label={`Supervisor ${(snap?.session.state ?? "unknown").toLowerCase()}`} pulse />
        <DataFreshness at={snap?.session.heartbeat_ms ?? null} staleAfterMs={180_000} label="heartbeat" />
      </div>

      <MetricCardGrid>
        <MetricCard label="Global verdict" accent loading={autonomy.loading} value={<span className="font-mono text-lg">{halted ? "HALTED" : blocked ? "ENTRIES BLOCKED" : snap ? "WITHIN LIMITS" : "UNKNOWN"}</span>} hint={risk?.label ?? "PAPER risk facts only — not exchange margin"} />
        <MetricCard label="Risk budget per trade" loading={autonomy.loading} value={<FinancialValue value={riskBudget} digits={2} unit="USDT" size="lg" />} hint={auth ? `${formatFractionPercent(riskFraction)} of ${auth.capital_usdt} USDT authorized capital` : "No authorized session"} />
        <MetricCard label="Max exposure" loading={autonomy.loading} value={<FinancialValue value={capital} digits={2} unit="USDT" size="lg" />} hint="Paper broker caps total exposure at authorized capital · 1 open position" />
        <MetricCard label="Open exposure" loading={autonomy.loading} value={<span className="font-mono">{risk?.open_exposure_positions ?? 0} position{risk?.open_exposure_positions === 1 ? "" : "s"}</span>} hint={`Equity ${risk?.equity ?? "—"} · peak ${risk?.peak_equity ?? "—"}`} />
      </MetricCardGrid>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionPanel title="Loss budgets" description="Fractions of paper equity measured by the supervisor each cycle.">
          {autonomy.loading ? <Skeleton className="h-32 rounded-xl" /> : (
            <div className="space-y-3">
              <Budget label="Daily loss" used={dailyLoss} limit={dailyLimit} hint="Reaching the limit halts new entries until the next UTC day." />
              <Budget label="Drawdown from peak" used={drawdown} limit={drawdownLimit} hint="Reaching the limit halts new entries; protective exits keep running." />
            </div>
          )}
        </SectionPanel>
        <SectionPanel title="Current decision gate" description="Why the latest cycle did or did not open exposure.">
          {!latest ? (
            <EmptyState title="No decision yet" badge="Waiting" description="Reason codes appear after the supervisor evaluates a confirmed candle." className="p-5" />
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusIndicator status={latest.action === "BUY" || latest.action === "SELL" ? "OK" : latest.action} label={latest.action} />
                <StatusBadge label={`Risk ${latest.risk?.verdict ?? "—"}`} tone={latest.risk?.verdict === "APPROVED" ? "ok" : "danger"} />
                <span className="text-[11px] text-muted-foreground">{formatRelative(latest.timestamp_ms)}</span>
              </div>
              <p className="text-xs text-muted-foreground">{latest.risk?.explanation}</p>
              <ReasonList codes={latest.reason_codes} />
              {latest.risk?.risk_reward != null || latest.risk?.position_notional != null ? (
                <p className="font-mono text-[11px] text-muted-foreground">RR {latest.risk.risk_reward ?? "—"} · notional {latest.risk.position_notional ?? "—"}</p>
              ) : null}
            </div>
          )}
        </SectionPanel>
      </div>

      <SectionPanel title="Position-level protection" description="Stop and target distances for open paper positions.">
        {positions.length === 0 ? (
          <p className="text-xs text-muted-foreground">No open paper positions. The supervisor stays flat when agents disagree or the Risk Engine vetoes an entry.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {positions.map((p) => {
              const entry = toNumber(p.entry_price);
              const mark = toNumber(p.mark_price);
              const sl = toNumber(p.stop_loss);
              const tp = toNumber(p.take_profit);
              const slDist = entry && sl ? ((entry - sl) / entry) * 100 : null;
              const tpDist = entry && tp ? ((tp - entry) / entry) * 100 : null;
              return (
                <div key={String(p.position_id)} className="rounded-xl border border-border bg-muted/40 p-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{String(p.symbol)} · <FinancialValue value={p.quantity} maxDigits={8} size="xs" /></span>
                    <FinancialValue value={p.unrealized_pnl} digits={2} signed showPlus size="sm" />
                  </div>
                  <dl className="mt-2 grid grid-cols-3 gap-2">
                    <div><dt className="text-muted-foreground">Entry</dt><dd><FinancialValue value={entry} maxDigits={6} size="xs" /></dd></div>
                    <div><dt className="text-muted-foreground">Mark</dt><dd><FinancialValue value={mark} maxDigits={6} size="xs" fallback="unavailable" /></dd></div>
                    <div><dt className="text-muted-foreground">Stop / target</dt><dd className="font-mono">{slDist !== null ? `-${slDist.toFixed(2)}%` : "—"} / {tpDist !== null ? `+${tpDist.toFixed(2)}%` : "—"}</dd></div>
                  </dl>
                </div>
              );
            })}
          </div>
        )}
      </SectionPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionPanel title="Risk event timeline" description="Vetoes and blocks from the decision ring, newest first.">
          {vetoes.length === 0 ? (
            <p className="text-xs text-muted-foreground">No vetoes recorded in the current decision ring.</p>
          ) : (
            <ol className="space-y-2">
              {vetoes.map((d) => (
                <li key={d.decision_id} className="rounded-xl border border-border bg-muted/30 px-3 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span className="font-medium text-foreground">{d.risk_verdict ?? d.action} · {d.symbol}</span>
                    <span className="text-muted-foreground" title={formatDateTime(d.timestamp_ms)}>{formatRelative(d.timestamp_ms)}</span>
                  </div>
                  <ReasonList codes={d.reason_codes} compact max={3} className="mt-1.5" />
                </li>
              ))}
            </ol>
          )}
        </SectionPanel>
        <SectionPanel title="Protective exits" description="Stop-loss and take-profit fills from the journal.">
          {protective.length === 0 ? (
            <p className="text-xs text-muted-foreground">No protective exits yet.</p>
          ) : (
            <ol className="space-y-2">
              {protective.map((e) => (
                <li key={e.event_id} className="flex items-center justify-between gap-2 rounded-xl border border-border bg-muted/30 px-3 py-2 text-xs">
                  <span className="font-medium text-foreground">{String(e.event_type).replace(/_/g, " ")} · {e.exit_reason ?? "exit"}</span>
                  <span className="text-muted-foreground">{formatRelative(e.created_ms)}</span>
                </li>
              ))}
            </ol>
          )}
        </SectionPanel>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" size="sm" className="rounded-full"><Link href="/autonomy">Autonomy desk<ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden /></Link></Button>
        <Button asChild variant="ghost" size="sm" className="rounded-full"><Link href="/positions">Positions</Link></Button>
      </div>
    </OverviewTemplate>
  );
}
