"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { fetchTickers } from "@/lib/market/api";
import { DEFAULT_WATCHLIST, type MarketTicker } from "@/lib/market/types";

/** Compact public price strip for dashboard — not private account connectivity. */
export function PublicTickerStrip() {
  const [tickers, setTickers] = useState<MarketTicker[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetchTickers("linear", [...DEFAULT_WATCHLIST]);
        if (!cancelled) {
          setTickers(res.tickers);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("public_market_unavailable");
      }
    };
    void load();
    const id = setInterval(() => void load(), 8_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="mb-4 rounded-2xl border border-white/10 bg-card/50 px-3 py-2.5 shadow-[0_0_40px_-24px_rgba(245,158,11,0.25)]">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="rounded-full border-white/20 text-white/90">
          PUBLIC MARKET
        </Badge>
        <span className="text-xs text-muted-foreground">
          Live public quotes — separate from private wallet / trading
        </span>
      </div>
      {error ? (
        <p className="text-xs text-muted-foreground">
          Public market feed offline (start FastAPI). Not SAMPLE-invented prices.
        </p>
      ) : (
        <div className="flex flex-wrap gap-4 font-mono text-sm">
          {DEFAULT_WATCHLIST.map((sym) => {
            const t = tickers.find((x) => x.symbol === sym);
            const pct = t?.price_24h_pct;
            return (
              <div key={sym} className="min-w-[7rem]">
                <div className="text-[10px] text-muted-foreground">{sym}</div>
                <div>
                  {t
                    ? t.last_price.toLocaleString(undefined, { maximumFractionDigits: 4 })
                    : "—"}
                </div>
                <div
                  className={`text-[10px] ${
                    pct == null ? "text-muted-foreground" : pct >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {pct == null ? "—" : `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
