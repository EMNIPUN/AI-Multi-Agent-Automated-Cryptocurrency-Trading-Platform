"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  resolvePaperUiMode,
} from "@/lib/paper/api";
import type {
  PaperAccount,
  PaperOrder,
  PaperPosition,
  PaperSessionSummary,
  PaperStatus,
} from "@/lib/paper/types";

function msToUtc(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return new Date(ms).toISOString();
}

function Money({ value }: { value: string | null | undefined }) {
  if (value == null || value === "") {
    return <span className="text-muted-foreground">unavailable</span>;
  }
  return <span className="font-mono">{value}</span>;
}

function PaperPageInner() {
  const search = useSearchParams();
  const sessionParam = search.get("session");
  const symbolParam = search.get("symbol");
  const signalParam = search.get("signal");

  const [category, setCategory] = useState<"spot" | "linear">("spot");
  const [symbol, setSymbol] = useState<string>(symbolParam || "ALL");
  const [sessionId, setSessionId] = useState<string>(sessionParam || "");
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [sessions, setSessions] = useState<PaperSessionSummary[]>([]);
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [openPositions, setOpenPositions] = useState<PaperPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [signalNote, setSignalNote] = useState<string | null>(null);

  const refreshSessionData = useCallback(
    async (sid: string, sym: string) => {
      const symFilter = sym !== "ALL" ? sym : undefined;
      const [acct, openP, closedP, ords] = await Promise.all([
        fetchPaperAccount(sid),
        fetchPaperPositions(sid, { status: "OPEN", symbol: symFilter }),
        fetchPaperPositions(sid, { status: "CLOSED", symbol: symFilter }),
        fetchPaperOrders(sid, { symbol: symFilter }),
      ]);
      setAccount(acct.ok ? acct.data : null);
      setOpenPositions(openP.ok ? openP.data.items : []);
      setClosedPositions(closedP.ok ? closedP.data.items : []);
      setOrders(ords.ok ? ords.data.items : []);
      if (!acct.ok) setError(acct.detail);
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      const st = await fetchPaperStatus();
      if (cancelled) return;
      if (!st.ok) {
        setStatus(null);
        setSessions([]);
        setError(st.detail);
        setLoading(false);
        return;
      }
      setStatus(st.data);
      if (!st.data.paper_read_api_enabled) {
        setSessions([]);
        setAccount(null);
        setOpenPositions([]);
        setClosedPositions([]);
        setOrders([]);
        setLoading(false);
        return;
      }
      const sess = await fetchPaperSessions();
      if (cancelled) return;
      if (!sess.ok) {
        setError(sess.detail);
        setSessions([]);
        setLoading(false);
        return;
      }
      setSessions(sess.data.items);
      const preferred =
        (sessionParam &&
        sess.data.items.some((s) => s.session_id === sessionParam)
          ? sessionParam
          : null) ||
        sess.data.items[0]?.session_id ||
        "";
      setSessionId(preferred);
      if (preferred && category === "spot") {
        await refreshSessionData(preferred, symbolParam || symbol);
      }
      if (signalParam) {
        const linkRes = await fetch(
          `/api/paper/orders/by-signal/${encodeURIComponent(signalParam)}`,
          { cache: "no-store" },
        );
        const linkJson = await linkRes.json().catch(() => null);
        if (!cancelled) {
          setSignalNote(
            linkJson?.linked
              ? `Signal ${signalParam}: ${linkJson.message}`
              : `No paper trade linked to this signal (${signalParam})`,
          );
        }
      } else if (!cancelled) {
        setSignalNote(null);
      }
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionParam, symbolParam, signalParam, category]);

  useEffect(() => {
    if (!sessionId || category !== "spot" || !status?.paper_read_api_enabled) return;
    void refreshSessionData(sessionId, symbol);
  }, [sessionId, symbol, category, status?.paper_read_api_enabled, refreshSessionData]);

  const mode = useMemo(
    () =>
      resolvePaperUiMode({
        loading,
        category,
        statusOk: Boolean(status) || !error,
        enabled: Boolean(status?.paper_read_api_enabled),
        apiError: Boolean(error && !status),
        sessionCount: sessions.length,
      }),
    [loading, category, error, status, sessions.length],
  );

  const symbolOptions = useMemo(() => {
    const set = new Set<string>(["ALL", "BTCUSDT", "ETHUSDT", "SOLUSDT"]);
    for (const p of [...openPositions, ...closedPositions]) set.add(p.symbol);
    for (const o of orders) set.add(o.symbol);
    return Array.from(set);
  }, [openPositions, closedPositions, orders]);

  if (mode === "loading" && !status) {
    return <LogoLoader fullScreen label="Loading paper journal…" />;
  }

  return (
    <div>
      <PageHeader
        title="Paper trading journal"
        description="Read-only view of local simulated sessions. No exchange orders. SIMULATED / PAPER ONLY."
      />
      {sessionId ? (
        <p className="mb-3 text-sm">
          <Link
            className="underline text-muted-foreground hover:text-foreground"
            href={`/analytics?session=${encodeURIComponent(sessionId)}`}
          >
            Open paper analytics for this session
          </Link>
        </p>
      ) : null}

      {mode === "disabled" ? (
        <DataModeBanner
          mode="demo"
          notes={[
            "PAPER_READ_API_ENABLED is false — paper journal API disabled.",
            "Enable locally on FastAPI to inspect persisted 65A sessions. Broker auto-attach stays OFF.",
          ]}
        />
      ) : null}
      {mode === "unavailable" ? (
        <DataModeBanner
          mode="demo"
          notes={[
            "Paper API unreachable. Start FastAPI on loopback with PAPER_READ_API_ENABLED=true.",
            error || "api_unavailable",
          ]}
        />
      ) : null}
      {mode === "unsupported_futures" ? (
        <DataModeBanner
          mode="demo"
          notes={[
            "Futures / linear paper simulation is not supported in Milestone 1.",
            "65A broker supports spot-like unleveraged longs only. Switch category to Spot.",
          ]}
        />
      ) : null}
      {status?.paper_read_api_enabled && category === "spot" ? (
        <DataModeBanner
          mode="live"
          notes={[
            "SIMULATED / PAPER ONLY — balances are virtual USDT, not Bybit funds.",
            status.note,
            signalNote || (account?.session_id ? `Session ${account.session_id}` : "Select a session"),
          ]}
        />
      ) : null}

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Market category</div>
          <Select
            value={category}
            onValueChange={(v) => setCategory(v as "spot" | "linear")}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="spot">Spot</SelectItem>
              <SelectItem value="linear">Futures (unsupported)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Session</div>
          <Select
            value={sessionId || undefined}
            onValueChange={setSessionId}
            disabled={sessions.length === 0 || category !== "spot"}
          >
            <SelectTrigger className="w-[240px]">
              <SelectValue placeholder="No sessions" />
            </SelectTrigger>
            <SelectContent>
              {sessions.map((s) => (
                <SelectItem key={s.session_id} value={s.session_id}>
                  {s.session_id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-muted-foreground">Symbol filter</div>
          <Select value={symbol} onValueChange={setSymbol} disabled={category !== "spot"}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {symbolOptions.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Badge variant="outline">No order submission</Badge>
        <Link href="/agents" className="text-sm text-primary underline-offset-4 hover:underline">
          Back to Agent Studio
        </Link>
      </div>

      {mode === "no_sessions" && category === "spot" ? (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>No paper sessions</CardTitle>
            <CardDescription>
              Run the local synthetic demo intentionally, then set PAPER_SQLITE_PATH. Page loads
              never create sessions or trades.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <code>python scripts/demo_paper_broker_65a.py</code>
          </CardContent>
        </Card>
      ) : null}

      {mode === "ready" && account ? (
        <>
          <div className="mb-4 grid gap-4 md:grid-cols-3 lg:grid-cols-6">
            <Metric title="Initial" value={account.initial_balance} />
            <Metric title="Available" value={account.available_balance} />
            <Metric title="Reserved" value={account.reserved_capital} />
            <Metric title="Realized PnL" value={account.realized_pnl} />
            <Metric title="Fees paid" value={account.fees_paid} />
            <Metric
              title="Marked equity"
              value={account.marked_equity_status === "ok" ? account.marked_equity : null}
              hint={account.marked_equity_status}
            />
          </div>
          <p className="mb-4 text-xs text-muted-foreground">
            Unrealized:{" "}
            {account.unrealized_pnl_status === "ok" || account.unrealized_pnl_status === "none"
              ? account.unrealized_pnl
              : "unavailable / stale"}{" "}
            · Status {account.status} · {account.data_label}
          </p>

          <Section title="Open positions">
            {openPositions.length === 0 ? (
              <Empty>No open positions</Empty>
            ) : (
              <PositionsTable rows={openPositions} open />
            )}
          </Section>

          <Section title="Order history">
            {orders.length === 0 ? (
              <Empty>No orders</Empty>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Qty</TableHead>
                    <TableHead>Fill</TableHead>
                    <TableHead>Time (UTC)</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.map((o) => (
                    <TableRow key={o.order_id}>
                      <TableCell>{o.symbol}</TableCell>
                      <TableCell>{o.side}</TableCell>
                      <TableCell>{o.status}</TableCell>
                      <TableCell className="font-mono">{o.quantity}</TableCell>
                      <TableCell className="font-mono">{o.fill_price ?? "—"}</TableCell>
                      <TableCell className="text-xs">
                        {msToUtc(o.filled_ms ?? o.created_ms)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Section>

          <Section title="Closed trades">
            {closedPositions.length === 0 ? (
              <Empty>No closed trades</Empty>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Entry</TableHead>
                    <TableHead>Exit</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Entry fee</TableHead>
                    <TableHead>Exit fee</TableHead>
                    <TableHead>Net PnL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {closedPositions.map((p) => (
                    <TableRow key={p.position_id}>
                      <TableCell>{p.symbol}</TableCell>
                      <TableCell className="font-mono">{p.entry_price}</TableCell>
                      <TableCell className="font-mono">{p.exit_price ?? "—"}</TableCell>
                      <TableCell>{p.exit_reason ?? "—"}</TableCell>
                      <TableCell className="font-mono">{p.entry_fee}</TableCell>
                      <TableCell className="font-mono">{p.exit_fee}</TableCell>
                      <TableCell className="font-mono">{p.realized_pnl}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Section>
        </>
      ) : null}
    </div>
  );
}

export default function PaperPage() {
  return (
    <Suspense fallback={<LogoLoader fullScreen label="Loading paper journal…" />}>
      <PaperPageInner />
    </Suspense>
  );
}

function Metric({
  title,
  value,
  hint,
}: {
  title: string;
  value: string | null | undefined;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>
          {title}
          {hint && hint !== "ok" ? ` (${hint})` : ""}
        </CardDescription>
        <CardTitle className="text-lg">
          <Money value={value} />
        </CardTitle>
      </CardHeader>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>SIMULATED / PAPER ONLY</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function PositionsTable({ rows, open }: { rows: PaperPosition[]; open?: boolean }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Coin</TableHead>
          <TableHead>Side</TableHead>
          <TableHead>Qty</TableHead>
          <TableHead>Entry</TableHead>
          <TableHead>SL</TableHead>
          <TableHead>TP</TableHead>
          {open ? <TableHead>Mark</TableHead> : null}
          {open ? <TableHead>uPnL</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((p) => (
          <TableRow key={p.position_id}>
            <TableCell>{p.symbol}</TableCell>
            <TableCell>{p.side}</TableCell>
            <TableCell className="font-mono">{p.quantity}</TableCell>
            <TableCell className="font-mono">{p.entry_price}</TableCell>
            <TableCell className="font-mono">{p.stop_loss ?? "—"}</TableCell>
            <TableCell className="font-mono">{p.take_profit ?? "—"}</TableCell>
            {open ? (
              <TableCell className="font-mono">
                {p.unrealized_pnl_status === "ok" ? p.mark_price : "unavailable"}
              </TableCell>
            ) : null}
            {open ? (
              <TableCell className="font-mono">
                {p.unrealized_pnl_status === "ok" ? p.unrealized_pnl : "unavailable"}
              </TableCell>
            ) : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
