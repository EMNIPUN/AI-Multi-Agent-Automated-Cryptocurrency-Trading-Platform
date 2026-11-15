"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { DataFreshness, FinancialValue, ReasonList, StatusBadge, StatusIndicator } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { AutonomySnapshot, OpenAiUsage, OrchestratorStatus } from "@/lib/api/orchestrator";
import type { PaperJournalReport } from "@/lib/orchestrator/autonomy";
import { intervalLabel } from "@/lib/formatting/time";

import { ORCHESTRATION_LABEL, type ChatExecutionMode, type OrchestrationState } from "./orchestrator-state";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/50 px-3 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 max-w-[60%] truncate text-right font-mono text-xs text-foreground">{value}</dd>
    </div>
  );
}

export function ContextInspector({
  status,
  report,
  autonomy,
  openai,
  loading,
  chatMode,
  liveArmed,
  lastState,
  lastModel,
}: {
  status: OrchestratorStatus | null;
  report: PaperJournalReport | null;
  autonomy: AutonomySnapshot | null;
  openai: OpenAiUsage | null;
  loading: boolean;
  chatMode: ChatExecutionMode;
  liveArmed: boolean;
  lastState: OrchestrationState | null;
  lastModel: string | null;
}) {
  const auth = status?.authorization ?? autonomy?.session.authorization ?? null;
  const latest = status?.latest_decision ?? autonomy?.latest_decision ?? null;
  const agents = autonomy?.agents?.agents ?? [];
  const risk = autonomy?.risk ?? null;
  const badge = lastState ? ORCHESTRATION_LABEL[lastState] : null;

  if (loading && !status) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <SectionPanel title="Market context" description="Scope of the authorized paper session.">
        <dl className="space-y-2">
          <Row label="Symbol" value={auth?.symbol ?? "—"} />
          <Row label="Timeframe" value={auth?.interval ? intervalLabel(auth.interval) : "—"} />
          <Row label="Market" value={auth?.category ?? "—"} />
          <Row label="Last price" value={latest?.market?.last_price != null ? <FinancialValue value={latest.market.last_price} maxDigits={6} size="xs" /> : "—"} />
          <Row label="Candle" value={<DataFreshness at={latest?.market?.newest_close_ms ?? null} staleAfterMs={45 * 60_000} />} />
        </dl>
      </SectionPanel>

      <SectionPanel title="Paper supervisor" description="Session-authorized — no per-trade Approve.">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <StatusIndicator status={status?.state ?? "UNKNOWN"} pulse />
          <StatusBadge label={status?.enabled ? "feature on" : "feature off"} tone={status?.enabled ? "ok" : "neutral"} />
          <DataFreshness at={status?.heartbeat_ms ?? null} staleAfterMs={180_000} label="heartbeat" />
        </div>
        <dl className="space-y-2">
          <Row label="Equity" value={<FinancialValue value={report?.equity} digits={2} unit={report?.currency ?? "USDT"} size="xs" />} />
          <Row label="Open positions" value={String(report?.open_positions ?? 0)} />
          <Row label="Realized PnL" value={<FinancialValue value={report?.realized_pnl} digits={2} signed showPlus size="xs" />} />
          <Row label="Drawdown" value={<FinancialValue value={report?.drawdown} digits={2} size="xs" />} />
        </dl>
        <Button asChild variant="ghost" size="sm" className="mt-2 rounded-full">
          <Link href="/autonomy">Autonomy desk<ArrowRight className="ml-1 h-3.5 w-3.5" aria-hidden /></Link>
        </Button>
      </SectionPanel>

      <SectionPanel title="Latest analysis" description="Verified supervisor decision — not model speculation.">
        {latest ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusIndicator status={latest.action === "BUY" || latest.action === "SELL" ? "OK" : latest.action} label={latest.action} />
              <StatusBadge
                label={`Risk ${latest.risk?.verdict ?? "—"}`}
                tone={latest.risk?.verdict === "APPROVED" ? "ok" : latest.risk?.verdict ? "danger" : "neutral"}
              />
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">{latest.explanation}</p>
            <ReasonList codes={latest.reason_codes} compact max={4} />
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No decision yet — start paper trading or ask “Explain the last trading decision.”</p>
        )}
      </SectionPanel>

      <SectionPanel title="Agent activity" description="From the latest pipeline contributions only.">
        {agents.length === 0 ? (
          <p className="text-xs text-muted-foreground">No runtime agents reported.</p>
        ) : (
          <ul className="space-y-1.5">
            {agents.map((a) => (
              <li key={a.agent_id} className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/40 px-2.5 py-1.5 text-xs">
                <span className="truncate text-foreground">{a.label}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {a.bias ? <span className="font-mono text-[10px] text-muted-foreground">{a.bias}</span> : null}
                  <StatusIndicator status={a.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionPanel>

      <SectionPanel title="Risk verdict" description="PAPER risk facts from the supervisor journal.">
        <div className="flex flex-wrap items-center gap-2">
          <StatusIndicator
            status={risk ? (risk.halted ? "HALTED" : risk.block_new_exposure ? "BLOCKED" : "OK") : "UNKNOWN"}
            label={risk ? (risk.halted ? "Halted" : risk.block_new_exposure ? "Entries blocked" : "Within limits") : "Unknown"}
          />
          {risk?.halt_reason ? <span className="text-[11px] text-muted-foreground">{String(risk.halt_reason).replace(/_/g, " ")}</span> : null}
        </div>
        <dl className="mt-2 space-y-2">
          <Row label="Daily loss" value={`${risk?.daily_loss_fraction ?? "—"} / ${risk?.daily_loss_limit_fraction ?? "0.03"}`} />
          <Row label="Drawdown" value={`${risk?.drawdown_fraction ?? "—"} / ${risk?.drawdown_limit_fraction ?? "0.10"}`} />
        </dl>
      </SectionPanel>

      <SectionPanel title="Model & spend" description="Ledger-backed usage — no fabricated costs.">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {badge ? <StatusBadge label={`Last reply · ${badge.label}`} tone={badge.tone} /> : <StatusBadge label="No reply yet" tone="neutral" />}
          <StatusBadge label={openai?.gates_open ? "OpenAI gates open" : "Paid calls off"} tone={openai?.gates_open ? "ok" : "neutral"} />
        </div>
        <dl className="space-y-2">
          <Row label="Model" value={lastModel ?? openai?.model ?? "—"} />
          <Row label="Spent 24h" value={openai ? `$${openai.spent_usd_24h.toFixed(4)} / $${openai.daily_budget_usd.toFixed(2)}` : "—"} />
          <Row label="Spent 30d" value={openai ? `$${openai.spent_usd_30d.toFixed(4)} / $${openai.monthly_budget_usd.toFixed(2)}` : "—"} />
          <Row label="Remaining" value={openai ? `$${openai.remaining_usd_total.toFixed(4)}` : "—"} />
        </dl>
      </SectionPanel>

      {chatMode === "LIVE" ? (
        <SectionPanel title="Live Bybit lane" description="Every MAINNET order still needs an explicit Approve.">
          <dl className="space-y-2">
            <Row label="Env armed" value={liveArmed ? "Yes" : "No"} />
            <Row label="Bybit mainnet" value={status?.bybit_mainnet ? "Yes" : "No"} />
            <Row label="Per-order Approve" value="Required" />
          </dl>
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            Opens use the futures intake checklist (side, Market/Limit, qty, leverage, SL/TP). Closes and cancels also need Approve.
          </p>
        </SectionPanel>
      ) : null}
    </div>
  );
}
