"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { Plus, Search, SlidersHorizontal, Star, X } from "lucide-react";

import { SectionPanel } from "@/components/command-center";
import { DataFreshness, FinancialValue, StatusBadge, StatusIndicator, TradingTerminalTemplate } from "@/components/design-system";
import { MarketCandleChart } from "@/components/market/MarketCandleChart";
import { OrderBookPanel } from "@/components/market/OrderBookPanel";
import { RecentTradesFeed } from "@/components/market/RecentTradesFeed";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LiveAnalysisPanel } from "@/features/agents/components/LiveAnalysisPanel";
import { FAVORITES_KEY, WATCHLIST_KEY, defaultWatchlist, normalizeSymbol, readList, writeList } from "@/features/markets/lib/watchlist";
import { lastRsi } from "@/lib/market/candles";
import { useMarketStream } from "@/lib/market/use-market-stream";
import { INTERVAL_OPTIONS, type MarketCategory, type MarketTicker } from "@/lib/market/types";
import { formatCompact } from "@/lib/formatting/decimal";
import { cn } from "@/lib/utils";

function pctClass(pct: number | null | undefined) {
  if (pct == null) return "text-muted-foreground";
  return pct >= 0 ? "text-profit" : "text-loss";
}

function WatchlistRow({ symbol, ticker, active, favorite, onSelect, onFavorite, onRemove, removable }: {
  symbol: string;
  ticker: MarketTicker | undefined;
  active: boolean;
  favorite: boolean;
  onSelect: () => void;
  onFavorite: () => void;
  onRemove: () => void;
  removable: boolean;
}) {
  return (
    <li className={cn("group flex items-center gap-1 rounded-xl border px-2 py-1.5 transition-colors", active ? "border-brand/50 bg-brand/10" : "border-transparent hover:bg-muted/60")}>
      <button type="button" onClick={onFavorite} aria-label={favorite ? `Unfavorite ${symbol}` : `Favorite ${symbol}`} aria-pressed={favorite} className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <Star className={cn("h-3.5 w-3.5", favorite && "fill-brand text-brand")} aria-hidden />
      </button>
      <button type="button" onClick={onSelect} aria-current={active ? "true" : undefined} className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
        <span className="truncate text-xs font-medium text-foreground">{symbol.replace("USDT", "")}<span className="text-muted-foreground">/USDT</span></span>
        <span className="text-right">
          <span className="block font-mono text-xs text-foreground">{ticker ? ticker.last_price.toLocaleString(undefined, { maximumFractionDigits: ticker.last_price >= 100 ? 1 : 4 }) : "—"}</span>
          <span className={cn("block font-mono text-[10px]", pctClass(ticker?.price_24h_pct))}>{ticker?.price_24h_pct == null ? "—" : `${ticker.price_24h_pct >= 0 ? "+" : ""}${ticker.price_24h_pct.toFixed(2)}%`}</span>
        </span>
      </button>
      {removable ? (
        <button type="button" onClick={onRemove} aria-label={`Remove ${symbol} from watchlist`} className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100">
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      ) : null}
    </li>
  );
}

export function MarketsTerminal() {
  const [category, setCategory] = useState<MarketCategory>("linear");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setTf] = useState("15");
  const [watchlist, setWatchlist] = useState<string[]>(defaultWatchlist);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [showEma, setShowEma] = useState(true);
  const [, startTransition] = useTransition();

  useEffect(() => {
    setWatchlist(readList(WATCHLIST_KEY, defaultWatchlist()));
    setFavorites(readList(FAVORITES_KEY, []));
  }, []);

  const stream = useMarketStream({ category, symbol, interval, watchlist });
  const ticker = useMemo(() => stream.tickers.find((t) => t.symbol === symbol) ?? null, [stream.tickers, symbol]);
  const rsi = stream.indicators ? lastRsi(stream.indicators.rsi_14) : null;
  const lastCandle = stream.candles.length ? stream.candles[stream.candles.length - 1] : null;
  const emaLast = (arr?: Array<number | null>) => (arr && arr.length ? arr[arr.length - 1] : null);
  const ema20 = emaLast(stream.indicators?.ema_20);
  const ema50 = emaLast(stream.indicators?.ema_50);
  const ema200 = emaLast(stream.indicators?.ema_200);

  const sortedWatchlist = useMemo(() => {
    const favSet = new Set(favorites);
    const needle = query.trim().toUpperCase();
    return watchlist
      .filter((s) => !needle || s.includes(needle))
      .sort((a, b) => Number(favSet.has(b)) - Number(favSet.has(a)) || a.localeCompare(b));
  }, [watchlist, favorites, query]);

  function addSymbol() {
    const next = normalizeSymbol(query);
    if (!next) {
      setAddError("Use a USDT pair like HYPEUSDT.");
      return;
    }
    setAddError(null);
    const list = Array.from(new Set([...watchlist, next]));
    setWatchlist(list);
    writeList(WATCHLIST_KEY, list);
    startTransition(() => setSymbol(next));
    setQuery("");
  }
  function removeSymbol(s: string) {
    const list = watchlist.filter((x) => x !== s);
    setWatchlist(list);
    writeList(WATCHLIST_KEY, list);
    if (symbol === s && list[0]) startTransition(() => setSymbol(list[0]));
  }
  function toggleFavorite(s: string) {
    const list = favorites.includes(s) ? favorites.filter((x) => x !== s) : [...favorites, s];
    setFavorites(list);
    writeList(FAVORITES_KEY, list);
  }

  const modeLabel = stream.streamMode === "streaming" ? (stream.stale ? "WS stale" : "WS live") : stream.streamMode === "rest_fallback" ? "REST fallback" : stream.streamMode === "connecting" ? "Connecting" : "Disconnected";
  const connectionStatus = stream.error && stream.streamMode === "disconnected" ? "FAILED" : stream.stale ? "STALE" : stream.streamMode === "streaming" ? "RUNNING" : stream.streamMode === "rest_fallback" ? "PAUSED" : stream.streamMode === "connecting" ? "IDLE" : "STOPPED";

  const watchlistPanel = (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <form
        className="flex gap-1.5"
        onSubmit={(e) => {
          e.preventDefault();
          addSymbol();
        }}
      >
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={query} onChange={(e) => { setQuery(e.target.value); setAddError(null); }} placeholder="Search or add (e.g. HYPE)" aria-label="Search or add symbol" className="h-8 rounded-full pl-8 text-xs" />
        </div>
        <Button type="submit" size="sm" variant="outline" className="h-8 rounded-full px-2.5" aria-label="Add symbol to watchlist" disabled={!query.trim()}>
          <Plus className="h-3.5 w-3.5" aria-hidden />
        </Button>
      </form>
      {addError ? <p className="text-[11px] text-loss" role="alert">{addError}</p> : null}
      <Tabs value={category} onValueChange={(v) => startTransition(() => setCategory(v as MarketCategory))}>
        <TabsList className="h-8 w-full p-1" aria-label="Market category">
          <TabsTrigger value="linear" className="flex-1 px-2 py-1 text-xs">USDT perpetual</TabsTrigger>
          <TabsTrigger value="spot" className="flex-1 px-2 py-1 text-xs">Spot</TabsTrigger>
        </TabsList>
      </Tabs>
      <ul className="cn-thin-scroll min-h-0 flex-1 space-y-0.5 overflow-y-auto" aria-label="Watchlist">
        {sortedWatchlist.length === 0 ? <li className="px-2 py-6 text-center text-xs text-muted-foreground">No symbols match.</li> : null}
        {sortedWatchlist.map((s) => (
          <WatchlistRow key={s} symbol={s} ticker={stream.tickers.find((t) => t.symbol === s)} active={symbol === s} favorite={favorites.includes(s)} onSelect={() => startTransition(() => setSymbol(s))} onFavorite={() => toggleFavorite(s)} onRemove={() => removeSymbol(s)} removable={watchlist.length > 1} />
        ))}
      </ul>
      <p className="text-[10px] text-muted-foreground">Watchlist and favorites are saved in this browser only.</p>
    </div>
  );

  return (
    <TradingTerminalTemplate
      title="Markets"
      description="Public Bybit prices, candles, order book and tape. Read-only; there is no order entry on this screen."
      modes={["readonly"]}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <StatusIndicator status={connectionStatus} label={modeLabel} pulse />
          <StatusBadge label={stream.dataPath ? stream.dataPath.replace(/_/g, " ") : "public"} tone="neutral" />
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm" className="rounded-full lg:hidden">
                <SlidersHorizontal className="h-4 w-4" aria-hidden />
                Watchlist
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[min(100%,20rem)]">
              <SheetHeader>
                <SheetTitle>Watchlist</SheetTitle>
                <SheetDescription>Symbols, favorites and market category</SheetDescription>
              </SheetHeader>
              <div className="mt-4 h-[75vh]">{watchlistPanel}</div>
            </SheetContent>
          </Sheet>
        </div>
      }
    >
      <div className="grid min-w-0 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] xl:grid-cols-[15rem_minmax(0,1fr)_19rem]">
        <aside className="hidden min-h-0 lg:block">
          <SectionPanel title="Watchlist" className="h-full" bodyClassName="min-h-[28rem]">{watchlistPanel}</SectionPanel>
        </aside>

        <section className="min-w-0 space-y-4">
          <div className="cn-panel p-4 md:p-5">
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-muted-foreground">{category === "linear" ? "USDT perpetual" : "Spot"} · {symbol}</p>
                <div className="mt-1 flex flex-wrap items-baseline gap-3">
                  {ticker ? (
                    <FinancialValue value={ticker.last_price} digits={ticker.last_price >= 100 ? 1 : 4} unit="USDT" size="xl" />
                  ) : (
                    <Skeleton className="h-8 w-36 rounded-md" />
                  )}
                  <span className={cn("rounded-full px-2 py-0.5 font-mono text-sm", ticker?.price_24h_pct == null ? "text-muted-foreground" : ticker.price_24h_pct >= 0 ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss")}>
                    {ticker?.price_24h_pct == null ? "—" : `${ticker.price_24h_pct >= 0 ? "+" : ""}${ticker.price_24h_pct.toFixed(2)}%`}
                  </span>
                  <DataFreshness at={lastCandle ? lastCandle.time * 1000 : null} staleAfterMs={3 * (Number(interval) || 15) * 60_000} label="candle" missingLabel="No candles" />
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Tabs value={interval} onValueChange={(v) => startTransition(() => setTf(v))}>
                  <TabsList className="h-8 w-auto p-1" aria-label="Timeframe">
                    {INTERVAL_OPTIONS.map((o) => (
                      <TabsTrigger key={o.value} value={o.value} className="px-2.5 py-1 text-xs">{o.label}</TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
                <Button type="button" variant={showEma ? "secondary" : "outline"} size="sm" className="h-8 rounded-full text-xs" aria-pressed={showEma} onClick={() => setShowEma((v) => !v)}>
                  EMA overlay
                </Button>
              </div>
            </div>
            <MarketCandleChart candles={stream.candles} indicators={stream.indicators} live={stream.live} symbol={symbol} interval={interval} height={440} showEma={showEma} />
            {stream.error ? <p className="mt-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-foreground">{stream.error}</p> : null}
          </div>

          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <SectionPanel title="Technical metrics" description="Computed from confirmed candles on the client — descriptive, not a signal.">
              <dl className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ["RSI 14", rsi == null ? "—" : rsi.toFixed(2)],
                  ["EMA 20", ema20 == null ? "—" : ema20.toLocaleString(undefined, { maximumFractionDigits: 4 })],
                  ["EMA 50", ema50 == null ? "—" : ema50.toLocaleString(undefined, { maximumFractionDigits: 4 })],
                  ["EMA 200", ema200 == null ? "—" : ema200.toLocaleString(undefined, { maximumFractionDigits: 4 })],
                  ["Bars", String(stream.candles.length)],
                  ["Last volume", lastCandle ? formatCompact(lastCandle.volume) : "—"],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-border bg-muted/40 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</dt>
                    <dd className="mt-0.5 font-mono text-foreground">{v}</dd>
                  </div>
                ))}
              </dl>
              {rsi != null ? (
                <p className="mt-2 text-[11px] text-muted-foreground">{rsi >= 70 ? "RSI ≥ 70 — overbought caution (not an automatic sell)." : rsi <= 30 ? "RSI ≤ 30 — oversold caution (not an automatic buy)." : "RSI in the neutral band."}</p>
              ) : null}
            </SectionPanel>
            <SectionPanel title="Market summary" description="24h statistics from the public ticker.">
              <dl className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ["24h high", ticker?.high_24h],
                  ["24h low", ticker?.low_24h],
                  ["24h volume", ticker?.volume_24h],
                  ["24h turnover", ticker?.turnover_24h],
                  ["Mark price", ticker?.mark_price],
                  ["Funding", ticker?.funding_rate != null ? `${(ticker.funding_rate * 100).toFixed(4)}%` : null],
                ].map(([k, v]) => (
                  <div key={String(k)} className="rounded-lg border border-border bg-muted/40 px-2.5 py-2">
                    <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">{k}</dt>
                    <dd className="mt-0.5 font-mono text-foreground">{v == null ? "—" : typeof v === "number" ? (String(k).includes("volume") || String(k).includes("turnover") ? formatCompact(v) : v.toLocaleString(undefined, { maximumFractionDigits: 4 })) : v}</dd>
                  </div>
                ))}
              </dl>
            </SectionPanel>
          </div>

          <LiveAnalysisPanel symbol={symbol} category={category} interval={interval} compact title="Agent analysis" />
        </section>

        <aside className="min-w-0 space-y-4">
          <SectionPanel title="Order book" description={stream.book?.spread_bps != null ? `Spread ${stream.book.spread_bps.toFixed(2)} bps` : undefined} className="p-4">
            <OrderBookPanel book={stream.book} />
          </SectionPanel>
          <SectionPanel title="Recent trades" description="Public tape" className="p-4">
            <RecentTradesFeed trades={stream.trades} />
          </SectionPanel>
        </aside>
      </div>
    </TradingTerminalTemplate>
  );
}
