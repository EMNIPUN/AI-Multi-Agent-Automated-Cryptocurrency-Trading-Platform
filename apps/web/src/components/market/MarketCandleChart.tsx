"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

import type { MarketCandle, MarketIndicators } from "@/lib/market/types";

type SeriesBag = {
  candle: ISeriesApi<"Candlestick">;
  volume: ISeriesApi<"Histogram">;
  ema20: ISeriesApi<"Line">;
  ema50: ISeriesApi<"Line">;
  ema200: ISeriesApi<"Line">;
};

function mapCandle(c: MarketCandle) {
  return {
    time: c.time as Time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

function mapVolume(c: MarketCandle, isLight: boolean) {
  return {
    time: c.time as Time,
    value: c.volume,
    color:
      c.close >= c.open
        ? isLight
          ? "rgba(15,118,110,0.35)"
          : "rgba(16,185,129,0.35)"
        : isLight
          ? "rgba(220,38,38,0.35)"
          : "rgba(239,68,68,0.35)",
  };
}

function mapEma(candles: MarketCandle[], arr: Array<number | null>) {
  return candles
    .map((c, i) =>
      arr[i] == null ? null : { time: c.time as Time, value: arr[i] as number },
    )
    .filter((x): x is { time: Time; value: number } => x != null);
}

export function MarketCandleChart({
  candles,
  indicators,
  live,
  symbol,
  interval,
}: {
  candles: MarketCandle[];
  indicators?: MarketIndicators | null;
  live: boolean;
  symbol: string;
  interval: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<SeriesBag | null>(null);
  const lastLenRef = useRef(0);
  const lastTimeRef = useRef<number | null>(null);
  const seriesKeyRef = useRef(`${symbol}:${interval}`);
  const isLightRef = useRef(false);

  // Create chart once.
  useEffect(() => {
    if (!ref.current) return;
    const isLight = document.documentElement.classList.contains("light");
    isLightRef.current = isLight;
    const chart = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: isLight ? "#475569" : "#94a3b8",
        fontFamily: "IBM Plex Mono, monospace",
      },
      grid: {
        vertLines: { color: isLight ? "rgba(148,163,184,0.35)" : "rgba(51,65,85,0.45)" },
        horzLines: { color: isLight ? "rgba(148,163,184,0.35)" : "rgba(51,65,85,0.45)" },
      },
      rightPriceScale: {
        borderVisible: false,
        // Keep margins so live wick updates do not yank the whole pane up/down.
        scaleMargins: { top: 0.12, bottom: 0.18 },
        entireTextOnly: true,
      },
      timeScale: {
        borderVisible: false,
        rightOffset: 4,
        lockVisibleTimeRangeOnResize: true,
      },
      handleScroll: { vertTouchDrag: false },
      width: ref.current.clientWidth,
      height: 420,
    });
    chartRef.current = chart;

    const candle = chart.addCandlestickSeries({
      upColor: isLight ? "#0f766e" : "#10b981",
      downColor: isLight ? "#dc2626" : "#ef4444",
      borderVisible: false,
      wickUpColor: isLight ? "#0f766e" : "#10b981",
      wickDownColor: isLight ? "#dc2626" : "#ef4444",
      lastValueVisible: true,
      priceLineVisible: true,
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    const lineOpts = {
      lineWidth: 1 as const,
      priceLineVisible: false,
      lastValueVisible: false,
    };
    const ema20 = chart.addLineSeries({ color: "#F7A600", ...lineOpts });
    const ema50 = chart.addLineSeries({ color: "#a78bfa", ...lineOpts });
    const ema200 = chart.addLineSeries({ color: "#fbbf24", ...lineOpts });
    seriesRef.current = { candle, volume, ema20, ema50, ema200 };

    const onResize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lastLenRef.current = 0;
      lastTimeRef.current = null;
    };
  }, []);

  // Incremental candle / indicator updates — never fitContent on live ticks.
  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;
    const isLight = isLightRef.current;
    const seriesKey = `${symbol}:${interval}`;
    const symbolChanged = seriesKeyRef.current !== seriesKey;
    if (symbolChanged) {
      seriesKeyRef.current = seriesKey;
      lastLenRef.current = 0;
      lastTimeRef.current = null;
    }

    if (candles.length === 0) {
      series.candle.setData([]);
      series.volume.setData([]);
      series.ema20.setData([]);
      series.ema50.setData([]);
      series.ema200.setData([]);
      lastLenRef.current = 0;
      lastTimeRef.current = null;
      return;
    }

    const last = candles[candles.length - 1];
    const prevLen = lastLenRef.current;
    const prevTime = lastTimeRef.current;

    const needsFullReplace =
      symbolChanged ||
      prevLen === 0 ||
      candles.length + 5 < prevLen ||
      (prevTime != null && last.time < prevTime);

    if (needsFullReplace) {
      series.candle.setData(candles.map(mapCandle));
      series.volume.setData(candles.map((c) => mapVolume(c, isLight)));
      // Fit only on first paint / symbol-interval change — not on every REST refresh.
      chart.timeScale().fitContent();
    } else if (prevTime === last.time) {
      series.candle.update(mapCandle(last));
      series.volume.update(mapVolume(last, isLight));
    } else if (prevTime != null && last.time > prevTime) {
      const start = Math.max(0, prevLen - 1);
      for (let i = start; i < candles.length; i += 1) {
        series.candle.update(mapCandle(candles[i]));
        series.volume.update(mapVolume(candles[i], isLight));
      }
    } else {
      // Same-length REST reseed: replace data quietly without zoom jumping.
      series.candle.setData(candles.map(mapCandle));
      series.volume.setData(candles.map((c) => mapVolume(c, isLight)));
    }

    if (indicators) {
      series.ema20.setData(mapEma(candles, indicators.ema_20));
      series.ema50.setData(mapEma(candles, indicators.ema_50));
      series.ema200.setData(mapEma(candles, indicators.ema_200));
    }

    lastLenRef.current = candles.length;
    lastTimeRef.current = last.time;
  }, [candles, indicators, symbol, interval]);

  return (
    <div
      className="relative h-[420px] w-full shrink-0 overflow-hidden rounded-lg border border-border/60 bg-card/40"
      role="img"
      aria-label={live ? "Live public market candle chart" : "Market candle chart"}
    >
      <div className="absolute right-2 top-2 z-10 rounded border border-border/50 bg-background/80 px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
        {live ? (
          <span className="text-emerald-400">PUBLIC WS LIVE</span>
        ) : (
          <span className="text-amber-400">REST / STALE</span>
        )}
      </div>
      {candles.length === 0 ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-muted-foreground">
          Waiting for public market candles…
        </div>
      ) : null}
      <div ref={ref} className="h-full w-full" />
      <p className="absolute bottom-1 left-2 font-mono text-[9px] text-muted-foreground/80">
        EMA20 · EMA50 · EMA200 · volume
      </p>
    </div>
  );
}
