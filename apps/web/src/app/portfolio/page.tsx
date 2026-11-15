"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { WalletBalancePanel } from "@/components/WalletBalancePanel";
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
  StatusBadge,
  StatusIndicator,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { fetchAutonomySnapshot } from "@/lib/api/orchestrator";
import { toNumber } from "@/lib/formatting/decimal";
import { cn } from "@/lib/utils";

type Source = "paper" | "exchange";

export default function PortfolioPage() {
  const [source, setSource] = useState<Source>("paper");
  const autonomy = usePolledResource(fetchAutonomySnapshot, { intervalMs: 20_000, enabled: source === "paper" });
  const snap = autonomy.data;
  const journal = snap?.journal;
  const auth = snap?.session.authorization ?? null;
  const equity = toNumber(journal?.equity);
  const open = snap?.open_position ?? null;
  const exposure = open ? (toNumber(open.entry_price) ?? 0) * (toNumber(open.quantity) ?? 0) : 0;
  const available = equity !== null ? equity - exposure : null;
  const allocation = equity && equity > 0 ? Math.min(100, (exposure / equity) * 100) : null;

  return (
    <OverviewTemplate
      title="Portfolio"
      description="Pick an account source. Paper balances are simulated journal values; the exchange wallet is a read-only Bybit UNIFIED snapshot. The two are never mixed."
      modes={["readonly"]}
      toolbar={
        <Tabs value={source} onValueChange={(v) => setSource(v as Source)}>
          <TabsList className="w-auto" aria-label="Account source">
            <TabsTrigger value="paper">Paper journal</TabsTrigger>
            <TabsTrigger value="exchange">Exchange wallet</TabsTrigger>
          </TabsList>
        </Tabs>
      }
      actions={
        source === "paper" ? (
          <Button variant="outline" size="sm" className="rounded-full" onClick={() => void autonomy.refresh()} disabled={autonomy.refreshing}>
            <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", autonomy.refreshing && "animate-spin")} aria-hidden />
            Refresh
          </Button>
        ) : undefined
      }
    >
      {source === "paper" ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <ExecutionMode mode="paper" />
            <StatusBadge label="SIMULATED · not Bybit funds" tone="paper" />
            <StatusIndicator status={snap?.session.state ?? "UNKNOWN"} label={`Supervisor ${(snap?.session.state ?? "unknown").toLowerCase()}`} pulse />
            <DataFreshness at={snap?.session.heartbeat_ms ?? null} staleAfterMs={180_000} label="reconciled" missingLabel="No heartbeat" />
          </div>
          {autonomy.error && !snap ? <ErrorState title="Paper journal unavailable" code={autonomy.error.code} at={autonomy.error.at} onRetry={() => void autonomy.refresh()} /> : null}
          <MetricCardGrid>
            <MetricCard label="Paper balance" accent loading={autonomy.loading} value={<FinancialValue value={journal?.equity} digits={2} unit="USDT" size="lg" />} hint={journal?.available ? `Journal ${snap?.session.session_id ?? ""}` : "Journal unavailable"} muted={!journal?.available} />
            <MetricCard label="Available capital" loading={autonomy.loading} value={<FinancialValue value={available} digits={2} unit="USDT" size="lg" />} hint="Equity minus open notional" />
            <MetricCard label="PnL" loading={autonomy.loading} value={<span className="flex flex-wrap items-baseline gap-x-2"><FinancialValue value={journal?.realized_pnl} digits={2} signed showPlus size="lg" /><FinancialValue value={journal?.unrealized_pnl} digits={2} signed showPlus size="sm" prefix={<span className="text-muted-foreground">/</span>} /></span>} hint="Realized / unrealized" />
            <MetricCard label="Reconciliation" loading={autonomy.loading} value={<StatusIndicator status={snap?.journal.available ? (snap.worker_running ? "RUNNING" : "STALE") : "UNKNOWN"} label={snap?.journal.available ? (snap.worker_running ? "Journal in sync" : "Worker offline") : "Unknown"} size="md" />} hint={`Source: ${journal?.equity_source ?? "paper_journal"} · exchange equity excluded`} />
          </MetricCardGrid>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <SectionPanel title="Allocation" description="Share of paper equity committed to the open position.">
              {autonomy.loading ? <Skeleton className="h-24 rounded-xl" /> : (
                <div>
                  <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted" role="img" aria-label={`Allocation: ${allocation === null ? "unknown" : `${allocation.toFixed(1)}% in positions`}`}>
                    <div className="h-full bg-brand" style={{ width: `${allocation ?? 0}%` }} />
                  </div>
                  <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs">
                    <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-brand" aria-hidden />Positions {allocation === null ? "—" : `${allocation.toFixed(1)}%`}</span>
                    <span className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-muted-foreground/40" aria-hidden />Cash {allocation === null ? "—" : `${(100 - allocation).toFixed(1)}%`}</span>
                  </div>
                  {auth ? <p className="mt-3 text-[11px] text-muted-foreground">Authorized {auth.capital_usdt} USDT · risk {auth.risk_fraction} per trade · {auth.symbol} {auth.category}</p> : null}
                </div>
              )}
            </SectionPanel>
            <SectionPanel title="Holdings" description="Open paper position(s) at their last journal mark.">
              {autonomy.loading ? <Skeleton className="h-24 rounded-xl" /> : !open ? (
                <EmptyState title="No paper holdings" badge="Flat" description="The supervisor is flat. Cash equals equity." className="p-5" />
              ) : (
                <div className="rounded-xl border border-border bg-muted/40 p-3 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{open.symbol} · {open.category} · long</span>
                    <FinancialValue value={open.unrealized_pnl} digits={2} signed showPlus size="sm" />
                  </div>
                  <dl className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <div><dt className="text-muted-foreground">Qty</dt><dd><FinancialValue value={open.quantity} maxDigits={8} size="xs" /></dd></div>
                    <div><dt className="text-muted-foreground">Entry</dt><dd><FinancialValue value={open.entry_price} maxDigits={6} size="xs" /></dd></div>
                    <div><dt className="text-muted-foreground">Mark</dt><dd><FinancialValue value={open.mark_price} maxDigits={6} size="xs" fallback="unavailable" /></dd></div>
                    <div><dt className="text-muted-foreground">Notional</dt><dd><FinancialValue value={exposure} digits={2} size="xs" /></dd></div>
                  </dl>
                </div>
              )}
            </SectionPanel>
          </div>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label="Bybit UNIFIED · read-only" tone="info" />
            <span className="text-xs text-muted-foreground">A connected API key reads balances; it is not permission to trade. Open P&amp;L is perpetual unrealized P&amp;L only.</span>
          </div>
          <WalletBalancePanel />
        </>
      )}
    </OverviewTemplate>
  );
}
