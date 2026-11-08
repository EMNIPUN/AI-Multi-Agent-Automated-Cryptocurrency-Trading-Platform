"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  fetchPaperAnalytics,
  fetchPaperAnalyticsEquity,
  fetchPaperAnalyticsSymbols,
  fetchPaperAnalyticsTrades,
  fetchPaperSessions,
  fetchPaperStatus,
  resolvePaperUiMode,
} from "@/lib/paper/api";
import {
  closedTradeRowKey,
  formatDecimalDisplay,
  formatHoldingDuration,
  formatOptionalMetric,
  formatUtcMs,
  signedMoneyClass,
  tradeOutcome,
  validateExitDateRange,
} from "@/lib/paper/analytics-format";
import type {
  PaperAnalyticsEquityResponse,
  PaperAnalyticsResponse,
  PaperAnalyticsTradeItem,
  PaperSessionSummary,
  PaperStatus,
  SymbolBreakdownApi,
} from "@/lib/paper/types";

const TRADE_PAGE_SIZE = 25;
const PAPER_ONLY =
  "SIMULATED / PAPER ONLY — NOT LIVE ACCOUNT PERFORMANCE";

function MetricCard({
  label,
  value,
  hint,
  valueClassName,
}: {
  label: string;
  value: string;
  hint?: string;
  valueClassName?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className={`text-lg ${valueClassName ?? "font-mono"}`}>{value}</CardTitle>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </CardHeader>
    </Card>
  );
}

export function AnalyticsDashboard() {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const sessionParam = search.get("session") || search.get("session_id") || "";
  const symbolParam = search.get("symbol") || "ALL";
  const seriesParam =
    search.get("series") === "realized_balance" ? "realized_balance" : "marked";
  const fromParam = search.get("exit_from") || "";
  const toParam = search.get("exit_to") || "";
  const offsetParam = Math.max(0, Number(search.get("offset") || "0") || 0);

  const [sessionId, setSessionId] = useState(sessionParam);
  const [symbol, setSymbol] = useState(symbolParam);
  const [series, setSeries] = useState<"marked" | "realized_balance">(seriesParam);
  const [exitFrom, setExitFrom] = useState(fromParam);
  const [exitTo, setExitTo] = useState(toParam);
  const [tradeOffset, setTradeOffset] = useState(offsetParam);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [sessions, setSessions] = useState<PaperSessionSummary[]>([]);
  const [analytics, setAnalytics] = useState<PaperAnalyticsResponse | null>(null);
  const [trades, setTrades] = useState<PaperAnalyticsTradeItem[]>([]);
  const [tradeWarnings, setTradeWarnings] = useState<string[]>([]);
  const [symbols, setSymbols] = useState<SymbolBreakdownApi[]>([]);
  const [equity, setEquity] = useState<PaperAnalyticsEquityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filterError, setFilterError] = useState<string | null>(null);

  const syncUrl = useCallback(
    (next: {
      session?: string;
      symbol?: string;
      series?: string;
      exitFrom?: string;
      exitTo?: string;
      offset?: number;
    }) => {
      const qs = new URLSearchParams();
      const sid = next.session ?? sessionId;
      const sym = next.symbol ?? symbol;
      const ser = next.series ?? series;
      const from = next.exitFrom ?? exitFrom;
      const to = next.exitTo ?? exitTo;
      const off = next.offset ?? tradeOffset;
      if (sid) qs.set("session", sid);
      if (sym && sym !== "ALL") qs.set("symbol", sym);
      if (ser && ser !== "marked") qs.set("series", ser);
      if (from) qs.set("exit_from", from);
      if (to) qs.set("exit_to", to);
      if (off > 0) qs.set("offset", String(off));
      const q = qs.toString();
      router.replace(q ? `${pathname}?${q}` : pathname, { scroll: false });
    },
    [sessionId, symbol, series, exitFrom, exitTo, tradeOffset, router, pathname],
  );

  const loadBootstrap = useCallback(async () => {
    setLoading(true);
    setError(null);
    const st = await fetchPaperStatus();
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
      setAnalytics(null);
      setTrades([]);
      setEquity(null);
      setSymbols([]);
      setLoading(false);
      return;
    }
    if (!st.data.db_present) {
      setSessions([]);
      setError("paper_db_missing");
      setLoading(false);
      return;
    }
    const sess = await fetchPaperSessions();
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
    setLoading(false);
  }, [sessionParam]);

  const loadAnalytics = useCallback(
    async (sid: string) => {
      if (!sid) {
        setAnalytics(null);
        setTrades([]);
        setEquity(null);
        setSymbols([]);
        return;
      }
      const range = validateExitDateRange(exitFrom, exitTo);
      if (!range.ok) {
        setFilterError(range.reason);
        return;
      }
      setFilterError(null);
      setRefreshing(true);
      setError(null);
      const filter = {
        symbol: symbol !== "ALL" ? symbol : undefined,
        exitFromMs: range.fromMs,
        exitToMs: range.toMs,
      };
      const [sum, tr, eq, sym] = await Promise.all([
        fetchPaperAnalytics(sid, filter),
        fetchPaperAnalyticsTrades(sid, {
          ...filter,
          limit: TRADE_PAGE_SIZE,
          offset: tradeOffset,
        }),
        fetchPaperAnalyticsEquity(sid, series),
        fetchPaperAnalyticsSymbols(sid, {
          exitFromMs: range.fromMs,
          exitToMs: range.toMs,
        }),
      ]);
      if (!sum.ok) {
        setAnalytics(null);
        setError(
          sum.status === 404
            ? "session_not_found"
            : sum.status === 503
              ? "paper_read_disabled"
              : sum.detail,
        );
      } else {
        setAnalytics(sum.data);
      }
      if (tr.ok) {
        setTrades(tr.data.items);
        setTradeWarnings(tr.data.warnings || []);
      } else {
        setTrades([]);
        setTradeWarnings([]);
        if (sum.ok) setError(tr.detail);
      }
      if (eq.ok) setEquity(eq.data);
      else setEquity(null);
      if (sym.ok) setSymbols(sym.data.items);
      else setSymbols([]);
      setRefreshing(false);
    },
    [exitFrom, exitTo, symbol, tradeOffset, series],
  );

  useEffect(() => {
    void loadBootstrap();
  }, [loadBootstrap]);

  useEffect(() => {
    if (!status?.paper_read_api_enabled || !sessionId) return;
    void loadAnalytics(sessionId);
  }, [status?.paper_read_api_enabled, sessionId, loadAnalytics]);

  const mode = useMemo(
    () =>
      resolvePaperUiMode({
        loading,
        category: "spot",
        statusOk: Boolean(status) || !error,
        enabled: Boolean(status?.paper_read_api_enabled),
        apiError: Boolean(error && !status),
        sessionCount: sessions.length,
      }),
    [loading, error, status, sessions.length],
  );

  const symbolOptions = useMemo(() => {
    const set = new Set<string>(["ALL"]);
    for (const s of symbols) set.add(s.symbol);
    for (const t of trades) set.add(t.symbol);
    if (symbol !== "ALL") set.add(symbol);
    return Array.from(set);
  }, [symbols, trades, symbol]);

  const chartData = useMemo(() => {
    if (!equity?.points?.length) return [];
    return equity.points.map((p) => ({
      t: formatUtcMs(p.as_of_ms),
      ms: p.as_of_ms,
      value: Number(p.value),
      raw: p.value,
      status: p.valuation_status,
    }));
  }, [equity]);

  const selectedSession = sessions.find((s) => s.session_id === sessionId);
  const currency = analytics?.currency || selectedSession?.currency || "USDT";
  const dd =
    series === "marked"
      ? analytics?.max_drawdown_marked
      : analytics?.max_drawdown_realized_balance;

  const resetFilters = () => {
    setSymbol("ALL");
    setSeries("marked");
    setExitFrom("");
    setExitTo("");
    setTradeOffset(0);
    setFilterError(null);
    syncUrl({
      symbol: "ALL",
      series: "marked",
      exitFrom: "",
      exitTo: "",
      offset: 0,
    });
  };

  if (mode === "loading" && !status) {
    return <LogoLoader fullScreen label="Loading paper analytics…" />;
  }

  return (
    <div>
      <PageHeader
        title="Paper analytics"
        description="Read-only performance from the local paper journal. Fees already netted into realized PnL."
      />

      <div className="mb-4 rounded-2xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm font-medium">
        {PAPER_ONLY}
      </div>

      {mode === "disabled" ? (
        <DataModeBanner
          mode="unavailable"
          notes={[
            "PAPER_READ_API_ENABLED is false. Enable it only for local loopback diagnostics.",
            "This page does not create sessions or place paper orders.",
          ]}
        />
      ) : null}

      {error === "paper_db_missing" || (status && !status.db_present && status.paper_read_api_enabled) ? (
        <DataModeBanner
          mode="unavailable"
          notes={[
            "No local paper journal database is present.",
            "GET requests do not create a database.",
          ]}
        />
      ) : null}

      {mode === "no_sessions" && status?.paper_read_api_enabled ? (
        <DataModeBanner
          mode="unavailable"
          notes={[
            "No paper sessions are available.",
            "Create sessions via the paper broker tooling, then return here.",
          ]}
        />
      ) : null}

      {error && error !== "paper_db_missing" && mode !== "disabled" ? (
        <Card className="mb-4 border-rose-500/40">
          <CardHeader>
            <CardTitle className="text-base">Analytics request failed</CardTitle>
            <CardDescription className="font-mono text-xs">{error}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                void loadBootstrap().then(() => {
                  if (sessionId) void loadAnalytics(sessionId);
                });
              }}
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {status?.paper_read_api_enabled && sessions.length > 0 ? (
        <>
          <Card className="mb-4">
            <CardHeader>
              <CardTitle className="text-base">Session & filters</CardTitle>
              <CardDescription>
                Trade metrics may be filtered by symbol / exit date (UTC). Equity curve stays
                session-wide.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="mb-1 text-xs text-muted-foreground">Session</p>
                <Select
                  value={sessionId || undefined}
                  onValueChange={(v) => {
                    setSessionId(v);
                    setTradeOffset(0);
                    setSymbol("ALL");
                    syncUrl({ session: v, symbol: "ALL", offset: 0 });
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select session" />
                  </SelectTrigger>
                  <SelectContent>
                    {sessions.map((s) => (
                      <SelectItem key={s.session_id} value={s.session_id}>
                        {s.session_id.slice(0, 18)}… ({s.status})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedSession ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Initial {selectedSession.initial_balance} {selectedSession.currency} · updated{" "}
                    {formatUtcMs(selectedSession.updated_ms)}
                  </p>
                ) : null}
              </div>

              <div>
                <p className="mb-1 text-xs text-muted-foreground">Symbol (trades)</p>
                <Select
                  value={symbol}
                  onValueChange={(v) => {
                    setSymbol(v);
                    setTradeOffset(0);
                    syncUrl({ symbol: v, offset: 0 });
                  }}
                >
                  <SelectTrigger>
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

              <div>
                <p className="mb-1 text-xs text-muted-foreground">Equity series</p>
                <Select
                  value={series}
                  onValueChange={(v) => {
                    const next = v === "realized_balance" ? "realized_balance" : "marked";
                    setSeries(next);
                    syncUrl({ series: next });
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="marked">Marked equity</SelectItem>
                    <SelectItem value="realized_balance">
                      Realized balance (available + reserved)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <p className="mb-1 text-xs text-muted-foreground">Exit from (UTC date)</p>
                <Input
                  type="date"
                  value={exitFrom}
                  onChange={(e) => setExitFrom(e.target.value)}
                />
              </div>
              <div>
                <p className="mb-1 text-xs text-muted-foreground">Exit to (UTC date)</p>
                <Input
                  type="date"
                  value={exitTo}
                  onChange={(e) => setExitTo(e.target.value)}
                />
              </div>
              <div className="flex items-end gap-2">
                <Button
                  type="button"
                  onClick={() => {
                    setTradeOffset(0);
                    syncUrl({
                      exitFrom,
                      exitTo,
                      offset: 0,
                      symbol,
                      series,
                      session: sessionId,
                    });
                    void loadAnalytics(sessionId);
                  }}
                >
                  Apply filters
                </Button>
                <Button type="button" variant="outline" onClick={resetFilters}>
                  Reset
                </Button>
              </div>
              {filterError ? (
                <p className="text-sm text-rose-400 md:col-span-3">{filterError}</p>
              ) : null}
              <div className="md:col-span-3 flex flex-wrap gap-2 text-xs">
                <Badge variant="outline">{refreshing ? "Refreshing…" : "Read-only"}</Badge>
                <Link
                  className="underline text-muted-foreground hover:text-foreground"
                  href={sessionId ? `/paper?session=${encodeURIComponent(sessionId)}` : "/paper"}
                >
                  Open paper journal
                </Link>
                <Link
                  className="underline text-muted-foreground hover:text-foreground"
                  href="/backtesting"
                >
                  Historical backtesting
                </Link>
              </div>
            </CardContent>
          </Card>

          {analytics ? (
            <>
              <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard label="Closed trades" value={String(analytics.closed_trades)} />
                <MetricCard
                  label="W / L / BE"
                  value={`${analytics.winning_trades} / ${analytics.losing_trades} / ${analytics.breakeven_trades}`}
                />
                <MetricCard
                  label="Win rate"
                  value={formatOptionalMetric(analytics.win_rate_pct, { suffix: "%" })}
                  hint="Breakeven trades included in denominator"
                />
                <MetricCard
                  label="Net realized PnL"
                  value={formatDecimalDisplay(analytics.net_realized_pnl, {
                    suffix: currency,
                  })}
                  valueClassName={signedMoneyClass(analytics.net_realized_pnl)}
                  hint="Already net of entry + exit fees"
                />
                <MetricCard
                  label="Gross profit"
                  value={formatDecimalDisplay(analytics.gross_profit, { suffix: currency })}
                />
                <MetricCard
                  label="Gross loss"
                  value={formatDecimalDisplay(analytics.gross_loss, { suffix: currency })}
                />
                <MetricCard
                  label="Profit factor"
                  value={formatOptionalMetric(analytics.profit_factor)}
                />
                <MetricCard
                  label="Expectancy / closed trade"
                  value={formatOptionalMetric(analytics.expectancy, {
                    suffix: currency,
                  })}
                  hint="Historical mean — not a forecast"
                />
                <MetricCard
                  label="Average win"
                  value={formatOptionalMetric(analytics.average_win, { suffix: currency })}
                />
                <MetricCard
                  label="Average loss"
                  value={formatOptionalMetric(analytics.average_loss, { suffix: currency })}
                />
                <MetricCard
                  label="Best / worst"
                  value={`${formatOptionalMetric(analytics.best_trade_pnl)} / ${formatOptionalMetric(analytics.worst_trade_pnl)}`}
                />
                <MetricCard
                  label="Total fees"
                  value={formatDecimalDisplay(analytics.total_fees, { suffix: currency })}
                />
                <MetricCard
                  label="Realized return %"
                  value={formatOptionalMetric(analytics.realized_return_pct, {
                    suffix: "%",
                  })}
                  hint="vs initial session capital; excludes unrealized"
                />
                <MetricCard
                  label="Avg holding"
                  value={formatHoldingDuration(analytics.average_holding_ms.value)}
                />
                <MetricCard
                  label="Open positions"
                  value={String(analytics.open_positions)}
                  hint="Excluded from closed-trade metrics"
                />
                <MetricCard
                  label="Initial balance"
                  value={formatDecimalDisplay(analytics.initial_balance, {
                    suffix: currency,
                  })}
                />
              </div>

              {(analytics.data_quality_warnings?.length || tradeWarnings.length) > 0 ? (
                <Card className="mb-4 border-amber-500/30">
                  <CardHeader>
                    <CardTitle className="text-base">Data-quality notices</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="list-disc pl-5 text-sm text-muted-foreground">
                      {[...(analytics.data_quality_warnings || []), ...tradeWarnings].map(
                        (w) => (
                          <li key={w}>{w}</li>
                        ),
                      )}
                    </ul>
                  </CardContent>
                </Card>
              ) : null}

              <Card className="mb-4">
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    Equity observations
                    <Badge variant="outline">
                      {series === "marked" ? "marked_equity" : "realized_balance"}
                    </Badge>
                    <Badge variant="outline">session-wide</Badge>
                  </CardTitle>
                  <CardDescription>
                    Snapshot series from the paper journal. Not interpolated. Symbol/date filters
                    above do not reshape this curve. Observed drawdown may understate intraperiod
                    extremes when snapshots are sparse.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {chartData.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No equity observations for this series
                      {equity?.warnings?.length
                        ? ` — ${equity.warnings.join("; ")}`
                        : "."}
                    </p>
                  ) : (
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid stroke="hsl(217 25% 20%)" strokeDasharray="3 3" />
                          <XAxis dataKey="t" stroke="hsl(215 16% 65%)" fontSize={11} />
                          <YAxis
                            stroke="hsl(215 16% 65%)"
                            fontSize={12}
                            domain={["auto", "auto"]}
                          />
                          <Tooltip
                            contentStyle={{
                              background: "hsl(222 40% 10%)",
                              border: "1px solid hsl(217 25% 22%)",
                            }}
                            formatter={(value: number, _n, item) => [
                              `${item?.payload?.raw ?? value} ${currency}`,
                              series === "marked" ? "Marked equity" : "Realized balance",
                            ]}
                          />
                          <Line
                            type="linear"
                            dataKey="value"
                            stroke="hsl(160 84% 45%)"
                            strokeWidth={2}
                            dot={false}
                            connectNulls={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                  {dd ? (
                    <div className="mt-3 grid gap-2 text-sm md:grid-cols-2">
                      <p>
                        <span className="text-muted-foreground">{dd.label}: </span>
                        {formatOptionalMetric(dd.max_drawdown_pct, { suffix: "%" })} ·{" "}
                        {formatOptionalMetric(dd.max_drawdown_amount, {
                          suffix: currency,
                        })}
                      </p>
                      <p className="text-muted-foreground">
                        Obs {dd.observation_count}
                        {dd.sparse_warning ? " · sparse history warning" : ""} · peak{" "}
                        {formatUtcMs(dd.peak_ms)} → trough {formatUtcMs(dd.trough_ms)}
                      </p>
                      {dd.notes?.length ? (
                        <ul className="md:col-span-2 list-disc pl-5 text-xs text-muted-foreground">
                          {dd.notes.map((n) => (
                            <li key={n}>{n}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                  {equity?.warnings?.length ? (
                    <ul className="mt-2 list-disc pl-5 text-xs text-muted-foreground">
                      {equity.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  ) : null}
                </CardContent>
              </Card>

              <Card className="mb-4">
                <CardHeader>
                  <CardTitle className="text-base">Symbol breakdown</CardTitle>
                  <CardDescription>
                    Closed-trade aggregates only. Click a row to filter the trades table.
                  </CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  {symbols.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No symbol closed-trade data.</p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Symbol</TableHead>
                          <TableHead>Closed</TableHead>
                          <TableHead>W/L/BE</TableHead>
                          <TableHead>Win rate</TableHead>
                          <TableHead>Net PnL</TableHead>
                          <TableHead>Fees</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {symbols.map((s) => (
                          <TableRow
                            key={s.symbol}
                            className="cursor-pointer"
                            onClick={() => {
                              setSymbol(s.symbol);
                              setTradeOffset(0);
                              syncUrl({ symbol: s.symbol, offset: 0 });
                            }}
                          >
                            <TableCell className="font-medium">{s.symbol}</TableCell>
                            <TableCell>{s.closed_trades}</TableCell>
                            <TableCell>
                              {s.winners}/{s.losers}/{s.breakeven}
                            </TableCell>
                            <TableCell>
                              {formatOptionalMetric(s.win_rate_pct, { suffix: "%" })}
                            </TableCell>
                            <TableCell className={signedMoneyClass(s.net_realized_pnl)}>
                              {formatDecimalDisplay(s.net_realized_pnl)}
                            </TableCell>
                            <TableCell className="font-mono">
                              {formatDecimalDisplay(s.fees)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>

              <Card className="mb-8">
                <CardHeader>
                  <CardTitle className="text-base">Closed trades</CardTitle>
                  <CardDescription>
                    Paginated from the analytics API. Open positions are excluded.
                  </CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  {analytics.closed_trades === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No closed trades for this session/filter. Metrics stay unavailable — not a
                      fabricated 0% win rate.
                    </p>
                  ) : trades.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No trades on this page. Try previous page or clear filters.
                    </p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Symbol</TableHead>
                          <TableHead>Category</TableHead>
                          <TableHead>Entry (UTC)</TableHead>
                          <TableHead>Exit (UTC)</TableHead>
                          <TableHead>Qty</TableHead>
                          <TableHead>Entry</TableHead>
                          <TableHead>Exit</TableHead>
                          <TableHead>Gross</TableHead>
                          <TableHead>Fees</TableHead>
                          <TableHead>Net</TableHead>
                          <TableHead>Outcome</TableHead>
                          <TableHead>Reason</TableHead>
                          <TableHead>Hold</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {trades.map((t) => {
                          const outcome = tradeOutcome(t.net_realized_pnl);
                          return (
                            <TableRow key={closedTradeRowKey(t)}>
                              <TableCell>{t.symbol}</TableCell>
                              <TableCell>{t.category}</TableCell>
                              <TableCell className="whitespace-nowrap text-xs">
                                {formatUtcMs(t.opened_ms)}
                              </TableCell>
                              <TableCell className="whitespace-nowrap text-xs">
                                {formatUtcMs(t.closed_ms)}
                              </TableCell>
                              <TableCell className="font-mono">{t.quantity}</TableCell>
                              <TableCell className="font-mono">{t.entry_price}</TableCell>
                              <TableCell className="font-mono">{t.exit_price}</TableCell>
                              <TableCell className={signedMoneyClass(t.gross_realized_pnl)}>
                                {t.gross_realized_pnl}
                              </TableCell>
                              <TableCell className="font-mono text-xs">
                                {t.entry_fee} + {t.exit_fee}
                              </TableCell>
                              <TableCell className={signedMoneyClass(t.net_realized_pnl)}>
                                {t.net_realized_pnl}
                              </TableCell>
                              <TableCell>{outcome}</TableCell>
                              <TableCell>{t.exit_reason || "—"}</TableCell>
                              <TableCell>
                                {formatHoldingDuration(t.holding_duration_ms)}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  )}
                  <div className="mt-3 flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={tradeOffset <= 0}
                      onClick={() => {
                        const next = Math.max(0, tradeOffset - TRADE_PAGE_SIZE);
                        setTradeOffset(next);
                        syncUrl({ offset: next });
                      }}
                    >
                      Previous
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={trades.length < TRADE_PAGE_SIZE}
                      onClick={() => {
                        const next = tradeOffset + TRADE_PAGE_SIZE;
                        setTradeOffset(next);
                        syncUrl({ offset: next });
                      }}
                    >
                      Next
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      offset {tradeOffset} · page size {TRADE_PAGE_SIZE}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </>
          ) : null}

          {status.paper_read_api_enabled && sessionId && !analytics && !error && !refreshing ? (
            <p className="text-sm text-muted-foreground">Loading session analytics…</p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
