"use client";

import type { OrderBookView } from "@/lib/market/types";
import { Badge } from "@/components/ui/badge";

const ROWS = 8;

function depthPct(size: number, max: number) {
  if (!max || !Number.isFinite(size) || size <= 0) return 0;
  return Math.max(6, Math.min(100, (size / max) * 100));
}

function takeLevels(
  levels: Array<{ price: number; size: number }>,
  count: number,
): Array<{ price: number | null; size: number | null; key: string }> {
  const out: Array<{ price: number | null; size: number | null; key: string }> = [];
  for (let i = 0; i < count; i += 1) {
    const level = levels[i];
    if (level && Number.isFinite(level.price) && Number.isFinite(level.size) && level.size > 0) {
      out.push({ price: level.price, size: level.size, key: String(level.price) });
    } else {
      out.push({ price: null, size: null, key: `empty-${i}` });
    }
  }
  return out;
}

export function OrderBookPanel({ book }: { book: OrderBookView | null }) {
  // Asks nearest the mid sit at the bottom (closest to spread); higher asks above.
  const asksNear = book?.asks.slice(0, ROWS) ?? [];
  const bidsNear = book?.bids.slice(0, ROWS) ?? [];
  const asks = takeLevels(asksNear, ROWS).reverse();
  const bids = takeLevels(bidsNear, ROWS);
  const maxAsk = Math.max(0, ...asksNear.map((a) => a.size));
  const maxBid = Math.max(0, ...bidsNear.map((b) => b.size));

  return (
    <div className="space-y-2">
      <div className="flex h-5 items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wide text-foreground">Price · Size</span>
        {!book ? (
          <Badge variant="warning" className="rounded-full">
            Waiting
          </Badge>
        ) : book.stale || !book.synced ? (
          <Badge variant="warning" className="rounded-full">
            Stale
          </Badge>
        ) : (
          <Badge variant="outline" className="rounded-full border-border">
            Synced
          </Badge>
        )}
      </div>

      {/* Fixed row count so live book updates do not resize the page. */}
      <div className="font-mono text-[11px] leading-5">
        {asks.map((a) => (
          <div key={`a-${a.key}`} className="relative grid h-5 grid-cols-[1fr_auto] gap-x-3">
            {a.size != null ? (
              <span
                aria-hidden
                className="absolute inset-y-0 right-0 rounded-sm bg-rose-500/15"
                style={{ width: `${depthPct(a.size, maxAsk)}%` }}
              />
            ) : null}
            <span className="relative text-rose-400 tabular-nums">
              {a.price != null
                ? a.price.toLocaleString(undefined, { maximumFractionDigits: 4 })
                : "—"}
            </span>
            <span className="relative text-right text-foreground tabular-nums">
              {a.size != null
                ? a.size.toLocaleString(undefined, { maximumFractionDigits: 4 })
                : "—"}
            </span>
          </div>
        ))}

        <div className="my-1.5 flex h-8 items-center justify-center rounded-xl border border-border bg-muted/70 px-2 text-[11px]">
          {book?.best_bid != null && book?.best_ask != null ? (
            <span className="text-foreground">
              Spread{" "}
              <span className="text-foreground tabular-nums">
                {book.spread?.toPrecision(4)}
                {book.spread_bps != null ? ` · ${book.spread_bps.toFixed(1)} bps` : ""}
              </span>
            </span>
          ) : (
            <span className="text-foreground">Spread —</span>
          )}
        </div>

        {bids.map((b) => (
          <div key={`b-${b.key}`} className="relative grid h-5 grid-cols-[1fr_auto] gap-x-3">
            {b.size != null ? (
              <span
                aria-hidden
                className="absolute inset-y-0 right-0 rounded-sm bg-emerald-500/15"
                style={{ width: `${depthPct(b.size, maxBid)}%` }}
              />
            ) : null}
            <span className="relative text-emerald-400 tabular-nums">
              {b.price != null
                ? b.price.toLocaleString(undefined, { maximumFractionDigits: 4 })
                : "—"}
            </span>
            <span className="relative text-right text-foreground tabular-nums">
              {b.size != null
                ? b.size.toLocaleString(undefined, { maximumFractionDigits: 4 })
                : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
