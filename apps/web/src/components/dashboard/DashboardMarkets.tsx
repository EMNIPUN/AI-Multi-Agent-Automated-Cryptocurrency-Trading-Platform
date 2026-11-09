"use client";

import Link from "next/link";
import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";

import { BorderBeam } from "@/components/magicui/border-beam";
import { Button } from "@/components/ui/button";
import { fetchTickers } from "@/lib/market/api";
import { DEFAULT_WATCHLIST, type MarketTicker } from "@/lib/market/types";
import { cn } from "@/lib/utils";

/** Friendly market cards for the simplified dashboard. */
export function DashboardMarkets() {
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
        if (!cancelled) setError("offline");
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
    <div className="relative h-full overflow-hidden rounded-3xl border border-border/70 bg-card/60 p-5 md:p-6">
      <BorderBeam size={160} duration={11} colorFrom="#F7A600" colorTo="#FFCE6E" />
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl tracking-tight">Live markets</h2>
          <p className="text-sm text-muted-foreground">Public prices · updates every few seconds</p>
        </div>
        <Button asChild variant="outline" size="sm" className="rounded-full">
          <Link href="/markets">
            Charts
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>

      {error ? (
        <p className="rounded-2xl border border-border/60 bg-background/40 px-4 py-6 text-sm text-muted-foreground">
          Market feed is offline. Start the API to see live prices — we never invent numbers.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          {DEFAULT_WATCHLIST.map((sym) => {
            const t = tickers.find((x) => x.symbol === sym);
            const pct = t?.price_24h_pct;
            const up = pct != null && pct >= 0;
            return (
              <div
                key={sym}
                className="rounded-2xl border border-border/60 bg-background/50 p-4 transition-colors hover:border-border"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    {sym.replace("USDT", "")}
                    <span className="text-muted-foreground/60">/USDT</span>
                  </p>
                  {pct == null ? null : up ? (
                    <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
                  ) : (
                    <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
                  )}
                </div>
                <p className="mt-2 font-mono text-xl tracking-tight">
                  {t
                    ? t.last_price.toLocaleString(undefined, { maximumFractionDigits: 2 })
                    : "—"}
                </p>
                <p
                  className={cn(
                    "mt-1 text-xs font-medium",
                    pct == null
                      ? "text-muted-foreground"
                      : up
                        ? "text-emerald-400"
                        : "text-rose-400",
                  )}
                >
                  {pct == null ? "Waiting…" : `${up ? "+" : ""}${pct.toFixed(2)}% today`}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
