"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Briefcase, ListOrdered, RefreshCw } from "lucide-react";

import { BorderBeam } from "@/components/magicui/border-beam";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetchPaperAccount,
  fetchPaperOrders,
  fetchPaperPositions,
  fetchPaperSessions,
  fetchPaperStatus,
} from "@/lib/paper/api";
import type { PaperAccount, PaperOrder, PaperPosition } from "@/lib/paper/types";
import { cn } from "@/lib/utils";

type LoadState = "loading" | "ready" | "disabled" | "unavailable" | "error";
type ViewTab = "overview" | "positions" | "orders";
type PositionFilter = "all" | "open" | "with_pnl";
type OrderFilter = "all" | "open" | "filled" | "rejected";

function formatQty(value: string | null | undefined) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return n.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function pnlTone(value: string | null | undefined) {
  const n = value == null || value === "" ? null : Number(value);
  if (n == null || !Number.isFinite(n)) return "text-muted-foreground";
  if (n > 0) return "text-emerald-400";
  if (n < 0) return "text-rose-400";
  return "text-muted-foreground";
}

function msLabel(ms: number | null | undefined) {
  if (ms == null) return "—";
  return new Date(ms).toLocaleString();
}

function FilterChip({
  active,
  children,
  onClick,
  count,
}: {
  active?: boolean;
  children: ReactNode;
  onClick: () => void;
  count?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "bg-muted/40 text-foreground hover:bg-muted/40 hover:text-foreground",
      )}
    >
      {children}
      {typeof count === "number" ? (
        <span className={cn("ml-1.5 tabular-nums", active ? "text-black/60" : "text-foreground")}>
          {count}
        </span>
      ) : null}
    </button>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-4" role="status" aria-label="Loading positions">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner className="size-4" />
        Checking paper read adapter…
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-border bg-muted/40 p-4">
            <Skeleton className="h-3 w-20 rounded-full" />
            <Skeleton className="mt-3 h-8 w-28 rounded-md" />
          </div>
        ))}
      </div>
      <Skeleton className="h-56 w-full rounded-2xl" />
    </div>
  );
}

export function PositionsOrdersPanel() {
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<ViewTab>("overview");
  const [positionFilter, setPositionFilter] = useState<PositionFilter>("all");
  const [orderFilter, setOrderFilter] = useState<OrderFilter>("all");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const load = useCallback(async (soft = false) => {
    if (soft) setRefreshing(true);
    else setState("loading");
    setError("");
    try {
      const status = await fetchPaperStatus();
      if (!status.ok) {
        setState("unavailable");
        setError(status.detail);
        setAccount(null);
        setPositions([]);
        setOrders([]);
        setSessionId(null);
        setNote("Live exchange position APIs stay gated. Paper journal is unreachable.");
        return;
      }
      if (!status.data.paper_read_api_enabled) {
        setState("disabled");
        setError("paper_read_api_disabled");
        setAccount(null);
        setPositions([]);
        setOrders([]);
        setSessionId(null);
        setNote(status.data.note || "Paper read API is off. No invented exposure.");
        return;
      }

      const sessions = await fetchPaperSessions();
      if (!sessions.ok) {
        setState("error");
        setError(sessions.detail);
        return;
      }
      const preferred = sessions.data.items[0]?.session_id ?? null;
      setSessionId(preferred);
      if (!preferred) {
        setState("ready");
        setAccount(null);
        setPositions([]);
        setOrders([]);
        setNote("Paper read is enabled, but no sessions exist yet.");
        return;
      }

      const [acct, openP, closedP, ords] = await Promise.all([
        fetchPaperAccount(preferred),
        fetchPaperPositions(preferred, { status: "OPEN" }),
        fetchPaperPositions(preferred, { status: "CLOSED" }),
        fetchPaperOrders(preferred),
      ]);

      const openItems = openP.ok ? openP.data.items : [];
      const closedItems = closedP.ok ? closedP.data.items : [];
      const orderItems = ords.ok ? ords.data.items : [];

      setAccount(acct.ok ? acct.data : null);
      setPositions([...openItems, ...closedItems]);
      setOrders(orderItems);
      setSelectedPositionId((prev) => prev ?? openItems[0]?.position_id ?? closedItems[0]?.position_id ?? null);
      setSelectedOrderId((prev) => prev ?? orderItems[0]?.order_id ?? null);
      setNote(
        acct.ok
          ? acct.data.note
          : "Session loaded without account summary — positions/orders still shown when present.",
      );
      setState("ready");
    } catch {
      setState("error");
      setError("api_unreachable");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openPositions = useMemo(
    () => positions.filter((p) => p.status === "OPEN"),
    [positions],
  );

  const positionCounts = useMemo(() => {
    const withPnl = positions.filter((p) => {
      const n = Number(p.unrealized_pnl ?? p.realized_pnl ?? 0);
      return Number.isFinite(n) && n !== 0;
    }).length;
    return {
      all: positions.length,
      open: openPositions.length,
      with_pnl: withPnl,
    };
  }, [positions, openPositions.length]);

  const filteredPositions = useMemo(() => {
    return positions.filter((p) => {
      if (positionFilter === "open") return p.status === "OPEN";
      if (positionFilter === "with_pnl") {
        const n = Number(p.unrealized_pnl ?? p.realized_pnl ?? 0);
        return Number.isFinite(n) && n !== 0;
      }
      return true;
    });
  }, [positions, positionFilter]);

  const orderCounts = useMemo(() => {
    const open = orders.filter((o) =>
      ["NEW", "PENDING", "ACCEPTED", "PARTIAL"].includes(o.status.toUpperCase()),
    ).length;
    const filled = orders.filter((o) => o.status.toUpperCase() === "FILLED").length;
    const rejected = orders.filter((o) =>
      ["REJECTED", "CANCELLED", "CANCELED"].includes(o.status.toUpperCase()),
    ).length;
    return { all: orders.length, open, filled, rejected };
  }, [orders]);

  const filteredOrders = useMemo(() => {
    return orders.filter((o) => {
      const status = o.status.toUpperCase();
      if (orderFilter === "open") {
        return ["NEW", "PENDING", "ACCEPTED", "PARTIAL"].includes(status);
      }
      if (orderFilter === "filled") return status === "FILLED";
      if (orderFilter === "rejected") {
        return ["REJECTED", "CANCELLED", "CANCELED"].includes(status);
      }
      return true;
    });
  }, [orders, orderFilter]);

  const selectedPosition =
    filteredPositions.find((p) => p.position_id === selectedPositionId) ??
    filteredPositions[0] ??
    null;

  const selectedOrder =
    filteredOrders.find((o) => o.order_id === selectedOrderId) ??
    filteredOrders[0] ??
    null;

  useEffect(() => {
    if (!selectedPositionId) return;
    if (filteredPositions.some((p) => p.position_id === selectedPositionId)) return;
    setSelectedPositionId(filteredPositions[0]?.position_id ?? null);
  }, [filteredPositions, selectedPositionId]);

  useEffect(() => {
    if (!selectedOrderId) return;
    if (filteredOrders.some((o) => o.order_id === selectedOrderId)) return;
    setSelectedOrderId(filteredOrders[0]?.order_id ?? null);
  }, [filteredOrders, selectedOrderId]);

  const metrics: Array<{
    label: string;
    value: string | null;
    pnl?: boolean;
  }> = [
    {
      label: "Open positions",
      value: account ? String(account.open_position_count) : String(openPositions.length),
    },
    {
      label: "Unrealized P&L",
      value:
        account?.unrealized_pnl ??
        (account?.unrealized_pnl_status === "unavailable" ||
        account?.unrealized_pnl_status === "stale_or_partial"
          ? account.unrealized_pnl_status
          : null),
      pnl: true,
    },
    {
      label: "Available",
      value: account?.available_balance ?? null,
    },
    {
      label: "Orders",
      value: String(orders.length),
    },
  ];

  return (
    <section className="relative overflow-hidden rounded-3xl border border-border/70 bg-card/60 p-5 md:p-6">
      <BorderBeam size={190} duration={13} colorFrom="#F7A600" colorTo="#FFCE6E" />
      <div className="relative z-10 flex flex-row items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-display text-xl tracking-tight">
            <Briefcase className="h-4 w-4 text-foreground" />
            Positions & orders
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Paper journal reads when enabled · live exchange stays gated
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="rounded-full"
          onClick={() => void load(true)}
          disabled={refreshing || state === "loading"}
        >
          {refreshing || state === "loading" ? (
            <Spinner className="mr-1" data-icon="inline-start" />
          ) : (
            <RefreshCw className="mr-1 h-3.5 w-3.5" />
          )}
          Refresh
        </Button>
      </div>

      <div className="relative z-10 mt-5">
        {state === "loading" ? <PanelSkeleton /> : null}

        {state === "disabled" || state === "unavailable" || state === "error" ? (
          <div className="space-y-4">
            <div className="rounded-2xl border border-border/60 bg-background/40 px-4 py-5">
              <Badge
                variant={state === "disabled" ? "warning" : "danger"}
                className="rounded-full"
              >
                {state === "disabled"
                  ? "Read off"
                  : state === "unavailable"
                    ? "Unavailable"
                    : "Error"}
              </Badge>
              <p className="mt-3 text-sm text-muted-foreground">
                {note || error || "Positions adapter is not connected."}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button asChild variant="secondary" size="sm" className="rounded-full">
                  <Link href="/paper">Open paper journal</Link>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-full"
                  onClick={() => void load(true)}
                  disabled={refreshing}
                >
                  {refreshing ? (
                    <Spinner className="mr-1" data-icon="inline-start" />
                  ) : (
                    <RefreshCw className="mr-1 h-3.5 w-3.5" />
                  )}
                  Retry
                </Button>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="relative overflow-hidden rounded-2xl border border-dashed border-border bg-muted/50 p-8 text-center">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-border bg-muted/40">
                  <Briefcase className="h-4 w-4 text-muted-foreground" />
                </div>
                <Badge variant="outline" className="mt-3 rounded-full">
                  Unavailable
                </Badge>
                <h3 className="mt-2 font-display text-lg">No open positions</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  A live snapshot is not connected. This panel will not invent exposure.
                </p>
              </div>
              <div className="relative overflow-hidden rounded-2xl border border-dashed border-border bg-muted/50 p-8 text-center">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-border bg-muted/40">
                  <ListOrdered className="h-4 w-4 text-muted-foreground" />
                </div>
                <Badge variant="outline" className="mt-3 rounded-full">
                  Unavailable
                </Badge>
                <h3 className="mt-2 font-display text-lg">No open orders</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Order history appears only from a verified read adapter.
                </p>
              </div>
            </div>
          </div>
        ) : null}

        {state === "ready" ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="rounded-full">
                SIMULATED / PAPER
              </Badge>
              {sessionId ? (
                <Badge variant="secondary" className="rounded-full font-mono text-[10px]">
                  {sessionId}
                </Badge>
              ) : (
                <Badge variant="warning" className="rounded-full">
                  No session
                </Badge>
              )}
              <Badge variant="outline" className="rounded-full">
                Read only
              </Badge>
              <Badge variant="secondary" className="rounded-full">
                Live exchange gated
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {metrics.map((m) => (
                <div
                  key={m.label}
                  className="rounded-2xl border border-border/60 bg-background/40 p-4"
                >
                  <p className="text-xs text-muted-foreground">{m.label}</p>
                  <p className={cn("mt-1 font-mono text-lg", m.pnl ? pnlTone(m.value) : undefined)}>
                    {m.value == null || m.value === ""
                      ? "—"
                      : m.pnl
                        ? formatQty(m.value)
                        : m.value}
                  </p>
                </div>
              ))}
            </div>

            <Tabs value={view} onValueChange={(v) => setView(v as ViewTab)}>
              <TabsList className="w-auto" aria-label="Positions views">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="positions">Positions</TabsTrigger>
                <TabsTrigger value="orders">Orders</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="mt-4 space-y-4">
                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-2xl border border-border bg-muted/50 p-4">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-foreground">Open exposure</p>
                        <p className="text-xs text-muted-foreground">
                          From paper journal only — nothing invented
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="rounded-full"
                        onClick={() => setView("positions")}
                      >
                        View all
                      </Button>
                    </div>
                    <ScrollArea className="h-56">
                      <div className="space-y-2 pr-3">
                        {openPositions.length === 0 ? (
                          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                            <Spinner className="size-4 opacity-40" />
                            <p className="text-sm text-muted-foreground">No open positions</p>
                          </div>
                        ) : (
                          openPositions.slice(0, 5).map((p) => (
                            <button
                              key={p.position_id}
                              type="button"
                              onClick={() => {
                                setSelectedPositionId(p.position_id);
                                setView("positions");
                              }}
                              className="w-full rounded-xl border border-border bg-muted/40 px-3 py-2.5 text-left transition-colors hover:bg-muted/40"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-medium text-foreground">{p.symbol}</span>
                                <Badge variant="outline" className="rounded-full">
                                  {p.side}
                                </Badge>
                              </div>
                              <div className="mt-2 flex justify-between text-[11px] text-muted-foreground">
                                <span className="font-mono">qty {formatQty(p.quantity)}</span>
                                <span className={cn("font-mono", pnlTone(p.unrealized_pnl))}>
                                  uPnL {formatQty(p.unrealized_pnl)}
                                </span>
                              </div>
                            </button>
                          ))
                        )}
                      </div>
                    </ScrollArea>
                  </div>

                  <div className="rounded-2xl border border-border bg-muted/50 p-4">
                    <p className="text-sm font-medium text-foreground">Snapshot</p>
                    <p className="text-xs text-muted-foreground">Adapter + session facts</p>
                    <Separator className="my-3 bg-muted/40" />
                    <ScrollArea className="h-56">
                      <dl className="space-y-2 pr-3 text-sm">
                        {[
                          ["Source", "Paper read API"],
                          ["Session", sessionId ?? "—"],
                          ["Open positions", String(openPositions.length)],
                          ["Closed positions", String(positions.length - openPositions.length)],
                          ["Orders", String(orders.length)],
                          ["Open / pending orders", String(orderCounts.open)],
                          ["Filled orders", String(orderCounts.filled)],
                          ["Currency", account?.currency ?? "—"],
                          ["Updated", account ? msLabel(account.updated_ms) : "—"],
                        ].map(([label, value]) => (
                          <div
                            key={label}
                            className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2"
                          >
                            <dt className="text-muted-foreground">{label}</dt>
                            <dd className="max-w-[60%] truncate font-mono text-foreground">
                              {value}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </ScrollArea>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="positions" className="mt-4 space-y-3">
                <div className="flex flex-wrap items-center gap-1.5 rounded-full border border-border bg-muted/70 p-1.5">
                  <FilterChip
                    active={positionFilter === "all"}
                    count={positionCounts.all}
                    onClick={() => setPositionFilter("all")}
                  >
                    All
                  </FilterChip>
                  <FilterChip
                    active={positionFilter === "open"}
                    count={positionCounts.open}
                    onClick={() => setPositionFilter("open")}
                  >
                    Open
                  </FilterChip>
                  <FilterChip
                    active={positionFilter === "with_pnl"}
                    count={positionCounts.with_pnl}
                    onClick={() => setPositionFilter("with_pnl")}
                  >
                    With P&L
                  </FilterChip>
                </div>

                <div className="h-[28rem] overflow-hidden rounded-2xl border border-border bg-muted/50">
                  <ResizablePanelGroup direction="horizontal" className="h-full">
                    <ResizablePanel defaultSize={62} minSize={40}>
                      <div className="flex h-full flex-col">
                        <div className="px-4 py-3">
                          <p className="text-sm font-medium text-foreground">Positions</p>
                          <p className="text-xs text-muted-foreground">
                            Showing {filteredPositions.length} of {positions.length}
                          </p>
                        </div>
                        <Separator className="bg-muted/40" />
                        <ScrollArea className="min-h-0 flex-1">
                          {filteredPositions.length === 0 ? (
                            <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
                              <Spinner className="size-4 opacity-35" />
                              <p className="text-sm text-muted-foreground">
                                No positions match this filter.
                              </p>
                            </div>
                          ) : (
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Symbol</TableHead>
                                  <TableHead>Side</TableHead>
                                  <TableHead>Qty</TableHead>
                                  <TableHead>Entry</TableHead>
                                  <TableHead>Status</TableHead>
                                  <TableHead>P&L</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {filteredPositions.map((p) => {
                                  const active = selectedPosition?.position_id === p.position_id;
                                  const pnl =
                                    p.status === "OPEN" ? p.unrealized_pnl : p.realized_pnl;
                                  return (
                                    <TableRow
                                      key={p.position_id}
                                      className={cn("cursor-pointer", active && "bg-muted/40")}
                                      onClick={() => setSelectedPositionId(p.position_id)}
                                      data-state={active ? "selected" : undefined}
                                    >
                                      <TableCell className="font-medium">{p.symbol}</TableCell>
                                      <TableCell>{p.side}</TableCell>
                                      <TableCell className="font-mono">
                                        {formatQty(p.quantity)}
                                      </TableCell>
                                      <TableCell className="font-mono">
                                        {formatQty(p.entry_price)}
                                      </TableCell>
                                      <TableCell>{p.status}</TableCell>
                                      <TableCell className={cn("font-mono", pnlTone(pnl))}>
                                        {formatQty(pnl)}
                                      </TableCell>
                                    </TableRow>
                                  );
                                })}
                              </TableBody>
                            </Table>
                          )}
                        </ScrollArea>
                      </div>
                    </ResizablePanel>
                    <ResizableHandle withHandle />
                    <ResizablePanel defaultSize={38} minSize={26}>
                      <div className="flex h-full flex-col p-4">
                        <p className="text-sm font-medium text-foreground">Position detail</p>
                        <p className="text-xs text-muted-foreground">
                          Select a row · ACCEPTED ≠ FILLED
                        </p>
                        <Separator className="my-3 bg-muted/40" />
                        <ScrollArea className="min-h-0 flex-1">
                          {selectedPosition ? (
                            <dl className="space-y-2 pr-3 text-sm">
                              {[
                                ["Symbol", selectedPosition.symbol],
                                ["Side", selectedPosition.side],
                                ["Status", selectedPosition.status],
                                ["Quantity", selectedPosition.quantity],
                                ["Entry", selectedPosition.entry_price],
                                ["Mark", selectedPosition.mark_price],
                                ["Stop loss", selectedPosition.stop_loss],
                                ["Take profit", selectedPosition.take_profit],
                                ["Unrealized P&L", selectedPosition.unrealized_pnl],
                                ["Realized P&L", selectedPosition.realized_pnl],
                                ["Opened", msLabel(selectedPosition.opened_ms)],
                                ["Closed", msLabel(selectedPosition.closed_ms)],
                                ["Signal", selectedPosition.entry_signal_id],
                              ].map(([label, value]) => (
                                <div
                                  key={label}
                                  className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2"
                                >
                                  <dt className="text-muted-foreground">{label}</dt>
                                  <dd
                                    className={cn(
                                      "max-w-[55%] truncate font-mono text-foreground",
                                      String(label).includes("P&L")
                                        ? pnlTone(value)
                                        : undefined,
                                    )}
                                  >
                                    {value == null || value === ""
                                      ? "—"
                                      : String(label).includes("P&L") ||
                                          ["Quantity", "Entry", "Mark", "Stop loss", "Take profit"].includes(
                                            String(label),
                                          )
                                        ? formatQty(value)
                                        : value}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          ) : (
                            <p className="text-sm text-muted-foreground">No position selected.</p>
                          )}
                        </ScrollArea>
                      </div>
                    </ResizablePanel>
                  </ResizablePanelGroup>
                </div>
              </TabsContent>

              <TabsContent value="orders" className="mt-4 space-y-3">
                <div className="flex flex-wrap items-center gap-1.5 rounded-full border border-border bg-muted/70 p-1.5">
                  <FilterChip
                    active={orderFilter === "all"}
                    count={orderCounts.all}
                    onClick={() => setOrderFilter("all")}
                  >
                    All
                  </FilterChip>
                  <FilterChip
                    active={orderFilter === "open"}
                    count={orderCounts.open}
                    onClick={() => setOrderFilter("open")}
                  >
                    Open
                  </FilterChip>
                  <FilterChip
                    active={orderFilter === "filled"}
                    count={orderCounts.filled}
                    onClick={() => setOrderFilter("filled")}
                  >
                    Filled
                  </FilterChip>
                  <FilterChip
                    active={orderFilter === "rejected"}
                    count={orderCounts.rejected}
                    onClick={() => setOrderFilter("rejected")}
                  >
                    Rejected
                  </FilterChip>
                </div>

                <div className="h-[28rem] overflow-hidden rounded-2xl border border-border bg-muted/50">
                  <ResizablePanelGroup direction="horizontal" className="h-full">
                    <ResizablePanel defaultSize={62} minSize={40}>
                      <div className="flex h-full flex-col">
                        <div className="px-4 py-3">
                          <p className="text-sm font-medium text-foreground">Orders</p>
                          <p className="text-xs text-muted-foreground">
                            Showing {filteredOrders.length} of {orders.length}
                          </p>
                        </div>
                        <Separator className="bg-muted/40" />
                        <ScrollArea className="min-h-0 flex-1">
                          {filteredOrders.length === 0 ? (
                            <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
                              <Spinner className="size-4 opacity-35" />
                              <p className="text-sm text-muted-foreground">
                                No orders match this filter.
                              </p>
                            </div>
                          ) : (
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Symbol</TableHead>
                                  <TableHead>Side</TableHead>
                                  <TableHead>Qty</TableHead>
                                  <TableHead>Status</TableHead>
                                  <TableHead>Fill</TableHead>
                                  <TableHead>Created</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {filteredOrders.map((o) => {
                                  const active = selectedOrder?.order_id === o.order_id;
                                  return (
                                    <TableRow
                                      key={o.order_id}
                                      className={cn("cursor-pointer", active && "bg-muted/40")}
                                      onClick={() => setSelectedOrderId(o.order_id)}
                                      data-state={active ? "selected" : undefined}
                                    >
                                      <TableCell className="font-medium">{o.symbol}</TableCell>
                                      <TableCell>{o.side}</TableCell>
                                      <TableCell className="font-mono">
                                        {formatQty(o.quantity)}
                                      </TableCell>
                                      <TableCell>{o.status}</TableCell>
                                      <TableCell className="font-mono">
                                        {formatQty(o.fill_price)}
                                      </TableCell>
                                      <TableCell className="font-mono text-[11px]">
                                        {msLabel(o.created_ms)}
                                      </TableCell>
                                    </TableRow>
                                  );
                                })}
                              </TableBody>
                            </Table>
                          )}
                        </ScrollArea>
                      </div>
                    </ResizablePanel>
                    <ResizableHandle withHandle />
                    <ResizablePanel defaultSize={38} minSize={26}>
                      <div className="flex h-full flex-col p-4">
                        <p className="text-sm font-medium text-foreground">Order detail</p>
                        <p className="text-xs text-muted-foreground">
                          Cancel / place controls are not in this UI
                        </p>
                        <Separator className="my-3 bg-muted/40" />
                        <ScrollArea className="min-h-0 flex-1">
                          {selectedOrder ? (
                            <dl className="space-y-2 pr-3 text-sm">
                              {[
                                ["Order", selectedOrder.order_id],
                                ["Symbol", selectedOrder.symbol],
                                ["Side", selectedOrder.side],
                                ["Status", selectedOrder.status],
                                ["Quantity", selectedOrder.quantity],
                                ["Intended", selectedOrder.intended_entry_price],
                                ["Fill", selectedOrder.fill_price],
                                ["Fee", selectedOrder.fee],
                                ["Slippage", selectedOrder.slippage],
                                ["Rejection", selectedOrder.rejection_reason],
                                ["Signal", selectedOrder.source_signal_id],
                                ["Created", msLabel(selectedOrder.created_ms)],
                                ["Filled", msLabel(selectedOrder.filled_ms)],
                              ].map(([label, value]) => (
                                <div
                                  key={label}
                                  className="flex items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-3 py-2"
                                >
                                  <dt className="text-muted-foreground">{label}</dt>
                                  <dd className="max-w-[55%] truncate font-mono text-foreground">
                                    {value == null || value === "" ? "—" : value}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          ) : (
                            <p className="text-sm text-muted-foreground">No order selected.</p>
                          )}
                        </ScrollArea>
                      </div>
                    </ResizablePanel>
                  </ResizablePanelGroup>
                </div>
              </TabsContent>
            </Tabs>

            {note ? <p className="text-[11px] text-muted-foreground">{note}</p> : null}
            <p className="text-[11px] text-muted-foreground">
              Paper data only · ACCEPTED does not mean FILLED · place/cancel stay off
            </p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
