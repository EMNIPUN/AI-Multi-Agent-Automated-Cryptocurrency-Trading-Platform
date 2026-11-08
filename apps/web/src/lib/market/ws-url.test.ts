import { describe, expect, it } from "vitest";

import { applyCandleUpdate } from "@/lib/market/candles";
import { computeOverlayIndicators } from "@/lib/market/indicators";
import { marketStreamWsUrl } from "@/lib/market/ws-url";

describe("market stream url", () => {
  it("defaults to local FastAPI public stream (no arbitrary upstream)", () => {
    expect(marketStreamWsUrl()).toBe("ws://127.0.0.1:8000/api/v1/market/stream");
    expect(marketStreamWsUrl()).not.toContain("bybit.com");
  });
});

describe("streaming candle + indicator consistency", () => {
  it("does not let forming bar rewrite confirmed history for indicators seed", () => {
    let bars = applyCandleUpdate([], {
      time: 100,
      open: 1,
      high: 2,
      low: 0.5,
      close: 1.5,
      volume: 1,
      confirmed: true,
    }).bars;
    bars = applyCandleUpdate(bars, {
      time: 200,
      open: 1.5,
      high: 2,
      low: 1,
      close: 1.8,
      volume: 1,
      confirmed: false,
    }).bars;
    const confirmed = bars.filter((b) => b.confirmed !== false);
    const ind = computeOverlayIndicators(confirmed.map((c) => c.close));
    expect(confirmed).toHaveLength(1);
    expect(ind.ema_20).toHaveLength(1);
  });
});
