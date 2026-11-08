"use client";

import { AnimatedList } from "@/components/magicui/animated-list";
import type { PublicTradeView } from "@/lib/market/types";
import { cn } from "@/lib/utils";

/** Magic UI animated feed for recent public trades. */
export function RecentTradesFeed({ trades }: { trades: PublicTradeView[] }) {
  const rows = trades.slice(0, 16);

  if (rows.length === 0) {
    return (
      <p className="rounded-2xl border border-dashed border-white/10 px-3 py-10 text-center text-sm text-white/45">
        Waiting for live trades…
      </p>
    );
  }

  return (
    <div className="max-h-[22rem] overflow-hidden">
      <AnimatedList delay={0} className="gap-1.5">
        {rows.map((t) => (
          <div
            key={`${t.trade_id}-${t.timestamp_ms}-${t.price}`}
            className="grid grid-cols-[3.25rem_1fr_1fr] items-center rounded-xl border border-white/5 bg-black/35 px-2.5 py-1.5 font-mono text-[11px]"
          >
            <span
              className={cn(
                t.side === "Buy"
                  ? "text-emerald-400"
                  : t.side === "Sell"
                    ? "text-rose-400"
                    : "text-white/45",
              )}
            >
              {t.side === "Unknown" ? "—" : t.side}
            </span>
            <span className="text-white/90">
              {t.price.toLocaleString(undefined, { maximumFractionDigits: 4 })}
            </span>
            <span className="text-right text-white/45">
              {t.size.toLocaleString(undefined, { maximumFractionDigits: 4 })}
            </span>
          </div>
        ))}
      </AnimatedList>
    </div>
  );
}
