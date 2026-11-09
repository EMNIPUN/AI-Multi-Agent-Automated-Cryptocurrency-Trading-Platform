"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import {
  fetchAutoEngineStatus,
  fetchPublicSignalEvaluate,
  fetchSignalAnalytics,
  fetchSignalHistory,
  fetchSignalStatus,
  fetchSignalSyncStatus,
  startAutoEngine,
  stopAutoEngine,
} from "@/lib/signals/api";
import type { SignalDecision, SignalHistoryItem } from "@/lib/signals/types";
import { cn } from "@/lib/utils";

function actionVariant(action: string) {
  if (action === "BUY") return "success" as const;
  if (action === "SELL") return "danger" as const;
  if (action === "BLOCKED") return "warning" as const;
  return "secondary" as const;
}

function msLabel(ms: number | null | undefined) {
  if (ms == null || !Number.isFinite(ms)) return "—";
  return new Date(ms).toLocaleString();
}

function MetricTile({
  label,
  children,
  className,
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-xl border border-border bg-muted/40 px-3 py-2.5",
        className,
      )}
    >
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <div className="mt-1 min-w-0 break-words font-mono text-xs text-foreground">{children}</div>
    </div>
  );
}

export function SignalsPanel({
  symbol = "BTCUSDT",
  category = "linear",
  interval = "15",
}: {
  symbol?: string;
  category?: string;
  interval?: string;
}) {
  const [decision, setDecision] = useState<SignalDecision | null>(null);
  const [history, setHistory] = useState<SignalHistoryItem[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(null);
  const [engine, setEngine] = useState<Record<string, unknown> | null>(null);
  const [sync, setSync] = useState<Record<string, unknown> | null>(null);
  const [filterAction, setFilterAction] = useState<string>("");
  const [pathLabel, setPathLabel] = useState("—");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [engineBusy, setEngineBusy] = useState(false);
  const [selected, setSelected] = useState<SignalHistoryItem | null>(null);
  const [paperLinkNote, setPaperLinkNote] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [status, evalRes, hist, stats, eng, syncStatus] = await Promise.all([
        fetchSignalStatus(),
        fetchPublicSignalEvaluate({ symbol, category, interval }),
        fetchSignalHistory({
          symbol,
          interval,
          action: filterAction || undefined,
          limit: 40,
        }),
        fetchSignalAnalytics(),
        fetchAutoEngineStatus(),
        fetchSignalSyncStatus(),
      ]);
      setDecision(evalRes.decision);
      setHistory(hist.items || []);
      setAnalytics(stats);
      setEngine(eng);
      setSync(syncStatus);
      const path = evalRes.decision.market.data_path || "public";
      const ver = String(status.strategy_version || evalRes.decision.strategy_version || "");
      setPathLabel(`${path} · ${ver} · SIGNALS ONLY`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "signals_unavailable");
    } finally {
      setLoading(false);
    }
  }, [symbol, category, interval, filterAction]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void fetchAutoEngineStatus()
        .then(setEngine)
        .catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!selected?.decision_id) {
      setPaperLinkNote(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/paper/orders/by-signal/${encodeURIComponent(selected.decision_id)}`,
          { cache: "no-store" },
        );
        const body = await res.json().catch(() => null);
        if (cancelled) return;
        if (!res.ok) {
          setPaperLinkNote(
            res.status === 503
              ? "Paper read API disabled or unavailable — no auto trade created."
              : "Paper link lookup unavailable",
          );
          return;
        }
        setPaperLinkNote(
          body?.linked
            ? String(body.message)
            : "No paper trade linked to this signal",
        );
      } catch {
        if (!cancelled) setPaperLinkNote("Paper link lookup unavailable");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected?.decision_id]);

  const onEngineStart = async () => {
    setEngineBusy(true);
    setError(null);
    try {
      setEngine(await startAutoEngine());
    } catch (err) {
      setError(err instanceof Error ? err.message : "engine_start_failed");
    } finally {
      setEngineBusy(false);
    }
  };

  const onEngineStop = async () => {
    setEngineBusy(true);
    setError(null);
    try {
      setEngine(await stopAutoEngine());
    } catch (err) {
      setError(err instanceof Error ? err.message : "engine_stop_failed");
    } finally {
      setEngineBusy(false);
    }
  };

  const byAction = (analytics?.by_action as Record<string, number> | undefined) || {};
  const lastCandle = engine?.last_candle as
    | {
        symbol?: string;
        interval?: string;
        candle_start_ms?: number;
        candle_close_ms?: number;
        source?: string;
      }
    | null
    | undefined;
  const lastSignal = engine?.last_persisted_signal as
    | {
        action?: string;
        decision_id?: string;
        symbol?: string;
        signal_strength?: number;
      }
    | null
    | undefined;
  const outbox = sync?.outbox as
    | {
        pending?: number;
        failed?: number;
        synced?: number;
        last_synced_at_ms?: number;
      }
    | undefined;
  const ownerReady = Boolean(
    (sync?.owner_binding as { sync_owner_ready?: boolean } | undefined)?.sync_owner_ready,
  );
  const audit = Array.isArray(engine?.audit)
    ? (engine.audit as Array<{ event_type: string; created_at_ms: number }>)
    : [];

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-base">Phase 4C automatic signal engine</CardTitle>
            <CardDescription>
              Closed-candle SIGNAL evaluation only — never automatic trading or order submission.
            </CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              className="rounded-full"
              onClick={() => void onEngineStart()}
              disabled={engineBusy || String(engine?.state) === "running"}
            >
              {engineBusy && String(engine?.state) !== "running" ? (
                <Spinner className="mr-1" data-icon="inline-start" />
              ) : null}
              Start auto
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="rounded-full"
              onClick={() => void onEngineStop()}
              disabled={engineBusy || String(engine?.state || "stopped") === "stopped"}
            >
              {engineBusy && String(engine?.state) === "running" ? (
                <Spinner className="mr-1" data-icon="inline-start" />
              ) : null}
              Stop
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="rounded-full"
              onClick={() => void refresh()}
              disabled={loading}
            >
              {loading ? <Spinner className="mr-1" data-icon="inline-start" /> : null}
              {loading ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="rounded-full">
              engine {String(engine?.state ?? "stopped")}
            </Badge>
            <Badge variant="outline" className="rounded-full">
              v{String(engine?.engine_version ?? "4C")}
            </Badge>
            <Badge variant="sample" className="rounded-full">
              NOT AUTOMATIC TRADING
            </Badge>
            {engine?.last_error ? (
              <Badge variant="warning" className="rounded-full">
                error
              </Badge>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={sync?.cloud_writes_allowed ? "success" : "secondary"}
              className="rounded-full"
            >
              supabase writes {sync?.cloud_writes_allowed ? "armed" : "OFF"}
            </Badge>
            <Badge
              variant={sync?.sync_allowed ? "success" : "secondary"}
              className="rounded-full"
            >
              auto-sync {sync?.sync_allowed ? "armed" : "OFF"}
            </Badge>
            <Badge variant="outline" className="rounded-full">
              pending {String(outbox?.pending ?? 0)}
            </Badge>
            <Badge variant="outline" className="rounded-full">
              failed {String(outbox?.failed ?? 0)}
            </Badge>
            <Badge variant="outline" className="rounded-full">
              synced {String(outbox?.synced ?? 0)}
            </Badge>
            <Badge variant="outline" className="rounded-full">
              last cloud sync{" "}
              {outbox?.last_synced_at_ms ? msLabel(outbox.last_synced_at_ms) : "never"}
            </Badge>
            <Badge variant="outline" className="rounded-full">
              owner {ownerReady ? "bound" : "unbound"}
            </Badge>
          </div>

          <p className="text-xs text-muted-foreground">
            Local SQLite is the durable authority for risk and scheduler. Cloud-confirmed only
            after gated Supabase sync (writes/sync OFF until operator approval). History below
            is local-only — signal counts are not PnL.
          </p>

          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <MetricTile label="Last candle">
              {lastCandle ? (
                <div className="space-y-0.5">
                  <div className="truncate">
                    {lastCandle.symbol ?? "—"} · {lastCandle.interval ?? "—"}m
                  </div>
                  <div className="truncate text-muted-foreground">
                    close {msLabel(lastCandle.candle_close_ms)}
                  </div>
                  <div className="truncate text-muted-foreground">
                    src {lastCandle.source ?? "—"}
                  </div>
                </div>
              ) : (
                "—"
              )}
            </MetricTile>
            <MetricTile label="Last signal">
              {lastSignal ? (
                <div className="space-y-0.5">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <Badge
                      variant={actionVariant(String(lastSignal.action ?? ""))}
                      className="rounded-full"
                    >
                      {String(lastSignal.action ?? "—")}
                    </Badge>
                    <span className="truncate text-muted-foreground">
                      {lastSignal.symbol ?? ""}
                    </span>
                  </div>
                  <div className="truncate text-muted-foreground">
                    {lastSignal.decision_id ?? "—"}
                  </div>
                </div>
              ) : (
                "—"
              )}
            </MetricTile>
            <MetricTile label="Lag ms">
              {String(engine?.processing_lag_ms ?? "—")}
            </MetricTile>
            <MetricTile label="Freshness ms">
              {String(engine?.data_freshness_ms ?? "—")}
            </MetricTile>
          </div>

          {audit.length > 0 ? (
            <div className="rounded-xl border border-border bg-muted/50">
              <div className="flex items-center justify-between gap-2 px-3 py-2">
                <p className="text-xs font-medium text-foreground">Engine audit</p>
                <span className="text-[11px] text-muted-foreground">{audit.length} events</span>
              </div>
              <Separator className="bg-muted/40" />
              <ScrollArea className="h-28">
                <div className="space-y-1 px-3 py-2 font-mono text-[11px] text-muted-foreground">
                  {audit.map((a, i) => (
                    <div
                      key={`${a.event_type}-${a.created_at_ms}-${i}`}
                      className="truncate"
                    >
                      {new Date(a.created_at_ms).toLocaleTimeString()} · {a.event_type}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="text-base">Phase 4B/4C multi-agent signals</CardTitle>
            <CardDescription>
              Symmetric directional conviction + market-quality gate + paper risk. Not an executed
              trade.
            </CardDescription>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="rounded-full"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? <Spinner className="mr-1" data-icon="inline-start" /> : null}
            {loading ? "Evaluating…" : "Manual evaluate"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{pathLabel}</Badge>
            <Badge variant="sample">NOT AN ORDER</Badge>
            {decision ? <Badge variant={actionVariant(decision.action)}>{decision.action}</Badge> : null}
            {decision?.source_mode ? <Badge variant="secondary">{decision.source_mode}</Badge> : null}
          </div>

          {error ? <p className="text-amber-300">{error}</p> : null}

          {decision ? (
            <>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <div className="text-[11px] text-muted-foreground">Symbol</div>
                  <div className="font-mono">
                    {decision.symbol} · {decision.category} · {decision.interval}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-muted-foreground">Conviction / quality</div>
                  <div className="font-mono">
                    {(decision.directional_conviction ?? 0).toFixed(3)} /{" "}
                    {(decision.market_quality ?? 0).toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-muted-foreground">Signal strength</div>
                  <div className="font-mono">{decision.signal_strength.toFixed(3)}</div>
                </div>
                <div>
                  <div className="text-[11px] text-muted-foreground">Risk</div>
                  <div className="font-mono">{decision.risk.verdict}</div>
                </div>
              </div>

              <p className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs">
                {decision.news_advisory?.label ||
                  decision.news_influence_label ||
                  "News Advisory Only — Trading Decisions Unchanged"}
                {decision.news_advisory?.enabled
                  ? ` · freshness ${decision.news_advisory.freshness || "unknown"} · storage ${decision.news_advisory.storage_availability || "unknown"}`
                  : " · advisory off"}
                {" · news_changed_decision=false"}
              </p>
              <p className="text-xs text-muted-foreground">{decision.signal_strength_note}</p>
              <p>{decision.explanation}</p>

              <div className="grid gap-2 md:grid-cols-3">
                {decision.contributions.map((c) => (
                  <div
                    key={c.agent_id}
                    className={cn(
                      "rounded-lg border border-border/60 bg-muted/20 p-2",
                      c.timed_out && "border-amber-500/40",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium capitalize">{c.agent_id}</span>
                      <Badge variant="outline">{c.bias}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{c.explanation}</p>
                  </div>
                ))}
              </div>

              {(decision.risk.verdict === "VETO" || decision.risk.verdict === "HALTED") && (
                <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
                  Risk veto: {decision.risk.explanation} ({decision.risk.reason_codes.join(", ")})
                </div>
              )}

              <div className="rounded-lg border border-border/60 p-2 font-mono text-xs">
                <div>Hypothetical entry {decision.levels.entry ?? "—"}</div>
                <div>Stop {decision.levels.stop_loss ?? "—"}</div>
                <div>Take profit {decision.levels.take_profit ?? "—"}</div>
                <div className="mt-1 text-muted-foreground">{decision.levels.note}</div>
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">No decision yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Local signal history</CardTitle>
          <CardDescription>
            SQLite persistence on the API host. Counts are signal tallies — not win rate or PnL.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2">
            {["", "BUY", "SELL", "HOLD", "BLOCKED"].map((a) => (
              <Button
                key={a || "ALL"}
                size="sm"
                variant={filterAction === a ? "default" : "outline"}
                onClick={() => setFilterAction(a)}
              >
                {a || "ALL"}
                {a && byAction[a] != null ? ` (${byAction[a]})` : ""}
              </Button>
            ))}
          </div>

          {analytics ? (
            <div className="grid gap-2 sm:grid-cols-4 font-mono text-xs">
              <div>Total {String(analytics.total_signals ?? 0)}</div>
              <div>Blocked/veto {String(analytics.risk_veto_or_blocked ?? 0)}</div>
              <div>Conflicts {String(analytics.agent_disagreement ?? 0)}</div>
              <div className="text-muted-foreground">{String(analytics.metrics_note ?? "")}</div>
            </div>
          ) : null}

          <ScrollArea className="h-72 rounded-xl border border-border bg-muted/40">
            <div className="space-y-1 p-2">
              {history.length === 0 ? (
                <p className="px-2 py-8 text-center text-muted-foreground">
                  No stored signals yet.
                </p>
              ) : (
                history.map((row) => (
                  <button
                    key={row.decision_id}
                    type="button"
                    onClick={() => setSelected(row)}
                    className={cn(
                      "flex w-full min-w-0 items-center justify-between gap-2 rounded-md border border-border/50 px-2 py-1.5 text-left hover:bg-muted/40",
                      selected?.decision_id === row.decision_id &&
                        "border-primary/50 bg-primary/10",
                    )}
                  >
                    <span className="min-w-0 truncate font-mono text-xs">
                      {new Date(row.timestamp_ms).toLocaleString()} · {row.symbol} ·{" "}
                      {row.interval}
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      <Badge variant={actionVariant(String(row.action))}>{row.action}</Badge>
                      <Badge variant="outline">{row.source_mode}</Badge>
                      <Badge variant="secondary">local</Badge>
                      <span className="hidden font-mono text-[10px] text-muted-foreground sm:inline">
                        {row.strategy_version}
                      </span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </ScrollArea>

          {selected ? (
            <div className="rounded-lg border border-border/60 bg-muted/20 p-3 text-xs space-y-1">
              <div className="font-medium">Signal detail (not a trade)</div>
              <div className="font-mono">{selected.decision_id}</div>
              <div>
                Risk {selected.risk_verdict} · strength {selected.signal_strength.toFixed(3)} ·
                conviction {selected.directional_conviction.toFixed(3)}
              </div>
              <div>{selected.explanation}</div>
              <div className="text-muted-foreground">{selected.reason_codes.join(", ")}</div>
              <div className="font-mono">
                Entry {(selected.levels as { entry?: number }).entry ?? "—"} · SL{" "}
                {(selected.levels as { stop_loss?: number }).stop_loss ?? "—"} · TP{" "}
                {(selected.levels as { take_profit?: number }).take_profit ?? "—"}
              </div>
              <div className="text-muted-foreground">
                {paperLinkNote ?? "Checking paper link…"}
              </div>
              <Link
                href={`/paper?signal=${encodeURIComponent(selected.decision_id)}`}
                className="inline-block text-primary underline-offset-4 hover:underline"
              >
                Open paper journal for this signal
              </Link>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
