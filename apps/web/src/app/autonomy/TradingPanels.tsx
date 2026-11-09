"use client";

import { Activity, ArrowDownToLine, ArrowUpFromLine, CheckCircle2, CircleDot, ShieldCheck } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { StatusBadge } from "@/components/design-system";
import { finiteNumber, formatMoney, formatTime, scorePercent, type DecisionEvidence, type PaperJournalReport, type PaperPosition } from "@/lib/orchestrator/autonomy";
import { cn } from "@/lib/utils";

function humanize(value: string) {
  return value.replace(/[_-]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function DecisionPanel({ decision }: { decision: DecisionEvidence | null }) {
  const strength = scorePercent(decision?.signal_strength);
  const quality = scorePercent(decision?.market_quality);
  return <SectionPanel title="Decision evidence" description="Each contributor is visible. The risk agent has veto authority." actions={decision ? <StatusBadge label={decision.action} tone={decision.action === "BLOCKED" ? "danger" : decision.action === "HOLD" ? "neutral" : "info"} /> : undefined}>
    {!decision ? <EmptyState icon={Activity} title="Waiting for the first decision" detail="Agent evidence appears after the supervisor evaluates a confirmed market candle." /> : <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted-foreground">{decision.explanation}</p>
      <div className="grid grid-cols-2 gap-3">
        <EvidenceScore label="Signal strength" value={strength} />
        <EvidenceScore label="Market quality" value={quality} />
      </div>
      <p className="text-[11px] text-muted-foreground">Qualitative scores only; neither score is a win probability.</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {(decision.contributions || []).map((agent) => <div key={agent.agent_id} className="rounded-xl border border-border bg-muted/30 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-xs font-medium">{humanize(agent.agent_id)}</p><StatusBadge label={agent.timed_out ? "TIMED OUT" : agent.error ? "ERROR" : agent.bias} tone={agent.timed_out || agent.error ? "danger" : "neutral"} /></div>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{agent.explanation}</p>
          {agent.reason_codes?.length > 0 && <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">{agent.reason_codes.map(humanize).join(" · ")}</p>}
        </div>)}
      </div>
      {decision.risk && <div className={cn("flex gap-3 rounded-xl border p-3", decision.risk.verdict === "APPROVED" ? "border-profit/25 bg-profit/5" : "border-warning/25 bg-warning/5")}><ShieldCheck className="mt-0.5 size-4 shrink-0" /><div><p className="text-xs font-medium">Risk verdict · {decision.risk.verdict}</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{decision.risk.explanation}</p></div></div>}
      <div className="flex flex-wrap justify-between gap-2 border-t border-border pt-3 text-[10px] text-muted-foreground"><span>Evaluated {formatTime(decision.timestamp_ms)}</span><span className="max-w-full truncate font-mono" title={decision.decision_id}>{decision.decision_id}</span></div>
    </div>}
  </SectionPanel>;
}

function EvidenceScore({ label, value }: { label: string; value: number | null }) {
  return <div className="rounded-xl border border-border px-3 py-2.5"><div className="mb-2 flex items-center justify-between gap-2 text-xs"><span className="text-muted-foreground">{label}</span><span className="font-mono">{value === null ? "—" : `${value}/100`}</span></div><div className="h-1 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-brand" style={{ width: `${value ?? 0}%` }} /></div></div>;
}

export function JournalPanels({ report }: { report: PaperJournalReport | null }) {
  const positions = report?.positions;
  const trades = report?.recent_trades;
  const events = report?.recent_events;
  const pending = report?.pending_orders;
  return <>
    <SectionPanel title="Position monitor" description="Marked paper positions, protection levels and pending execution." actions={<StatusBadge label={`${report?.open_positions ?? "—"} OPEN`} tone="paper" />}>
      {!positions ? <EmptyState icon={CircleDot} title="Position journal unavailable" detail="Position details appear when the paper session has an available journal." /> : positions.length === 0 ? <EmptyState icon={ShieldCheck} title="No open positions" detail="The supervisor can stay flat when agents disagree, risk vetoes an entry, or the market does not qualify." /> : <div className="grid gap-4 lg:grid-cols-2">{positions.map((position) => <PositionCard key={position.position_id} position={position} />)}</div>}
      {pending && pending.length > 0 && <div className="mt-4 border-t border-border pt-4"><p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Pending execution</p><div className="space-y-2">{pending.map((order) => <div key={order.order_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-muted/40 px-3 py-2 text-xs"><span className="font-medium">{order.symbol} · {order.side} {formatMoney(order.quantity, 6)}</span><span className="text-muted-foreground">{humanize(order.status)} · {formatTime(order.created_ms)}</span></div>)}</div></div>}
    </SectionPanel>

    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(18rem,1fr)]">
      <SectionPanel title="Closed trades" description="Recorded exits and realized performance from this paper journal.">
        {!trades?.length ? <EmptyState icon={CheckCircle2} title={trades ? "No completed trades yet" : "Trade journal unavailable"} detail="Closed positions appear here with their exit reason and recorded result." /> : <div className="overflow-x-auto"><table className="w-full min-w-[580px] text-left text-xs"><thead><tr className="border-b border-border text-[10px] uppercase tracking-wide text-muted-foreground"><th className="pb-3 font-normal">Market</th><th className="pb-3 text-right font-normal">Entry → Exit</th><th className="pb-3 text-right font-normal">Realized PnL</th><th className="pb-3 pl-4 font-normal">Exit reason</th><th className="pb-3 pl-4 font-normal">Closed</th></tr></thead><tbody>{trades.map((trade) => <tr key={trade.position_id} className="border-b border-border/50 last:border-0"><td className="py-3 font-medium">{trade.symbol}<span className="mt-1 block font-mono text-[10px] font-normal text-muted-foreground">{formatMoney(trade.quantity, 6)}</span></td><td className="py-3 text-right font-mono text-muted-foreground">{formatMoney(trade.entry_price, 4)} → {formatMoney(trade.exit_price, 4)}</td><td className={cn("py-3 text-right font-mono", pnlClass(trade.realized_pnl))}>{formatMoney(trade.realized_pnl)}</td><td className="py-3 pl-4">{humanize(trade.exit_reason || "Recorded exit")}</td><td className="py-3 pl-4 text-muted-foreground">{formatTime(trade.closed_ms)}</td></tr>)}</tbody></table><p className="mt-3 text-[11px] text-muted-foreground">Values in USDT. Showing {trades.length} recent closed trades; paper outcomes do not establish live profitability.</p></div>}
      </SectionPanel>
      <SectionPanel title="Journal activity" description="Recorded events, newest first.">
        {!events?.length ? <EmptyState icon={Activity} title="No recorded activity" detail="Order, fill and protection events will appear as the session progresses." /> : <ol className="max-h-[29rem] space-y-4 overflow-y-auto pr-1">{events.map((event) => {
          const symbol = typeof event.payload?.symbol === "string" ? event.payload.symbol : null;
          const reason = typeof event.payload?.reason === "string" ? event.payload.reason : null;
          return <li key={event.event_id} className="flex gap-3"><span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand" /><div className="min-w-0"><p className="break-words text-xs font-medium">{humanize(event.event_type)}{symbol ? ` · ${symbol}` : ""}</p>{reason && <p className="mt-1 break-words text-xs text-muted-foreground">{humanize(reason)}</p>}<p className="mt-1 text-[10px] text-muted-foreground">{formatTime(event.created_ms)}</p></div></li>;
        })}</ol>}
      </SectionPanel>
    </div>
  </>;
}

function PositionCard({ position }: { position: PaperPosition }) {
  const stop = finiteNumber(position.stop_loss);
  const target = finiteNumber(position.take_profit);
  const mark = finiteNumber(position.mark_price);
  const marker = stop !== null && target !== null && mark !== null && target > stop
    ? Math.max(0, Math.min(100, ((mark - stop) / (target - stop)) * 100)) : null;
  return <article className="rounded-2xl border border-border bg-muted/20 p-4">
    <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-sm font-medium">{position.symbol}</h3><p className="mt-1 text-[11px] text-muted-foreground">Long · {position.category} · {formatMoney(position.quantity, 6)} units</p></div><div className="text-right"><p className={cn("font-mono text-base", pnlClass(position.unrealized_pnl))}>{formatMoney(position.unrealized_pnl)} <span className="text-[10px]">USDT</span></p><p className="mt-1 text-[10px] text-muted-foreground">Unrealized PnL</p></div></div>
    <dl className="mt-4 grid grid-cols-2 gap-3 text-xs"><div><dt className="text-muted-foreground">Entry</dt><dd className="mt-1 font-mono">{formatMoney(position.entry_price, 4)}</dd></div><div className="text-right"><dt className="text-muted-foreground">Last mark</dt><dd className="mt-1 font-mono">{formatMoney(position.mark_price, 4)}</dd></div></dl>
    <div className="mt-5"><div className="relative h-1.5 rounded-full bg-gradient-to-r from-destructive/50 via-muted to-profit/50">{marker !== null && <span title="Last mark between stop and target" className="absolute -top-1 size-3.5 -translate-x-1/2 rounded-full border-2 border-background bg-foreground shadow" style={{ left: `${marker}%` }} />}</div><div className="mt-2 flex justify-between gap-3 text-[10px]"><span className="inline-flex items-center gap-1 text-muted-foreground"><ArrowDownToLine className="size-3" />Stop <span className="font-mono text-foreground">{formatMoney(position.stop_loss, 4)}</span></span><span className="inline-flex items-center gap-1 text-muted-foreground">Target <span className="font-mono text-foreground">{formatMoney(position.take_profit, 4)}</span><ArrowUpFromLine className="size-3" /></span></div></div>
    <p className="mt-4 text-[10px] text-muted-foreground">Opened {formatTime(position.opened_ms)} · {humanize(position.status)}</p>
  </article>;
}

function pnlClass(value: unknown) {
  const number = finiteNumber(value);
  return number === null || number === 0 ? "text-foreground" : number < 0 ? "text-destructive" : "text-profit";
}

function EmptyState({ icon: Icon, title, detail }: { icon: typeof Activity; title: string; detail: string }) {
  return <div className="flex flex-col items-center rounded-xl border border-dashed border-border px-5 py-8 text-center"><Icon className="mb-3 size-5 text-muted-foreground" /><p className="text-sm font-medium">{title}</p><p className="mt-1 max-w-md text-xs leading-relaxed text-muted-foreground">{detail}</p></div>;
}
