import type { OrderBookLevel, OrderBookView } from "@/lib/market/types";

export type SyncResult = {
  ok: boolean;
  reason: string;
  needsResnapshot?: boolean;
};

export class OrderBookSync {
  bids = new Map<number, number>();
  asks = new Map<number, number>();
  updateId: number | null = null;
  sequence: number | null = null;
  synced = false;
  stale = false;

  constructor(
    public symbol: string,
    public category: "spot" | "linear",
    public depth = 50,
  ) {}

  applySnapshot(
    bids: Array<[number, number]>,
    asks: Array<[number, number]>,
    updateId?: number | null,
    sequence?: number | null,
  ): SyncResult {
    this.bids = new Map(bids.filter(([, s]) => s > 0));
    this.asks = new Map(asks.filter(([, s]) => s > 0));
    this.updateId = updateId ?? null;
    this.sequence = sequence ?? null;
    this.synced = true;
    this.stale = false;
    this.trim();
    return { ok: true, reason: "snapshot" };
  }

  applyDelta(
    bids: Array<[number, number]>,
    asks: Array<[number, number]>,
    updateId?: number | null,
    sequence?: number | null,
  ): SyncResult {
    if (!this.synced) return { ok: false, reason: "no_snapshot", needsResnapshot: true };
    if (sequence != null && this.sequence != null) {
      if (sequence <= this.sequence) return { ok: false, reason: "duplicate_or_old_sequence" };
      if (sequence > this.sequence + 1) {
        this.synced = false;
        this.stale = true;
        return { ok: false, reason: "sequence_gap", needsResnapshot: true };
      }
    }
    for (const [p, s] of bids) {
      if (s <= 0) this.bids.delete(p);
      else this.bids.set(p, s);
    }
    for (const [p, s] of asks) {
      if (s <= 0) this.asks.delete(p);
      else this.asks.set(p, s);
    }
    if (updateId != null) this.updateId = updateId;
    if (sequence != null) this.sequence = sequence;
    this.trim();
    return { ok: true, reason: "delta" };
  }

  view(): OrderBookView {
    const bids: OrderBookLevel[] = [...this.bids.entries()]
      .sort((a, b) => b[0] - a[0])
      .map(([price, size]) => ({ price, size }));
    const asks: OrderBookLevel[] = [...this.asks.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([price, size]) => ({ price, size }));
    const best_bid = bids[0]?.price ?? null;
    const best_ask = asks[0]?.price ?? null;
    let spread: number | null = null;
    let spread_bps: number | null = null;
    if (best_bid != null && best_ask != null) {
      spread = best_ask - best_bid;
      const mid = (best_ask + best_bid) / 2;
      if (mid > 0) spread_bps = (spread / mid) * 10_000;
    }
    return {
      symbol: this.symbol,
      category: this.category,
      bids,
      asks,
      best_bid,
      best_ask,
      spread,
      spread_bps,
      synced: this.synced && !this.stale,
      stale: this.stale || !this.synced,
    };
  }

  private trim() {
    if (this.bids.size > this.depth) {
      const keep = [...this.bids.entries()].sort((a, b) => b[0] - a[0]).slice(0, this.depth);
      this.bids = new Map(keep);
    }
    if (this.asks.size > this.depth) {
      const keep = [...this.asks.entries()].sort((a, b) => a[0] - b[0]).slice(0, this.depth);
      this.asks = new Map(keep);
    }
  }
}
