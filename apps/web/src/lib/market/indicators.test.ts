import { describe, expect, it } from "vitest";

import { applyCandleUpdate } from "@/lib/market/candles";
import { computeOverlayIndicators, ema, rsi } from "@/lib/market/indicators";
import { OrderBookSync } from "@/lib/market/orderbook";
import { isAllowedPublicMarketPath } from "@/lib/security/public-market-proxy";

describe("market indicators", () => {
  it("computes EMA/RSI without look-ahead seed", () => {
    const closes = Array.from({ length: 40 }, (_, i) => i + 1);
    const e = ema(closes, 20);
    expect(e[18]).toBeNull();
    expect(e[19]).not.toBeNull();
    const r = rsi(closes, 14);
    expect(r[13]).toBeNull();
    expect(r[14]).not.toBeNull();
    const overlay = computeOverlayIndicators(closes);
    expect(overlay.ema_200.every((v) => v == null)).toBe(true);
  });
});

describe("candle updates", () => {
  it("rejects duplicate confirmed bars and accepts forming replace", () => {
    const a = applyCandleUpdate([], {
      time: 100,
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
      volume: 10,
      confirmed: true,
    });
    expect(a.accepted).toBe(true);
    const dup = applyCandleUpdate(a.bars, a.bars[0]);
    expect(dup.reason).toBe("duplicate");
    const forming = applyCandleUpdate(a.bars, {
      time: 200,
      open: 2,
      high: 3,
      low: 1,
      close: 2.2,
      volume: 5,
      confirmed: false,
    });
    const replaced = applyCandleUpdate(forming.bars, {
      time: 200,
      open: 2,
      high: 3.5,
      low: 1,
      close: 3,
      volume: 8,
      confirmed: false,
    });
    expect(replaced.reason).toBe("replaced_forming");
  });
});

describe("order book sync", () => {
  it("requires snapshot before delta and detects sequence gaps", () => {
    const book = new OrderBookSync("BTCUSDT", "linear");
    expect(book.applyDelta([[1, 1]], [[2, 1]], 1, 2).needsResnapshot).toBe(true);
    expect(book.applySnapshot([[100, 1]], [[101, 1]], 10, 1).ok).toBe(true);
    expect(book.applyDelta([[100, 0]], [[101, 2]], 11, 2).ok).toBe(true);
    const gap = book.applyDelta([], [], 12, 9);
    expect(gap.needsResnapshot).toBe(true);
    expect(book.view().stale).toBe(true);
  });
});

describe("public market proxy allowlist", () => {
  it("allows only public market paths", () => {
    expect(isAllowedPublicMarketPath("/api/v1/market/tickers")).toBe(true);
    expect(isAllowedPublicMarketPath("/api/v1/exchange/wallet")).toBe(false);
    expect(isAllowedPublicMarketPath("/api/v1/market/hack")).toBe(false);
  });
});
