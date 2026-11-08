/** EMA / RSI from chronological closes — no look-ahead. */

export function ema(values: number[], period: number): Array<number | null> {
  if (period <= 0 || values.length === 0) return values.map(() => null);
  const out: Array<number | null> = values.map(() => null);
  if (values.length < period) return out;
  const mult = 2 / (period + 1);
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = prev;
  for (let i = period; i < values.length; i += 1) {
    prev = (values[i] - prev) * mult + prev;
    out[i] = prev;
  }
  return out;
}

export function rsi(values: number[], period = 14): Array<number | null> {
  const out: Array<number | null> = values.map(() => null);
  if (values.length <= period) return out;

  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i += 1) {
    const delta = values[i] - values[i - 1];
    if (delta >= 0) gains += delta;
    else losses -= delta;
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);

  for (let i = period + 1; i < values.length; i += 1) {
    const delta = values[i] - values[i - 1];
    const gain = Math.max(delta, 0);
    const loss = Math.max(-delta, 0);
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

export function computeOverlayIndicators(closes: number[]) {
  return {
    ema_20: ema(closes, 20),
    ema_50: ema(closes, 50),
    ema_200: ema(closes, 200),
    rsi_14: rsi(closes, 14),
  };
}
