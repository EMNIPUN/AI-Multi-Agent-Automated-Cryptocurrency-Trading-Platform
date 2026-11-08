import type { MarketCandle } from "@/lib/market/types";

export type CandleApplyReason =
  | "appended"
  | "duplicate"
  | "replaced_forming"
  | "inserted_historical"
  | "immutable_confirmed"
  | "invalid_time";

export function applyCandleUpdate(
  bars: MarketCandle[],
  candle: MarketCandle,
  maxBars = 1000,
): { bars: MarketCandle[]; accepted: boolean; reason: CandleApplyReason } {
  if (!candle.time || candle.time <= 0) {
    return { bars, accepted: false, reason: "invalid_time" };
  }
  const idx = bars.findIndex((b) => b.time === candle.time);
  if (idx >= 0) {
    const existing = bars[idx];
    if (existing.confirmed) {
      const same =
        existing.open === candle.open &&
        existing.high === candle.high &&
        existing.low === candle.low &&
        existing.close === candle.close &&
        existing.volume === candle.volume;
      return { bars, accepted: false, reason: same ? "duplicate" : "immutable_confirmed" };
    }
    const next = bars.slice();
    next[idx] = candle;
    return { bars: next, accepted: true, reason: "replaced_forming" };
  }
  const next = bars.concat(candle).sort((a, b) => a.time - b.time);
  const trimmed = next.length > maxBars ? next.slice(next.length - maxBars) : next;
  const reason: CandleApplyReason =
    bars.length > 0 && candle.time < bars[bars.length - 1].time
      ? "inserted_historical"
      : "appended";
  return { bars: trimmed, accepted: true, reason };
}

export function lastRsi(values: Array<number | null>): number | null {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    if (values[i] != null) return values[i];
  }
  return null;
}
