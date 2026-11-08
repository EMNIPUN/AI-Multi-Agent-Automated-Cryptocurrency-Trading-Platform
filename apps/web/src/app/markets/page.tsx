"use client";

import { useMemo, useState, useTransition } from "react";
import { Radio, SlidersHorizontal } from "lucide-react";

import { MarketCandleChart } from "@/components/market/MarketCandleChart";
import { MarketConnectionBadge } from "@/components/market/MarketConnectionBadge";
import { OrderBookPanel } from "@/components/market/OrderBookPanel";
import { RecentTradesFeed } from "@/components/market/RecentTradesFeed";
import { AnimatedCircularProgressBar } from "@/components/magicui/animated-circular-progress-bar";
import { BlurFade } from "@/components/magicui/blur-fade";
import { BorderBeam } from "@/components/magicui/border-beam";
import { NumberTicker } from "@/components/magicui/number-ticker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { lastRsi } from "@/lib/market/candles";
import { useMarketStream } from "@/lib/market/use-market-stream";
import {
  DEFAULT_WATCHLIST,
  INTERVAL_OPTIONS,
  type MarketCategory,
} from "@/lib/market/types";
import { cn } from "@/lib/utils";

export default function MarketsPage() {
  const [category, setCategory] = useState<MarketCategory>("linear");
  const [symbol, setSymbol] = useState<string>("BTCUSDT");
  const [interval, setTf] = useState("15");
  const [, startTransition] = useTransition();

  const stream = useMarketStream({
    category,
    symbol,
    interval,
    watchlist: DEFAULT_WATCHLIST,
  });

  const selectedTicker = useMemo(
    () => stream.tickers.find((t) => t.symbol === symbol) ?? null,
    [stream.tickers, symbol],
  );
  const rsiValue = stream.indicators ? lastRsi(stream.indicators.rsi_14) : null;
  const pct = selectedTicker?.price_24h_pct;
  const pctUp = pct != null && pct >= 0;

  const modeLabel =
    stream.streamMode === "streaming"
      ? stream.stale
        ? "WS STALE"
        : "WS LIVE"
      : stream.streamMode === "rest_fallback"
        ? "REST FALLBACK"
        : stream.streamMode === "connecting"
          ? "CONNECTING"
          : "DISCONNECTED";

  const base = symbol.replace("USDT", "");

  return (
    <div className="space-y-4 pb-6">
      <BlurFade>
        <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-5 md:p-6">
          <BorderBeam size={240} duration={14} colorFrom="#f59e0b" colorTo="#ffffff" />
          <div className="relative z-10 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-amber-200/80">
                Public markets
              </p>
              <h1 className="text-metallic mt-1 text-3xl font-medium tracking-tight md:text-4xl">
                Markets
              </h1>
              <p className="mt-2 max-w-xl text-sm text-white/55">
                Live Bybit prices, candles, order book, and trades — read-only. No wallet or order
                entry here.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <MarketConnectionBadge
                state={
                  stream.error && stream.streamMode === "disconnected"
                    ? "error"
                    : stream.connectionState
                }
                stale={stream.stale}
              />
              <Badge
                variant={stream.live ? "outline" : "warning"}
                className="rounded-full border-white/15"
              >
                <Radio className="mr-1 h-3 w-3" />
                {modeLabel}
              </Badge>
              {stream.updatedAt ? (
                <span className="text-[11px] text-white/40">{stream.updatedAt}</span>
              ) : null}
            </div>
          </div>
        </section>
      </BlurFade>

      <BlurFade delay={0.04}>
        <div className="flex items-center gap-2">
          <div className="hidden min-w-0 flex-1 flex-wrap items-center gap-2 md:flex">
            <Tabs
              value={category}
              onValueChange={(value) =>
                startTransition(() => setCategory(value as MarketCategory))
              }
            >
              <TabsList className="w-auto" aria-label="Market category">
                <TabsTrigger value="linear">Perp</TabsTrigger>
                <TabsTrigger value="spot">Spot</TabsTrigger>
              </TabsList>
            </Tabs>
            <Separator orientation="vertical" className="hidden h-8 bg-white/15 sm:block" />
            <Tabs
              value={symbol}
              onValueChange={(value) => startTransition(() => setSymbol(value))}
            >
              <TabsList className="w-auto" aria-label="Symbol">
                {DEFAULT_WATCHLIST.map((s) => (
                  <TabsTrigger key={s} value={s}>
                    {s.replace("USDT", "")}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Separator orientation="vertical" className="hidden h-8 bg-white/15 lg:block" />
            <Tabs
              value={interval}
              onValueChange={(value) => startTransition(() => setTf(value))}
            >
              <TabsList className="w-auto" aria-label="Timeframe">
                {INTERVAL_OPTIONS.map((opt) => (
                  <TabsTrigger key={opt.value} value={opt.value}>
                    {opt.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          </div>

          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm" className="rounded-full md:hidden">
                <SlidersHorizontal className="h-4 w-4" />
                Filters
              </Button>
            </SheetTrigger>
            <SheetContent side="bottom" className="rounded-t-3xl border-white/10 bg-card/95">
              <SheetHeader>
                <SheetTitle>Market filters</SheetTitle>
                <SheetDescription>Category, symbol, and timeframe</SheetDescription>
              </SheetHeader>
              <div className="mt-4 space-y-4">
                <Tabs
                  value={category}
                  onValueChange={(value) =>
                    startTransition(() => setCategory(value as MarketCategory))
                  }
                >
                  <TabsList className="w-full" aria-label="Market category">
                    <TabsTrigger value="linear">Perp</TabsTrigger>
                    <TabsTrigger value="spot">Spot</TabsTrigger>
                  </TabsList>
                </Tabs>
                <Tabs
                  value={symbol}
                  onValueChange={(value) => startTransition(() => setSymbol(value))}
                >
                  <TabsList className="w-full" aria-label="Symbol">
                    {DEFAULT_WATCHLIST.map((s) => (
                      <TabsTrigger key={s} value={s}>
                        {s.replace("USDT", "")}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <Tabs
                  value={interval}
                  onValueChange={(value) => startTransition(() => setTf(value))}
                >
                  <TabsList className="w-full" aria-label="Timeframe">
                    {INTERVAL_OPTIONS.map((opt) => (
                      <TabsTrigger key={opt.value} value={opt.value}>
                        {opt.label}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
              </div>
            </SheetContent>
          </Sheet>

          <div className="hidden text-xs text-white/45 md:block">
            {category === "linear" ? "Perp" : "Spot"} · {symbol.replace("USDT", "")} ·{" "}
            {INTERVAL_OPTIONS.find((o) => o.value === interval)?.label ?? interval}
          </div>
        </div>
      </BlurFade>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_19rem]">
        <BlurFade delay={0.06} className="min-w-0 space-y-4">
          <section className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.03] p-4 md:p-5">
            <BorderBeam size={200} duration={12} colorFrom="#f59e0b" colorTo="#ffffff" />
            <div className="relative z-10 mb-4 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-xs text-white/45">
                  {category === "linear" ? "USDT perpetual" : "Spot"} · {symbol}
                </p>
                <div className="mt-1 flex flex-wrap items-baseline gap-3">
                  <span className="font-mono text-3xl tracking-tight text-white md:text-4xl">
                    {selectedTicker ? (
                      <NumberTicker
                        value={selectedTicker.last_price}
                        decimalPlaces={selectedTicker.last_price >= 100 ? 1 : 4}
                      />
                    ) : (
                      <Skeleton className="inline-block h-9 w-36 rounded-md" />
                    )}
                  </span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 font-mono text-sm",
                      pct == null
                        ? "text-white/40"
                        : pctUp
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "bg-rose-500/10 text-rose-400",
                    )}
                  >
                    {pct == null ? "—" : `${pctUp ? "+" : ""}${pct.toFixed(2)}%`}
                  </span>
                </div>
                <p className="mt-1 text-sm font-medium text-white/70">{base}/USDT</p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <div className="text-right text-xs text-white/45">
                  <p>24h volume</p>
                  <p className="mt-0.5 font-mono text-sm text-white">
                    {selectedTicker?.volume_24h != null
                      ? selectedTicker.volume_24h.toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })
                      : "—"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <AnimatedCircularProgressBar
                    value={rsiValue == null ? 0 : Math.min(100, Math.max(0, rsiValue))}
                    gaugePrimaryColor={
                      rsiValue == null
                        ? "rgba(255,255,255,0.25)"
                        : rsiValue >= 70
                          ? "#fb7185"
                          : rsiValue <= 30
                            ? "#34d399"
                            : "#f59e0b"
                    }
                    gaugeSecondaryColor="rgba(255,255,255,0.1)"
                    label="RSI"
                    className="size-20 text-sm"
                  />
                </div>
              </div>
            </div>

            <div className="relative z-10">
              <MarketCandleChart
                candles={stream.candles}
                indicators={stream.indicators}
                live={stream.live}
                symbol={symbol}
                interval={interval}
              />
            </div>
          </section>

          <div className="grid gap-3 sm:grid-cols-3">
            {DEFAULT_WATCHLIST.map((sym) => {
              const t = stream.tickers.find((x) => x.symbol === sym);
              const change = t?.price_24h_pct;
              const up = change != null && change >= 0;
              return (
                <button
                  key={sym}
                  type="button"
                  onClick={() => startTransition(() => setSymbol(sym))}
                  className={cn(
                    "cn-glow-card p-3.5 text-left",
                    symbol === sym && "border-white/30 bg-white/10",
                  )}
                >
                  <div className="flex items-center justify-between text-[11px] text-white/45">
                    <span>{sym.replace("USDT", "")}/USDT</span>
                    <span
                      className={
                        up ? "text-emerald-400" : change == null ? "" : "text-rose-400"
                      }
                    >
                      {change == null ? "—" : `${up ? "+" : ""}${change.toFixed(2)}%`}
                    </span>
                  </div>
                  <div className="mt-1.5 font-mono text-lg text-white">
                    {t
                      ? t.last_price.toLocaleString(undefined, { maximumFractionDigits: 4 })
                      : "—"}
                  </div>
                </button>
              );
            })}
          </div>
        </BlurFade>

        <BlurFade delay={0.08} className="space-y-4">
          <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-4">
            <h2 className="mb-3 text-sm font-medium text-white">Order book</h2>
            <OrderBookPanel book={stream.book} />
          </section>

          <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-white">Recent trades</h2>
              <Badge variant="outline" className="rounded-full border-white/15 text-[10px]">
                Live
              </Badge>
            </div>
            <RecentTradesFeed trades={stream.trades} />
          </section>

          {stream.error ? (
            <p className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              {stream.error}
            </p>
          ) : null}
        </BlurFade>
      </div>
    </div>
  );
}
