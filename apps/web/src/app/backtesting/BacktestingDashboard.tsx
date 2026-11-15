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
import { Filter, RotateCcw, ShieldAlert } from "lucide-react";

import { LogoLoader } from "@/components/brand/LogoLoader";
import { ResearchTemplate } from "@/components/design-system/templates";
import { MetricCard } from "@/components/design-system/MetricCard";
import { cn } from "@/lib/utils";
import { chartAxisProps, chartGridProps, chartLineProps, chartTooltipProps } from "@/lib/charts/recharts-theme";
import { CodeComparison } from "@/components/magicui/code-comparison";
import { Marquee } from "@/components/magicui/marquee";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RunBacktestPanel } from "@/app/backtesting/RunBacktestPanel";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  fetchBacktestDecisions,
  fetchBacktestEquity,
  fetchBacktestMetrics,
  fetchBacktestOrders,
  fetchBacktestRun,
  fetchBacktestRuns,
  fetchBacktestStatus,
  fetchBacktestTrades,
  resolveBacktestUiMode,
} from "@/lib/backtest/api";
import {
  ADVISORY_UNCHANGED_LABEL,
  HISTORICAL_SIM_LABEL,
  SIM_LABEL,
  asOptionalMetric,
  formatDecimalDisplay,
  formatHoldingDuration,
  formatOptionalMetric,
  formatUtcMs,
  shadowComparisonAllowed,
  signedMoneyClass,
} from "@/lib/backtest/format";
import {
  formatRunSnapshot,
  humanRunLabel,
  runDateRange,
  shortRunId,
} from "@/lib/backtest/run-label";
import type {
  BacktestDecisionsResponse,
  BacktestEquityResponse,
  BacktestMetrics,
  BacktestOrdersResponse,
  BacktestRunDetail,
  BacktestRunSummary,
  BacktestStatus,
  BacktestTradesResponse,
} from "@/lib/backtest/types";

const PAGE = 25;

type StatusFilter = "all" | "completed" | "failed" | "rejected_data";
type KindFilter = "all" | "synthetic" | "historical" | "other";

function Stat({
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
    <MetricCard
      label={label}
      value={<span className={cn("font-mono text-base md:text-lg", valueClassName ?? "text-foreground")}>{value}</span>}
      hint={hint}
    />
  );
}

function SectionTitle({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-medium text-foreground">{title}</h2>
      {description ? (
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

function matchKind(run: BacktestRunSummary, kind: KindFilter): boolean {
  const label = (run.dataset_label || "").toUpperCase();
  if (kind === "all") return true;
  if (kind === "synthetic") return label.includes("SYNTHETIC");
  if (kind === "historical") return label.includes("HISTORICAL");
  return !label.includes("SYNTHETIC") && !label.includes("HISTORICAL");
}

export function BacktestingDashboard() {
  const search = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const runParam = search.get("run") || "";

  const [runId, setRunId] = useState(runParam);
  const [compareId, setCompareId] = useState("");
  const [tradeOffset, setTradeOffset] = useState(0);
  const [decisionOffset, setDecisionOffset] = useState(0);
  const [orderOffset, setOrderOffset] = useState(0);
  const [series, setSeries] = useState<"marked" | "realized">("marked");
  const [showFilters, setShowFilters] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [kindFilter, setKindFilter] = useState<KindFilter>("all");
  const [symbolFilter, setSymbolFilter] = useState("ALL");

  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<BacktestStatus | null>(null);
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [detail, setDetail] = useState<BacktestRunDetail | null>(null);
  const [metrics, setMetrics] = useState<BacktestMetrics | null>(null);
  const [trades, setTrades] = useState<BacktestTradesResponse | null>(null);
  const [equity, setEquity] = useState<BacktestEquityResponse | null>(null);
  const [decisions, setDecisions] = useState<BacktestDecisionsResponse | null>(null);
  const [orders, setOrders] = useState<BacktestOrdersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | undefined>(undefined);

  const syncUrl = useCallback(
    (nextRun: string) => {
      const params = new URLSearchParams();
      if (nextRun) params.set("run", nextRun);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router],
  );

  const loadCatalog = useCallback(async () => {
    setLoading(true);
    setError(null);
    const st = await fetchBacktestStatus();
    if (!st.ok) {
      setStatus(null);
      setErrorStatus(st.status);
      setError(st.message || st.detail);
      setLoading(false);
      return;
    }
    setStatus(st.data);
    setErrorStatus(undefined);
    if (!st.data.enabled) {
      setRuns([]);
      setLoading(false);
      return;
    }
    const list = await fetchBacktestRuns(50, 0);
    if (!list.ok) {
      setErrorStatus(list.status);
      setError(list.message || list.detail);
      setRuns([]);
      setLoading(false);
      return;
    }
    setRuns(list.data.items);
    const preferred =
      runParam && list.data.items.some((r) => r.run_id === runParam)
        ? runParam
        : list.data.items[0]?.run_id || "";
    if (preferred && preferred !== runId) {
      setRunId(preferred);
      syncUrl(preferred);
    } else if (!preferred) {
      setRunId("");
    }
    if (!compareId && list.data.items.length > 1) {
      const other = list.data.items.find((r) => r.run_id !== preferred);
      if (other) setCompareId(other.run_id);
    }
    setLoading(false);
  }, [runParam, runId, syncUrl, compareId]);

  const loadRun = useCallback(
    async (id: string) => {
      if (!id) {
        setDetail(null);
        setMetrics(null);
        setTrades(null);
        setEquity(null);
        setDecisions(null);
        setOrders(null);
        return;
      }
      setError(null);
      const [d, m, t, e, dec, o] = await Promise.all([
        fetchBacktestRun(id),
        fetchBacktestMetrics(id),
        fetchBacktestTrades(id, PAGE, tradeOffset),
        fetchBacktestEquity(id),
        fetchBacktestDecisions(id, PAGE, decisionOffset),
        fetchBacktestOrders(id, PAGE, orderOffset),
      ]);
      if (!d.ok) {
        setErrorStatus(d.status);
        setError(d.message || d.detail);
        setDetail(null);
        return;
      }
      setDetail(d.data);
      setMetrics(m.ok ? m.data : null);
      setTrades(t.ok ? t.data : null);
      setEquity(e.ok ? e.data : null);
      setDecisions(dec.ok ? dec.data : null);
      setOrders(o.ok ? o.data : null);
      if (!m.ok || !t.ok || !e.ok || !dec.ok || !o.ok) {
        setError("Some sections could not load — others below are still valid.");
      }
    },
    [tradeOffset, decisionOffset, orderOffset],
  );

  useEffect(() => {
    void loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status?.enabled && runId) void loadRun(runId);
  }, [status?.enabled, runId, loadRun]);

  const mode = resolveBacktestUiMode(status, errorStatus);
  const analytics = (metrics?.analytics || null) as Record<string, unknown> | null;

  const symbols = useMemo(() => {
    const set = new Set<string>();
    for (const r of runs) {
      if (r.symbol) set.add(r.symbol);
    }
    return Array.from(set).sort();
  }, [runs]);

  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      if (statusFilter !== "all" && r.status !== statusFilter) return false;
      if (symbolFilter !== "ALL" && r.symbol !== symbolFilter) return false;
      if (!matchKind(r, kindFilter)) return false;
      return true;
    });
  }, [runs, statusFilter, symbolFilter, kindFilter]);

  const selectedSummary = useMemo(
    () => runs.find((r) => r.run_id === runId) || null,
    [runs, runId],
  );
  const compareSummary = useMemo(
    () => runs.find((r) => r.run_id === compareId) || null,
    [runs, compareId],
  );

  const chartPoints = useMemo(() => {
    if (!equity) return [];
    const src = series === "marked" ? equity.marked_equity : equity.realized_balance;
    return src.map((p) => ({
      t: formatUtcMs(p.as_of_ms),
      v: Number(p.value),
    }));
  }, [equity, series]);

  const cfg = detail?.effective_config || {};
  const ds = detail?.dataset || {};

  const resetFilters = () => {
    setStatusFilter("all");
    setKindFilter("all");
    setSymbolFilter("ALL");
  };

  const selectRun = (id: string) => {
    setRunId(id);
    setTradeOffset(0);
    setDecisionOffset(0);
    setOrderOffset(0);
    syncUrl(id);
  };

  if (loading) {
    return <LogoLoader fullScreen label="Loading backtesting…" />;
  }

  return (
    <ResearchTemplate
      title="Backtesting Lab"
      description="Configure and run historical multi-agent simulations, then inspect saved reports. A run starts only from an explicit action."
      modes={["readonly"]}
      actions={
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href="/analytics" className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
            Paper analytics
          </Link>
          <Link href="/agents/live" className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
            Agent Studio
          </Link>
        </div>
      }
    >

      <Marquee pauseOnHover className="min-w-0 overflow-hidden rounded-xl border border-border bg-muted/30 [--duration:28s]">
        {[
          SIM_LABEL,
          status?.enabled ? `${status.run_count} saved run(s)` : "API disabled",
          selectedSummary ? humanRunLabel(selectedSummary) : "No run selected",
          "BUY signals ≠ filled orders ≠ closed trades",
          "Open positions are not force-closed",
        ].map((item) => (
          <span
            key={item}
            className="mx-3 rounded-full border border-border bg-muted/80 px-3 py-1 text-xs text-foreground"
          >
            {item}
          </span>
        ))}
      </Marquee>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{HISTORICAL_SIM_LABEL}</CardTitle>
          <CardDescription>
            {ADVISORY_UNCHANGED_LABEL}. News and LLM rows are shadow labels on the technical
            simulation. They do not change orders, risk, or size.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>Technical baseline, news advisory shadow, and LLM shadow use the same 68A engine.</p>
          {shadowComparisonAllowed(
            String((detail?.extras?.shadow_69e as { provenance_status?: string } | undefined)?.provenance_status || ""),
          ) ? (
            <p>This saved run has a complete revision archive for its own fixture window.</p>
          ) : (
            <p>
              Historical news revision coverage is insufficient. Comparisons that need a past news
              snapshot are not valid, and missing events are not filled in.
            </p>
          )}
        </CardContent>
      </Card>

      {mode === "disabled" ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Backtest API is off</CardTitle>
            <CardDescription>
              Enable <code className="text-xs">BACKTEST_READ_API_ENABLED=true</code> on the local
              FastAPI loopback to inspect saved reports. Nothing here will generate a run.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : null}

      {(mode === "unreachable" || (error && !detail && mode === "ready")) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Could not load backtests</CardTitle>
            <CardDescription>{error || "API unreachable"}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button type="button" onClick={() => void loadCatalog()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {(mode === "missing_dir" || mode === "empty") && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">No saved runs yet</CardTitle>
            <CardDescription>
              Create one offline first:
              <code className="ml-1 rounded bg-muted px-1.5 py-0.5 text-xs">
                python scripts/demo_multi_agent_backtest_68a.py
              </code>
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <RunBacktestPanel
        onRunCompleted={(id) => {
          void (async () => {
            await loadCatalog();
            selectRun(id);
          })();
        }}
      />

      {status?.enabled && runs.length > 0 ? (
        <section className="w-full min-w-0 max-w-full rounded-2xl border border-border bg-muted/30 p-4 md:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-medium text-foreground">Choose a saved run</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Pick a saved simulation. Filters narrow the list — they do not re-run anything.
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button
                type="button"
                variant={showFilters ? "default" : "outline"}
                size="sm"
                onClick={() => setShowFilters((v) => !v)}
              >
                <Filter className="mr-1.5 h-3.5 w-3.5" />
                Filters
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={resetFilters}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Reset
              </Button>
            </div>
          </div>

          {showFilters ? (
            <div className="mt-4 grid grid-cols-1 gap-3 rounded-xl border border-border bg-muted/70 p-3 sm:grid-cols-2 xl:grid-cols-3">
              <div className="min-w-0">
                <p className="mb-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  Status
                </p>
                <Select
                  value={statusFilter}
                  onValueChange={(v) => setStatusFilter(v as StatusFilter)}
                >
                  <SelectTrigger className="w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="failed">Failed</SelectItem>
                    <SelectItem value="rejected_data">Rejected data</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="min-w-0">
                <p className="mb-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  Dataset kind
                </p>
                <Select value={kindFilter} onValueChange={(v) => setKindFilter(v as KindFilter)}>
                  <SelectTrigger className="w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All kinds</SelectItem>
                    <SelectItem value="synthetic">Synthetic test data</SelectItem>
                    <SelectItem value="historical">Historical exchange data</SelectItem>
                    <SelectItem value="other">Other / offline</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="min-w-0">
                <p className="mb-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  Symbol
                </p>
                <Select value={symbolFilter} onValueChange={setSymbolFilter}>
                  <SelectTrigger className="w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ALL">All symbols</SelectItem>
                    {symbols.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : null}

          <div className="mt-4 grid min-w-0 grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,12rem)] lg:items-center">
            <Select
              value={filteredRuns.some((r) => r.run_id === runId) ? runId : undefined}
              onValueChange={selectRun}
            >
              <SelectTrigger className="h-11 w-full min-w-0 [&>span]:truncate">
                <SelectValue placeholder="Select a saved run" />
              </SelectTrigger>
              <SelectContent>
                {filteredRuns.length === 0 ? (
                  <SelectItem value="__none" disabled>
                    No runs match filters
                  </SelectItem>
                ) : (
                  filteredRuns.map((r) => (
                    <SelectItem key={r.run_id} value={r.run_id}>
                      {humanRunLabel(r)}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            {selectedSummary ? (
              <div className="min-w-0 break-words text-xs text-muted-foreground lg:text-right">
                <div className="truncate">{shortRunId(selectedSummary.run_id)}</div>
                <div className="break-words">{runDateRange(selectedSummary)}</div>
              </div>
            ) : null}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Showing {filteredRuns.length} of {runs.length} saved run(s)
          </p>
        </section>
      ) : null}

      {detail ? (
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="w-full justify-start overflow-x-auto">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="setup">Setup</TabsTrigger>
            <TabsTrigger value="performance">Performance</TabsTrigger>
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="orders">Orders</TabsTrigger>
            <TabsTrigger value="decisions">Decisions</TabsTrigger>
            <TabsTrigger value="compare">Compare</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <SectionTitle
              title="2. What happened?"
              description="Plain-language snapshot of this simulation. Details live in the other tabs."
            />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Net realized PnL"
                value={formatDecimalDisplay(
                  analytics?.net_realized_pnl != null
                    ? String(analytics.net_realized_pnl)
                    : null,
                  { suffix: "USDT" },
                )}
                valueClassName={signedMoneyClass(
                  analytics?.net_realized_pnl != null
                    ? String(analytics.net_realized_pnl)
                    : null,
                )}
                hint="Closed trades only — excludes open positions"
              />
              <Stat
                label="Closed / still open"
                value={`${analytics?.closed_trades ?? "—"} / ${detail.open_positions ?? "—"}`}
              />
              <Stat
                label="Filled / rejected orders"
                value={`${metrics?.counters?.filled_orders ?? "—"} / ${metrics?.counters?.rejected_orders ?? "—"}`}
                hint="Rejected ≠ losing trade"
              />
              <Stat
                label="Win rate"
                value={formatOptionalMetric(asOptionalMetric(analytics?.win_rate_pct), {
                  suffix: "%",
                })}
              />
            </div>
            <div className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-sm text-amber-50/90">
              <div className="mb-1 flex items-center gap-2 font-medium">
                <ShieldAlert className="h-4 w-4" />
                How to read the counts
              </div>
              <p className="text-amber-50/70">
                A BUY signal is only a decision. Many BUYs can be rejected (cash, pending order,
                exposure). Filled orders can still be open at the end. Closed trades are exits
                only.
              </p>
            </div>
          </TabsContent>

          <TabsContent value="setup" className="space-y-5">
            <SectionTitle
              title="Market & money"
              description="What market was simulated and with which cash rules."
            />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Stat label="Symbol" value={String(ds.symbol ?? cfg.symbol ?? "—")} />
              <Stat label="Market type" value={String(ds.market_type ?? cfg.market_type ?? "—")} />
              <Stat label="Candle interval" value={`${String(ds.interval ?? cfg.interval ?? "—")}m`} />
              <Stat
                label="Initial capital"
                value={`${String(cfg.initial_capital ?? "—")} USDT`}
              />
              <Stat label="Fee rate" value={String(cfg.fee_rate ?? "—")} />
              <Stat label="Slippage" value={`${String(cfg.slippage_bps ?? "—")} bps`} />
            </div>

            <SectionTitle
              title="Engine & risk"
              description="Which CryptoNova pipeline and risk mode produced the decisions."
            />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Stat label="Engine" value={String(cfg.engine_version ?? "—")} />
              <Stat label="Pipeline" value={String(cfg.agent_pipeline_version ?? "—")} />
              <Stat label="Risk mode" value={String(cfg.risk_mode ?? "—")} />
              <Stat label="Warm-up bars" value={String(detail.warm_up_candles ?? "—")} />
              <Stat label="Eligible evaluations" value={String(detail.eligible_candles ?? "—")} />
              <Stat label="Candles in dataset" value={String(ds.candle_count ?? "—")} />
            </div>

            <SectionTitle
              title="Dataset provenance"
              description="Where the candles came from — synthetic is not live exchange validation."
            />
            <div className="space-y-2 rounded-xl border border-border bg-muted/50 p-4 text-sm">
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">{detail.dataset_label}</Badge>
                <Badge variant="outline">{String(cfg.data_source ?? ds.source_kind ?? "—")}</Badge>
              </div>
              <p className="text-muted-foreground">
                Range: {formatUtcMs(Number(ds.first_start_ms))} →{" "}
                {formatUtcMs(Number(ds.last_start_ms))}
              </p>
              <p className="break-all text-xs text-muted-foreground">
                Provenance: {String(ds.provenance ?? "—")}
              </p>
              <p className="break-all text-xs text-muted-foreground">
                Dataset hash: {String(ds.content_hash ?? cfg.dataset_hash ?? "—")}
              </p>
              <p className="break-all text-xs text-muted-foreground">
                Result hash: {detail.result_hash || "—"}
              </p>
              {String(ds.market_type || cfg.market_type) === "linear" ? (
                <p className="text-xs text-amber-300">
                  Linear candles still use spot-like long-only execution — not a Futures backtest.
                </p>
              ) : null}
            </div>
          </TabsContent>

          <TabsContent value="performance" className="space-y-4">
            <SectionTitle
              title="Performance metrics"
              description="67A paper-analytics definitions. Empty win rate means no closed trades — not 0%."
            />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Stat
                label="Realized return"
                value={formatOptionalMetric(asOptionalMetric(analytics?.realized_return_pct), {
                  suffix: "%",
                })}
              />
              <Stat
                label="Profit factor"
                value={formatOptionalMetric(asOptionalMetric(analytics?.profit_factor))}
              />
              <Stat
                label="Expectancy / closed trade"
                value={formatOptionalMetric(asOptionalMetric(analytics?.expectancy), {
                  suffix: "USDT",
                })}
                hint="Historical mean — not a forecast"
              />
              <Stat
                label="Total fees"
                value={formatDecimalDisplay(
                  analytics?.total_fees != null ? String(analytics.total_fees) : null,
                  { suffix: "USDT" },
                )}
              />
              <Stat
                label="Final marked equity"
                value={formatDecimalDisplay(detail.final_marked_equity, { suffix: "USDT" })}
              />
              <Stat
                label="Available / reserved"
                value={`${formatDecimalDisplay(detail.final_available_balance)} / ${formatDecimalDisplay(detail.final_reserved_capital)}`}
              />
            </div>

            <SectionTitle
              title="Equity curve"
              description="Snapshot observations only — sparse points can understate true intraperiod drawdown."
            />
            <div className="rounded-xl border border-border bg-muted/50 p-4">
              <Select
                value={series}
                onValueChange={(v) => setSeries(v === "realized" ? "realized" : "marked")}
              >
                <SelectTrigger className="mb-3 w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="marked">Marked equity</SelectItem>
                  <SelectItem value="realized">Realized balance (cash)</SelectItem>
                </SelectContent>
              </Select>
              {!equity || chartPoints.length === 0 ? (
                <p className="text-sm text-muted-foreground">No equity observations for this run.</p>
              ) : (
                <div className="h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartPoints}>
                      <CartesianGrid {...chartGridProps} />
                      <XAxis dataKey="t" hide />
                      <YAxis {...chartAxisProps} domain={["auto", "auto"]} width={72} />
                      <Tooltip {...chartTooltipProps} />
                      <Line
                        type="monotone"
                        dataKey="v"
                        name={series === "marked" ? "Marked equity" : "Realized balance"}
                        {...chartLineProps}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </TabsContent>

          <TabsContent value="trades" className="space-y-3">
            <SectionTitle
              title="Closed trades"
              description="Completed exits only. Open positions are listed separately."
            />
            {!trades || trades.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No closed trades in this run.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Entry</TableHead>
                      <TableHead>Exit</TableHead>
                      <TableHead>Net PnL</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>Hold</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {trades.items.map((t, i) => (
                      <TableRow key={`${String(t.opened_ms)}-${i}`}>
                        <TableCell>{String(t.symbol ?? "—")}</TableCell>
                        <TableCell>{formatUtcMs(Number(t.opened_ms))}</TableCell>
                        <TableCell>{formatUtcMs(Number(t.closed_ms))}</TableCell>
                        <TableCell
                          className={signedMoneyClass(
                            t.net_realized_pnl != null ? String(t.net_realized_pnl) : null,
                          )}
                        >
                          {formatDecimalDisplay(
                            t.net_realized_pnl != null ? String(t.net_realized_pnl) : null,
                            { suffix: "USDT" },
                          )}
                        </TableCell>
                        <TableCell>{String(t.exit_reason ?? "—")}</TableCell>
                        <TableCell>
                          {formatHoldingDuration(
                            t.holding_duration_ms != null
                              ? String(t.holding_duration_ms)
                              : null,
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {trades && trades.total > PAGE ? (
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={tradeOffset <= 0}
                  onClick={() => setTradeOffset((o) => Math.max(0, o - PAGE))}
                >
                  Prev
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={tradeOffset + PAGE >= trades.total}
                  onClick={() => setTradeOffset((o) => o + PAGE)}
                >
                  Next
                </Button>
              </div>
            ) : null}
            {trades && trades.open_positions.length > 0 ? (
              <div className="rounded-xl border border-border bg-muted/50 p-3 text-sm">
                <p className="mb-2 font-medium text-foreground">Still open at dataset end</p>
                {trades.open_positions.map((p, i) => (
                  <p key={i} className="text-xs text-muted-foreground">
                    {String(p.symbol)} · qty {String(p.quantity)} · entry {String(p.entry_price)}
                  </p>
                ))}
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="orders" className="space-y-3">
            <SectionTitle
              title="Orders & rejections"
              description="Each submit attempt from a decision. Rejection reasons explain blocked entries."
            />
            {orders?.rejection_breakdown &&
            Object.keys(orders.rejection_breakdown).length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {Object.entries(orders.rejection_breakdown).map(([k, v]) => (
                  <Badge key={k} variant="outline">
                    {k}: {v}
                  </Badge>
                ))}
              </div>
            ) : null}
            {!orders || orders.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No order submits recorded.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>When</TableHead>
                      <TableHead>Decision</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>Fills</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {orders.items.map((o, i) => (
                      <TableRow key={`${String(o.order_id)}-${i}`}>
                        <TableCell>{formatUtcMs(Number(o.candle_start_ms))}</TableCell>
                        <TableCell>{String(o.decision_action ?? "—")}</TableCell>
                        <TableCell>{String(o.final_status ?? "—")}</TableCell>
                        <TableCell>{String(o.reason ?? "—")}</TableCell>
                        <TableCell>{Array.isArray(o.fills) ? o.fills.length : 0}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {orders && orders.total > PAGE ? (
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={orderOffset <= 0}
                  onClick={() => setOrderOffset((o) => Math.max(0, o - PAGE))}
                >
                  Prev
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={orderOffset + PAGE >= orders.total}
                  onClick={() => setOrderOffset((o) => o + PAGE)}
                >
                  Next
                </Button>
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="decisions" className="space-y-3">
            <SectionTitle
              title="Agent decisions"
              description={detail.decision_trace_note}
            />
            {!decisions || decisions.items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No decision traces for this run.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Candle</TableHead>
                      <TableHead>Final</TableHead>
                      <TableHead>Risk</TableHead>
                      <TableHead>Biases (Market / Trend / Momentum)</TableHead>
                      <TableHead>Submit result</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {decisions.items.map((d, i) => {
                      const biases = (d.agent_bias_summary || {}) as Record<string, unknown>;
                      const submits = Array.isArray(d.submits) ? d.submits : [];
                      return (
                        <TableRow key={`${String(d.decision_id)}-${i}`}>
                          <TableCell>{formatUtcMs(Number(d.candle_start_ms))}</TableCell>
                          <TableCell>{String(d.action)}</TableCell>
                          <TableCell>{String(d.risk_verdict)}</TableCell>
                          <TableCell className="text-xs">
                            {String(biases.market ?? "—")} / {String(biases.trend ?? "—")} /{" "}
                            {String(biases.momentum ?? "—")}
                          </TableCell>
                          <TableCell className="text-xs">
                            {submits.length
                              ? submits
                                  .map((s) =>
                                    typeof s === "object" && s
                                      ? String((s as { reason?: string }).reason || "?")
                                      : "?",
                                  )
                                  .join(", ")
                              : "—"}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
            {decisions && decisions.total > PAGE ? (
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={decisionOffset <= 0}
                  onClick={() => setDecisionOffset((o) => Math.max(0, o - PAGE))}
                >
                  Prev
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={decisionOffset + PAGE >= decisions.total}
                  onClick={() => setDecisionOffset((o) => o + PAGE)}
                >
                  Next
                </Button>
              </div>
            ) : null}
          </TabsContent>

          <TabsContent value="compare" className="space-y-4">
            <SectionTitle
              title="Compare two saved runs"
              description="Side-by-side snapshots of configuration and headline results. Read-only."
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  Left (current)
                </p>
                <Select value={runId || undefined} onValueChange={selectRun}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select run A" />
                  </SelectTrigger>
                  <SelectContent>
                    {runs.map((r) => (
                      <SelectItem key={r.run_id} value={r.run_id}>
                        {humanRunLabel(r)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <p className="mb-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                  Right (compare)
                </p>
                <Select value={compareId || undefined} onValueChange={setCompareId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select run B" />
                  </SelectTrigger>
                  <SelectContent>
                    {runs.map((r) => (
                      <SelectItem key={r.run_id} value={r.run_id}>
                        {humanRunLabel(r)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {selectedSummary && compareSummary ? (
              <CodeComparison
                filename="run-summary.txt"
                beforeLabel={shortRunId(selectedSummary.run_id)}
                afterLabel={shortRunId(compareSummary.run_id)}
                beforeCode={formatRunSnapshot(selectedSummary)}
                afterCode={formatRunSnapshot(compareSummary)}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                Select two different runs to compare.
              </p>
            )}
          </TabsContent>

          <TabsContent value="notes" className="space-y-4">
            <SectionTitle
              title="Assumptions & warnings"
              description="What this simulation includes — and what it does not claim."
            />
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
              {detail.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
            {(equity?.data_quality_warnings?.length ||
              detail.data_quality_warnings.length) > 0 ? (
              <div className="rounded-xl border border-border bg-muted/50 p-4">
                <p className="mb-2 text-sm font-medium text-foreground">Data-quality notices</p>
                <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                  {[
                    ...(equity?.data_quality_warnings || []),
                    ...detail.data_quality_warnings,
                  ]
                    .filter((v, i, a) => a.indexOf(v) === i)
                    .map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                </ul>
              </div>
            ) : null}
          </TabsContent>
        </Tabs>
      ) : null}
    </ResearchTemplate>
  );
}
