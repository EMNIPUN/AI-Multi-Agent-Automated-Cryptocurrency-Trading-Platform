"use client";

import { useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import {
  DataTable,
  EmptyState,
  ErrorState,
  ExecutionMode,
  FinancialValue,
  MetricCard,
  MetricCardGrid,
  ReasonList,
  StatusBadge,
  StatusIndicator,
  TradingTerminalTemplate,
  type DataTableColumn,
} from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { filterRows, rowsFromReadApi, rowsFromSupervisorReport, type PositionFilters, type PositionRow } from "@/features/positions/lib/position-rows";
import { usePolledResource } from "@/hooks/use-polled-resource";
import { getJson, type ApiResult } from "@/lib/api/client";
import { fetchOrchestratorStatus, fetchPaperReport } from "@/lib/api/orchestrator";
import { formatDateTime, formatRelative } from "@/lib/formatting/time";
import type { PaperPosition as ReadApiPosition, PaperSessionSummary, PaperStatus } from "@/lib/paper/types";
import { useExecutionState } from "@/providers/ExecutionStateProvider";
import { cn } from "@/lib/utils";

/** Read-API archive: status → sessions → positions for every session (bounded). */
async function fetchReadApiPositions(init: RequestInit): Promise<ApiResult<{ enabled: boolean; sessions: PaperSessionSummary[]; positions: ReadApiPosition[]; note: string | null }>> {
  const status = await getJson<PaperStatus>("/api/paper/status", init);
  if (!status.ok) return status;
  if (!status.data.paper_read_api_enabled || !status.data.db_present) {
    return { ok: true, status: 200, at: Date.now(), data: { enabled: status.data.paper_read_api_enabled, sessions: [], positions: [], note: status.data.note } };
  }
  const sessions = await getJson<{ items: PaperSessionSummary[] }>("/api/paper/sessions", init);
  if (!sessions.ok) return sessions;
  const list = sessions.data.items.slice(0, 8);
  const results = await Promise.all(list.map((s) => getJson<{ items: ReadApiPosition[] }>(`/api/paper/sessions/${encodeURIComponent(s.session_id)}/positions`, init)));
  const positions = results.flatMap((r) => (r.ok ? r.data.items : []));
  return { ok: true, status: 200, at: Date.now(), data: { enabled: true, sessions: list, positions, note: status.data.note } };
}

const COLUMNS: DataTableColumn<PositionRow>[] = [
  { id: "symbol", header: "Symbol", cell: (r) => <span className="font-medium text-foreground">{r.symbol}</span>, accessor: (r) => r.symbol },
  { id: "market", header: "Market", cell: (r) => <span className="uppercase text-muted-foreground">{r.market}</span>, accessor: (r) => r.market, hideBelow: "md" },
  { id: "side", header: "Side", cell: (r) => <StatusBadge label={r.side} tone={r.side === "LONG" || r.side === "BUY" ? "ok" : "danger"} />, accessor: (r) => r.side },
  { id: "quantity", header: "Qty", align: "right", cell: (r) => <FinancialValue value={r.quantity} maxDigits={8} size="xs" />, accessor: (r) => r.quantity ?? "" },
  { id: "entry", header: "Entry", align: "right", cell: (r) => <FinancialValue value={r.entry_price} maxDigits={6} size="xs" />, accessor: (r) => r.entry_price ?? "" },
  { id: "mark", header: "Mark / exit", align: "right", cell: (r) => <FinancialValue value={r.mark_price ?? r.exit_price} maxDigits={6} size="xs" fallback={r.status === "OPEN" ? "unavailable" : "—"} />, accessor: (r) => r.mark_price ?? r.exit_price ?? "", hideBelow: "sm" },
  { id: "upnl", header: "Unrealized", align: "right", cell: (r) => <FinancialValue value={r.unrealized_pnl} digits={2} signed showPlus size="xs" fallback={r.status === "OPEN" ? "unavailable" : "—"} />, accessor: (r) => r.unrealized_pnl ?? "", hideBelow: "md" },
  { id: "rpnl", header: "Realized", align: "right", cell: (r) => <FinancialValue value={r.realized_pnl} digits={2} signed showPlus size="xs" />, accessor: (r) => r.realized_pnl ?? "" },
  { id: "sl", header: "SL", align: "right", cell: (r) => <FinancialValue value={r.stop_loss} maxDigits={6} size="xs" />, accessor: (r) => r.stop_loss ?? "", hideBelow: "lg" },
  { id: "tp", header: "TP", align: "right", cell: (r) => <FinancialValue value={r.take_profit} maxDigits={6} size="xs" />, accessor: (r) => r.take_profit ?? "", hideBelow: "lg" },
  { id: "status", header: "Status", cell: (r) => <StatusIndicator status={r.status === "OPEN" ? "RUNNING" : r.status === "CLOSED" ? "OK" : r.status} label={r.status} />, accessor: (r) => r.status },
  { id: "mode", header: "Mode", cell: (r) => <ExecutionMode mode={r.mode === "PAPER" ? "paper" : r.mode === "TESTNET" ? "testnet" : "live"} />, accessor: (r) => r.mode, hideBelow: "xl" },
  { id: "updated", header: "Last update", cell: (r) => <span className="text-muted-foreground" title={formatDateTime(r.updated_ms)}>{formatRelative(r.updated_ms)}</span>, accessor: (r) => r.updated_ms ?? 0, hideBelow: "lg" },
];

export function PositionsWorkspace() {
  const exec = useExecutionState();
  const status = usePolledResource(fetchOrchestratorStatus, { intervalMs: 20_000 });
  const report = usePolledResource(fetchPaperReport, { intervalMs: 20_000 });
  const archive = usePolledResource(fetchReadApiPositions, { intervalMs: 60_000 });
  const [filters, setFilters] = useState<PositionFilters>({ status: "all", market: "all", mode: "all" });
  const [selected, setSelected] = useState<PositionRow | null>(null);

  const rows = useMemo(() => {
    const sup = rowsFromSupervisorReport(report.data, status.data?.session_id ?? null);
    const api = rowsFromReadApi(archive.data?.positions ?? []);
    return [...sup, ...api];
  }, [report.data, status.data?.session_id, archive.data]);
  const visible = useMemo(() => filterRows(rows, filters), [rows, filters]);
  const openRows = rows.filter((r) => r.status.toUpperCase() === "OPEN");
  const loading = report.loading && archive.loading;

  return (
    <TradingTerminalTemplate
      title="Positions & Orders"
      description="Paper positions from the supervisor journal and archived read-API sessions. Live exchange positions are only read through the Orchestrator's Bybit tools. No cancel or modify controls exist here."
      modes={["paper", "readonly"]}
      actions={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => { void report.refresh(); void archive.refresh(); }} disabled={report.refreshing || archive.refreshing}>
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", (report.refreshing || archive.refreshing) && "animate-spin")} aria-hidden />
          Refresh
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <ExecutionMode mode="paper" />
        <ExecutionMode mode="testnet" armed={exec.data?.testnet === "armed"} />
        <ExecutionMode mode="live" armed={exec.data?.live === "armed_approve_required"} />
        <span>· TESTNET/MAINNET rows appear only when those lanes report positions through verified adapters.</span>
      </div>

      {report.error && !report.data ? <ErrorState title="Supervisor journal unavailable" code={report.error.code} at={report.error.at} onRetry={() => void report.refresh()} compact /> : null}

      <MetricCardGrid>
        <MetricCard label="Open positions" accent loading={loading} value={<span className="font-mono">{openRows.length}</span>} hint={status.data?.session_id ? `Supervisor session ${status.data.session_id}` : "No supervisor session"} />
        <MetricCard label="Unrealized PnL" loading={loading} value={<FinancialValue value={report.data?.unrealized_pnl} digits={2} signed showPlus unit="USDT" size="lg" />} hint="Supervisor journal marks" />
        <MetricCard label="Realized PnL" loading={loading} value={<FinancialValue value={report.data?.realized_pnl} digits={2} signed showPlus unit="USDT" size="lg" />} hint={`${report.data?.closed_trades ?? 0} closed · fees ${report.data?.fees_paid ?? "—"}`} />
        <MetricCard label="Archived sessions" loading={archive.loading} value={<span className="font-mono">{archive.data?.sessions.length ?? 0}</span>} hint={archive.data?.enabled ? (archive.data.note ?? "Paper read API") : "Paper read API off"} muted={!archive.data?.enabled} />
      </MetricCardGrid>

      <SectionPanel title="Positions" description="Search, sort and toggle columns. Click a row for the full record. ACCEPTED does not mean FILLED.">
        {loading ? (
          <Skeleton className="h-64 w-full rounded-xl" />
        ) : rows.length === 0 ? (
          <EmptyState title="No paper positions yet" badge="Empty" description="Rows appear when the supervisor opens a paper position or an archived read-API session has records. Nothing is invented." />
        ) : (
          <DataTable
            rows={visible}
            columns={COLUMNS}
            rowKey={(r) => r.key}
            caption="Paper positions and closed trades"
            initialSort={{ id: "updated", desc: true }}
            onRowClick={setSelected}
            selectedKey={selected?.key ?? null}
            pageSize={20}
            toolbar={
              <>
                <Tabs value={filters.status} onValueChange={(v) => setFilters((f) => ({ ...f, status: v as PositionFilters["status"] }))}>
                  <TabsList className="h-8 w-auto p-1" aria-label="Status filter">
                    <TabsTrigger value="all" className="px-2.5 py-1 text-xs">All</TabsTrigger>
                    <TabsTrigger value="open" className="px-2.5 py-1 text-xs">Open</TabsTrigger>
                    <TabsTrigger value="closed" className="px-2.5 py-1 text-xs">Closed</TabsTrigger>
                  </TabsList>
                </Tabs>
                <Tabs value={filters.market} onValueChange={(v) => setFilters((f) => ({ ...f, market: v as PositionFilters["market"] }))}>
                  <TabsList className="h-8 w-auto p-1" aria-label="Market filter">
                    <TabsTrigger value="all" className="px-2.5 py-1 text-xs">All markets</TabsTrigger>
                    <TabsTrigger value="linear" className="px-2.5 py-1 text-xs">Perp</TabsTrigger>
                    <TabsTrigger value="spot" className="px-2.5 py-1 text-xs">Spot</TabsTrigger>
                  </TabsList>
                </Tabs>
                <Tabs value={filters.mode} onValueChange={(v) => setFilters((f) => ({ ...f, mode: v as PositionFilters["mode"] }))}>
                  <TabsList className="h-8 w-auto p-1" aria-label="Mode filter">
                    <TabsTrigger value="all" className="px-2.5 py-1 text-xs">All modes</TabsTrigger>
                    <TabsTrigger value="PAPER" className="px-2.5 py-1 text-xs">Paper</TabsTrigger>
                    <TabsTrigger value="TESTNET" className="px-2.5 py-1 text-xs">Testnet</TabsTrigger>
                    <TabsTrigger value="MAINNET" className="px-2.5 py-1 text-xs">Mainnet</TabsTrigger>
                  </TabsList>
                </Tabs>
              </>
            }
          />
        )}
      </SectionPanel>

      <SectionPanel title="Pending paper orders" description="Queued entries and exits waiting for the next confirmed candle.">
        {report.data?.pending_orders && report.data.pending_orders.length > 0 ? (
          <ul className="space-y-1.5">
            {report.data.pending_orders.map((o) => (
              <li key={o.order_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs">
                <span className="font-medium text-foreground">{o.symbol} · {o.side} <FinancialValue value={o.quantity} maxDigits={8} size="xs" /></span>
                <span className="text-muted-foreground">{o.status} · {formatDateTime(o.created_ms)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">No pending paper orders.</p>
        )}
      </SectionPanel>

      <Sheet open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent side="right" className="w-[min(100%,26rem)] overflow-y-auto sm:max-w-md">
          <SheetHeader className="pr-8">
            <SheetTitle>{selected ? `${selected.symbol} · ${selected.status}` : "Position"}</SheetTitle>
            <SheetDescription>Full record as the journal reports it. Decimal fields are shown exactly.</SheetDescription>
          </SheetHeader>
          {selected ? (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-2">
                <ExecutionMode mode="paper" />
                <StatusBadge label={selected.source === "supervisor_journal" ? "Supervisor journal" : "Paper read API"} tone="neutral" />
                <StatusIndicator status={selected.status === "OPEN" ? "RUNNING" : "OK"} label={selected.status} />
              </div>
              <dl className="space-y-1.5 text-sm">
                {[
                  ["Session", selected.session_id ?? "—"],
                  ["Side", selected.side],
                  ["Quantity", <FinancialValue key="q" value={selected.quantity} maxDigits={8} size="xs" />],
                  ["Entry", <FinancialValue key="e" value={selected.entry_price} maxDigits={6} size="xs" />],
                  ["Mark", <FinancialValue key="m" value={selected.mark_price} maxDigits={6} size="xs" fallback="unavailable" />],
                  ["Exit", <FinancialValue key="x" value={selected.exit_price} maxDigits={6} size="xs" />],
                  ["Stop loss", <FinancialValue key="sl" value={selected.stop_loss} maxDigits={6} size="xs" />],
                  ["Take profit", <FinancialValue key="tp" value={selected.take_profit} maxDigits={6} size="xs" />],
                  ["Unrealized PnL", <FinancialValue key="u" value={selected.unrealized_pnl} digits={2} signed showPlus size="xs" />],
                  ["Realized PnL", <FinancialValue key="r" value={selected.realized_pnl} digits={2} signed showPlus size="xs" />],
                  ["Opened", formatDateTime(selected.opened_ms)],
                  ["Closed", formatDateTime(selected.closed_ms)],
                  ["Entry signal", selected.entry_signal_id ?? "—"],
                ].map(([k, v]) => (
                  <div key={String(k)} className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="min-w-0 truncate text-right font-mono text-xs text-foreground">{v}</dd>
                  </div>
                ))}
              </dl>
              {selected.exit_reason ? (
                <div>
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Exit reason</p>
                  <ReasonList codes={[selected.exit_reason]} />
                </div>
              ) : null}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </TradingTerminalTemplate>
  );
}
