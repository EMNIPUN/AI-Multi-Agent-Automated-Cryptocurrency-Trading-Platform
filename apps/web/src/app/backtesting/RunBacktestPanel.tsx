"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Play, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  estimateCandleCount,
  fetchBacktestJobStatus,
  fetchBacktestRunCapabilities,
  submitBacktestRun,
} from "@/lib/backtest/api";
import { SIM_LABEL } from "@/lib/backtest/format";
import type { BacktestJobStatus, BacktestRunCapabilities } from "@/lib/backtest/types";

type MarketChoice = "spot" | "linear" | "both";

function utcDateInputValue(ms: number): string {
  const d = new Date(ms);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function utcDayStartMs(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number);
  return Date.UTC(y, m - 1, d, 0, 0, 0, 0);
}

function utcDayEndMs(dateStr: string): number {
  const [y, m, d] = dateStr.split("-").map(Number);
  return Date.UTC(y, m - 1, d, 23, 59, 59, 999);
}

function newIdemKey(suffix: string) {
  const base =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `idem_${Date.now()}`;
  return `${base}_${suffix}`;
}

const DEFAULT_CAPS: BacktestRunCapabilities = {
  run_api_enabled: false,
  read_api_enabled: false,
  symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  market_types: ["spot", "linear"],
  intervals: ["15", "60", "240"],
  risk_modes: ["signal_only", "portfolio"],
  data_sources: ["bybit_public"],
  max_candles_per_run: 5000,
  max_range_ms: 90 * 24 * 60 * 60 * 1000,
  max_simultaneous_runs: 1,
  max_queued_runs: 2,
  max_runtime_seconds: 600,
  performance_label: SIM_LABEL,
  linear_note:
    "Futures/Linear candles still use spot-like long-only simulation — not leveraged Futures PnL.",
  note: "",
};

type Props = {
  onRunCompleted: (runId: string) => void;
};

export function RunBacktestPanel({ onRunCompleted }: Props) {
  const now = Date.now();
  const defaultEnd = utcDateInputValue(now - 24 * 60 * 60 * 1000);
  const defaultStart = utcDateInputValue(now - 8 * 24 * 60 * 60 * 1000);

  const [caps, setCaps] = useState<BacktestRunCapabilities>(DEFAULT_CAPS);
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [marketChoice, setMarketChoice] = useState<MarketChoice>("both");
  const [interval, setCandleInterval] = useState("15");
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);
  const [initialCapital, setInitialCapital] = useState("1000");
  const [feeRate, setFeeRate] = useState("0.001");
  const [slippageBps, setSlippageBps] = useState("5");
  const [riskMode, setRiskMode] = useState<"signal_only" | "portfolio">("signal_only");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [jobs, setJobs] = useState<BacktestJobStatus[]>([]);
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const queueRef = useRef<{ market: "spot" | "linear"; key: string }[]>([]);

  useEffect(() => {
    void (async () => {
      const res = await fetchBacktestRunCapabilities();
      if (res.ok) setCaps(res.data);
    })();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startMs = useMemo(() => utcDayStartMs(startDate), [startDate]);
  const endMs = useMemo(() => utcDayEndMs(endDate), [endDate]);
  const estimated = useMemo(
    () => estimateCandleCount(startMs, endMs, interval),
    [startMs, endMs, interval],
  );

  const marketsToRun = useMemo((): ("spot" | "linear")[] => {
    if (marketChoice === "both") return ["spot", "linear"];
    return [marketChoice];
  }, [marketChoice]);

  const busy =
    submitting ||
    jobs.some((j) => j.status === "QUEUED" || j.status === "RUNNING");

  const runDisabled = !caps.run_api_enabled || busy;

  const validate = (): string | null => {
    if (!startDate || !endDate) return "Start and end dates are required (UTC).";
    if (startMs > endMs) return "Start date must be on or before end date.";
    if (endMs > Date.now()) return "End date cannot be in the future.";
    if (endMs - startMs > caps.max_range_ms) {
      return `Range exceeds max ${(caps.max_range_ms / (24 * 60 * 60 * 1000)).toFixed(0)} days.`;
    }
    if (estimated > caps.max_candles_per_run) {
      return `Estimated ${estimated} candles exceeds max ${caps.max_candles_per_run}.`;
    }
    if (estimated < 220) {
      return `Estimated ${estimated} candles is below warm-up needs (~220+). Widen the range.`;
    }
    const capital = Number(initialCapital);
    if (!Number.isFinite(capital) || capital <= 0) return "Initial capital must be positive.";
    const fee = Number(feeRate);
    if (!Number.isFinite(fee) || fee < 0) return "Fee rate must be a non-negative decimal (e.g. 0.001).";
    if (fee >= 0.05) {
      return "Fee rate looks too high (use 0.001 for 0.1%, not 2).";
    }
    if (riskMode === "portfolio" && marketsToRun.includes("linear") && marketChoice !== "spot") {
      // Portfolio is spot-only; for both we auto-downgrade linear to signal_only.
      if (marketChoice === "linear") {
        return "Portfolio risk mode requires Spot. Switch market to Spot, or use Signal only for Futures.";
      }
    }
    return null;
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const upsertJob = (next: BacktestJobStatus) => {
    setJobs((prev) => {
      const i = prev.findIndex((j) => j.job_id === next.job_id);
      if (i < 0) return [...prev, next];
      const copy = [...prev];
      copy[i] = next;
      return copy;
    });
  };

  const startNextInQueue = async () => {
    const next = queueRef.current.shift();
    if (!next) {
      setSubmitting(false);
      setActiveLabel(null);
      return;
    }
    const riskForMarket =
      next.market === "linear" && riskMode === "portfolio" ? "signal_only" : riskMode;
    setActiveLabel(next.market === "spot" ? "Spot" : "Futures (Linear)");
    const res = await submitBacktestRun(
      {
        symbol,
        market_type: next.market,
        interval,
        start_ms: startMs,
        end_ms: endMs,
        initial_capital: initialCapital,
        fee_rate: feeRate,
        slippage_bps: slippageBps,
        risk_mode: riskForMarket,
        data_source: "bybit_public",
        idempotency_key: next.key,
      },
      next.key,
    );
    if (!res.ok) {
      setSubmitError(
        `${next.market}: ${res.message || res.detail}`,
      );
      setSubmitting(false);
      setActiveLabel(null);
      return;
    }
    const stub: BacktestJobStatus = {
      job_id: res.data.job_id,
      status: res.data.status,
      created_ms: Date.now(),
      request_summary: { symbol, market_type: next.market, interval },
      performance_label: SIM_LABEL,
    };
    upsertJob(stub);
    pollJob(res.data.job_id);
  };

  const pollJob = (jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const st = await fetchBacktestJobStatus(jobId);
      if (!st.ok) {
        setSubmitError(st.message || st.detail);
        stopPolling();
        setSubmitting(false);
        setActiveLabel(null);
        return;
      }
      upsertJob(st.data);
      if (st.data.status === "COMPLETED" && st.data.run_id) {
        stopPolling();
        onRunCompleted(st.data.run_id);
        void startNextInQueue();
      } else if (
        st.data.status === "FAILED" ||
        st.data.status === "INTERRUPTED" ||
        st.data.status === "CANCELLED"
      ) {
        stopPolling();
        setSubmitError(
          st.data.error_message || st.data.error_code || "Backtest failed",
        );
        // Continue remaining queue so the other category can still finish.
        void startNextInQueue();
      }
    }, 1500);
  };

  const onRun = async () => {
    setSubmitError(null);
    setJobs([]);
    const err = validate();
    setValidationError(err);
    if (err) return;
    if (!caps.run_api_enabled) {
      setSubmitError(
        "Run API is disabled. Set BACKTEST_RUN_API_ENABLED=true and restart the local FastAPI.",
      );
      return;
    }
    setSubmitting(true);
    queueRef.current = marketsToRun.map((market) => ({
      market,
      key: newIdemKey(market),
    }));
    await startNextInQueue();
  };

  const showLinearNote =
    marketChoice === "linear" || marketChoice === "both";

  return (
    <section className="w-full min-w-0 max-w-full rounded-2xl border border-border bg-muted/30 p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-medium text-foreground">Run historical backtest</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Explicit operator action only. Reuses Multi-Agent Pipeline 4B + engine 68A. Never places
            live orders.
          </p>
        </div>
        <Badge
          className={
            caps.run_api_enabled
              ? "border-profit/30 bg-profit/10 text-foreground"
              : "border-warning/30 bg-warning/10 text-foreground"
          }
        >
          {caps.run_api_enabled ? "Run API on" : "Run API off"}
        </Badge>
      </div>

      <p className="mt-3 text-xs uppercase tracking-[0.14em] text-brand">{SIM_LABEL}</p>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Symbol
          </Label>
          <Select value={symbol} onValueChange={setSymbol}>
            <SelectTrigger className="mt-1.5 w-full min-w-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {caps.symbols.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Market data
          </Label>
          <Select
            value={marketChoice}
            onValueChange={(v) => {
              if (v === "linear" || v === "both" || v === "spot") setMarketChoice(v);
            }}
          >
            <SelectTrigger className="mt-1.5 w-full min-w-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="spot">Spot only</SelectItem>
              <SelectItem value="linear">Futures (Linear) only</SelectItem>
              <SelectItem value="both">Spot + Futures (both)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Timeframe
          </Label>
          <Select value={interval} onValueChange={setCandleInterval}>
            <SelectTrigger className="mt-1.5 w-full min-w-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {caps.intervals.map((iv) => (
                <SelectItem key={iv} value={iv}>
                  {iv === "15" ? "15m" : iv === "60" ? "1h" : iv === "240" ? "4h" : `${iv}m`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Start (UTC)
          </Label>
          <Input
            type="date"
            className="mt-1.5 w-full min-w-0 max-w-full"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            End (UTC)
          </Label>
          <Input
            type="date"
            className="mt-1.5 w-full min-w-0 max-w-full"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Risk mode
          </Label>
          <Select
            value={riskMode}
            onValueChange={(v) => setRiskMode(v === "portfolio" ? "portfolio" : "signal_only")}
          >
            <SelectTrigger className="mt-1.5 w-full min-w-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="signal_only">Signal only</SelectItem>
              <SelectItem value="portfolio">Portfolio (spot runs)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Initial capital (USDT)
          </Label>
          <Input
            className="mt-1.5 w-full min-w-0 font-mono"
            value={initialCapital}
            onChange={(e) => setInitialCapital(e.target.value)}
          />
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Fee rate (e.g. 0.001)
          </Label>
          <Input
            className="mt-1.5 w-full min-w-0 font-mono"
            value={feeRate}
            onChange={(e) => setFeeRate(e.target.value)}
          />
        </div>
        <div className="min-w-0">
          <Label className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            Slippage (bps)
          </Label>
          <Input
            className="mt-1.5 w-full min-w-0 font-mono"
            value={slippageBps}
            onChange={(e) => setSlippageBps(e.target.value)}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3 rounded-xl border border-border bg-muted/50 px-4 py-3 text-sm sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <p className="break-words text-foreground">
            Will run:{" "}
            <span className="text-foreground">
              {marketsToRun
                .map((m) => (m === "spot" ? "Spot" : "Futures (Linear)"))
                .join(" → then ")}
            </span>
          </p>
          <p className="mt-1 break-words text-muted-foreground">
            Estimated candles each:{" "}
            <span className="font-mono text-foreground">{estimated}</span>
            <span className="mx-2 text-foreground">·</span>
            Source: Bybit public history
          </p>
        </div>
        <Button
          type="button"
          className="w-full shrink-0 sm:w-auto"
          disabled={runDisabled}
          onClick={() => void onRun()}
        >
          <Play className="mr-1.5 h-3.5 w-3.5" />
          {busy
            ? activeLabel
              ? `Running ${activeLabel}…`
              : "Running…"
            : marketChoice === "both"
              ? "Run Spot + Futures"
              : "Run Historical Backtest"}
        </Button>
      </div>

      {showLinearNote ? (
        <div className="mt-3 flex gap-2 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-50/80">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {caps.linear_note}
          {marketChoice === "both" && riskMode === "portfolio"
            ? " Futures leg uses signal_only risk (portfolio is spot-only)."
            : null}
        </div>
      ) : null}

      {validationError ? (
        <p className="mt-3 text-sm text-destructive">{validationError}</p>
      ) : null}
      {submitError ? <p className="mt-3 text-sm text-destructive">{submitError}</p> : null}

      {jobs.length > 0 ? (
        <div className="mt-3 space-y-2">
          {jobs.map((job) => (
            <div
              key={job.job_id}
              className="rounded-xl border border-border bg-muted/70 px-4 py-3 text-sm"
            >
              <p className="text-foreground">
                <span className="text-foreground">
                  {String(job.request_summary?.market_type || "").toUpperCase() || "JOB"}
                </span>
                <span className="mx-2 text-foreground">·</span>
                <span className="font-mono text-xs">{job.job_id}</span>
                <span className="mx-2 text-foreground">·</span>
                <Badge variant="outline">{job.status}</Badge>
                {job.phase ? (
                  <span className="ml-2 text-xs text-muted-foreground">phase: {job.phase}</span>
                ) : null}
              </p>
              {job.run_id ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  Saved run: <span className="font-mono">{job.run_id}</span>
                </p>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {!caps.run_api_enabled ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Enable with <code className="rounded bg-muted px-1">BACKTEST_RUN_API_ENABLED=true</code>{" "}
          and restart the local FastAPI loopback.
        </p>
      ) : null}
    </section>
  );
}
