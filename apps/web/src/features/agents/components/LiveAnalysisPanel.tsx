"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { DataFreshness, ErrorState, FinancialValue, ReasonList, StatusBadge, StatusIndicator } from "@/components/design-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchPublicSignalEvaluate } from "@/lib/signals/api";
import type { SignalDecision } from "@/lib/signals/types";
import { intervalLabel } from "@/lib/formatting/time";
import { DEFAULT_WATCHLIST, INTERVAL_OPTIONS, type MarketCategory } from "@/lib/market/types";
import { cn } from "@/lib/utils";

const REFRESH_MS = 60_000;
/** Symbols the public signals endpoint accepts (backend allowlist). */
export const ANALYSIS_SYMBOLS: readonly string[] = DEFAULT_WATCHLIST;

function indicator(decision: SignalDecision | null, agentId: string, key: string): unknown {
  const c = decision?.contributions.find((x) => x.agent_id === agentId);
  return c?.indicators?.[key];
}

function num(v: unknown, digits = 2): string {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

type Props = {
  /** Controlled scope (e.g. from the Markets terminal). When omitted the panel owns its selectors. */
  symbol?: string;
  category?: MarketCategory;
  interval?: string;
  compact?: boolean;
  title?: string;
};

/**
 * Live Analysis = the signals-only pipeline evaluated on current public
 * candles. Research output: `execution_allowed` is always false and the panel
 * says so. No private API, no orders.
 */
export function LiveAnalysisPanel(props: Props) {
  const controlled = props.symbol !== undefined;
  const [ownCategory, setCategory] = useState<MarketCategory>("linear");
  const [ownSymbol, setSymbol] = useState<string>("BTCUSDT");
  const [ownInterval, setInterval_] = useState("15");
  const category = props.category ?? ownCategory;
  const symbol = props.symbol ?? ownSymbol;
  const interval = props.interval ?? ownInterval;
  const allowed = ANALYSIS_SYMBOLS.includes(symbol);

  const [decision, setDecision] = useState<SignalDecision | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [evaluatedAt, setEvaluatedAt] = useState<number | null>(null);
  const seq = useRef(0);

  const run = useCallback(async () => {
    const id = ++seq.current;
    if (!allowed) {
      setDecision(null);
      setLoading(false);
      return;
    }
    setRefreshing(true);
    try {
      const res = await fetchPublicSignalEvaluate({ symbol, category, interval });
      if (id !== seq.current) return;
      setDecision(res.decision);
      setNote(res.note || null);
      setError(null);
      setEvaluatedAt(Date.now());
    } catch (err) {
      if (id !== seq.current) return;
      setError(err instanceof Error ? err.message : "signals_evaluate_failed");
    } finally {
      if (id === seq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [symbol, category, interval, allowed]);

  useEffect(() => {
    setLoading(true);
    void run();
    const t = window.setInterval(() => {
      if (!document.hidden) void run();
    }, REFRESH_MS);
    return () => window.clearInterval(t);
  }, [run]);

  const trend = decision?.contributions.find((c) => c.agent_id === "trend");
  const momentum = decision?.contributions.find((c) => c.agent_id === "momentum");
  const regime = decision?.contributions.find((c) => c.agent_id === "regime");
  const riskTone = decision?.risk.verdict === "APPROVED" ? "ok" : decision?.risk.verdict ? "danger" : "neutral";

  return (
    <SectionPanel
      title={props.title ?? "Live market analysis"}
      description={props.compact ? undefined : "Current public candles through the signals-only pipeline. Research output — not an order and not live-money execution."}
      className={props.compact ? "p-4" : undefined}
      actions={
        <Button variant="outline" size="sm" className="rounded-full" onClick={() => void run()} disabled={refreshing || !allowed}>
          <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", refreshing && "animate-spin")} aria-hidden />
          Re-evaluate
        </Button>
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {!controlled ? (
          <>
            <Tabs value={category} onValueChange={(v) => setCategory(v as MarketCategory)}>
              <TabsList className="w-auto" aria-label="Market category">
                <TabsTrigger value="linear">Perp</TabsTrigger>
                <TabsTrigger value="spot">Spot</TabsTrigger>
              </TabsList>
            </Tabs>
            <Tabs value={symbol} onValueChange={setSymbol}>
              <TabsList className="w-auto" aria-label="Symbol">
                {ANALYSIS_SYMBOLS.map((s) => (
                  <TabsTrigger key={s} value={s}>{s.replace("USDT", "")}</TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Tabs value={interval} onValueChange={setInterval_}>
              <TabsList className="w-auto" aria-label="Timeframe">
                {INTERVAL_OPTIONS.map((o) => (
                  <TabsTrigger key={o.value} value={o.value}>{o.label}</TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </>
        ) : (
          <span className="font-mono text-xs text-muted-foreground">{symbol} · {category} · {intervalLabel(interval)}</span>
        )}
        <span className="ml-auto flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <StatusBadge label="execution_allowed = false" tone="neutral" />
          <DataFreshness at={evaluatedAt} staleAfterMs={REFRESH_MS * 2} label="evaluated" missingLabel="Not evaluated" />
        </span>
      </div>

      {!allowed ? (
        <p className="rounded-xl border border-dashed border-border px-3 py-4 text-xs text-muted-foreground">
          Public signal evaluation is available for {ANALYSIS_SYMBOLS.map((s) => s.replace("USDT", "")).join(", ")} only. Other symbols are analyzed through the Orchestrator and the paper supervisor.
        </p>
      ) : error && !decision ? (
        <ErrorState title="Evaluation unavailable" code={error} at={evaluatedAt ?? Date.now()} onRetry={() => void run()} retrying={refreshing} compact />
      ) : loading && !decision ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: props.compact ? 4 : 8 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />)}</div>
      ) : decision ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status={decision.action === "BUY" || decision.action === "SELL" ? "OK" : decision.action} label={`Strategy ${decision.action}`} size="md" />
            <StatusBadge label={`Risk ${decision.risk.verdict}`} tone={riskTone} />
            <StatusBadge label={decision.market.data_fresh ? "Candles fresh" : "Candles stale"} tone={decision.market.data_fresh ? "ok" : "stale"} />
            <span className="font-mono text-xs text-muted-foreground">{decision.market.bar_count} bars · v{decision.strategy_version}</span>
          </div>
          <p className="text-sm text-foreground">{decision.explanation}</p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Tile label="Latest confirmed candle">
              <FinancialValue value={decision.market.last_price} maxDigits={6} size="md" />
              <div className="mt-1"><DataFreshness at={decision.market.newest_close_ms} staleAfterMs={3 * (Number(interval) || 15) * 60_000} /></div>
            </Tile>
            <Tile label="Trend">
              <span className="font-mono text-sm text-foreground">{trend?.bias ?? "—"}{trend ? ` · ${Math.round(trend.confidence * 100)}%` : ""}</span>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">EMA20 {num(indicator(decision, "trend", "ema_20"), 4)} · EMA50 {num(indicator(decision, "trend", "ema_50"), 4)} · EMA200 {num(indicator(decision, "trend", "ema_200"), 4)}</p>
            </Tile>
            <Tile label="Momentum">
              <span className="font-mono text-sm text-foreground">{momentum?.bias ?? "—"}{momentum ? ` · ${Math.round(momentum.confidence * 100)}%` : ""}</span>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">RSI14 {num(indicator(decision, "momentum", "rsi_14"))} · mom5 {num(Number(indicator(decision, "momentum", "momentum_5")) * 100)}%</p>
            </Tile>
            <Tile label="Regime">
              <span className="font-mono text-sm text-foreground">{String(regime?.indicators?.regime ?? "—")}</span>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">efficiency {num(indicator(decision, "regime", "efficiency_ratio"), 3)} · ATR {num(Number(indicator(decision, "regime", "atr_pct")) * 100)}%</p>
            </Tile>
          </div>
          {!props.compact ? (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Tile label="Signal strength"><span className="font-mono text-sm">{Math.round(decision.signal_strength * 100)}/100</span></Tile>
                <Tile label="Market quality"><span className="font-mono text-sm">{decision.market_quality != null ? `${Math.round(decision.market_quality * 100)}/100` : "—"}</span></Tile>
                <Tile label="Hypothetical levels">
                  <span className="font-mono text-[11px] text-foreground">
                    E <FinancialValue value={decision.levels.entry} maxDigits={6} size="xs" /> · SL <FinancialValue value={decision.levels.stop_loss} maxDigits={6} size="xs" /> · TP <FinancialValue value={decision.levels.take_profit} maxDigits={6} size="xs" />
                  </span>
                  <p className="mt-1 text-[10px] text-muted-foreground">{decision.levels.note}</p>
                </Tile>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Decision reasons</p>
                  <ReasonList codes={decision.reason_codes} />
                </div>
                <div>
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Risk engine</p>
                  <p className="mb-2 text-xs text-muted-foreground">{decision.risk.explanation}</p>
                  <ReasonList codes={decision.risk.reason_codes} compact />
                </div>
              </div>
            </>
          ) : (
            <ReasonList codes={decision.reason_codes} compact max={3} />
          )}
          {note && !props.compact ? <p className="text-[11px] text-muted-foreground">{note}</p> : null}
        </div>
      ) : null}
    </SectionPanel>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-muted/40 px-3 py-2.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <div className="mt-1 min-w-0 break-words">{children}</div>
    </div>
  );
}
