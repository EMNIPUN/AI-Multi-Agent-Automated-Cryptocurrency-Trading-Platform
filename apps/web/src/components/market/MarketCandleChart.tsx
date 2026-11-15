"use client";

import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";

import type { MarketCandle, MarketIndicators } from "@/lib/market/types";
import { intervalLabel } from "@/lib/formatting/time";

type SeriesBag = {
  candle: ISeriesApi<"Candlestick">;
  volume: ISeriesApi<"Histogram">;
  ema20: ISeriesApi<"Line">;
  ema50: ISeriesApi<"Line">;
  ema200: ISeriesApi<"Line">;
};

type Palette = ReturnType<typeof palette>;

/** Chart colours mirror the Obsidian Amber tokens for each theme. */
function palette(isLight: boolean) {
  return {
    text: isLight ? "#526175" : "#A5AFBD",
    grid: isLight ? "rgba(217,224,234,0.9)" : "rgba(40,49,61,0.9)",
    up: isLight ? "#087A54" : "#20C997",
    down: isLight ? "#B4233D" : "#EF6674",
    upVol: isLight ? "rgba(8,122,84,0.35)" : "rgba(32,201,151,0.35)",
    downVol: isLight ? "rgba(180,35,61,0.35)" : "rgba(239,102,116,0.35)",
    ema20: "#F7A600",
    ema50: isLight ? "#225DB6" : "#63A7FF",
    ema200: isLight ? "#526175" : "#A5AFBD",
    crosshair: isLight ? "rgba(82,97,117,0.8)" : "rgba(165,175,189,0.8)",
  };
}

function mapCandle(c: MarketCandle) {
  return { time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close };
}

function mapVolume(c: MarketCandle, p: Palette) {
  return { time: c.time as Time, value: c.volume, color: c.close >= c.open ? p.upVol : p.downVol };
}

function mapEma(candles: MarketCandle[], arr: Array<number | null>) {
  return candles
    .map((c, i) => (arr[i] == null ? null : { time: c.time as Time, value: arr[i] as number }))
    .filter((x): x is { time: Time; value: number } => x != null);
}

function priceFormat(candles: MarketCandle[]) {
  const last = candles.length ? candles[candles.length - 1].close : 0;
  const precision = last >= 1000 ? 1 : last >= 100 ? 2 : last >= 1 ? 4 : 6;
  return { type: "price" as const, precision, minMove: Number((1 / 10 ** precision).toFixed(precision)) };
}

export function MarketCandleChart({
  candles,
  indicators,
  live,
  symbol,
  interval,
  height = 420,
  showEma = true,
}: {
  candles: MarketCandle[];
  indicators?: MarketIndicators | null;
  live: boolean;
  symbol: string;
  interval: string;
  height?: number;
  showEma?: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<SeriesBag | null>(null);
  const lastLenRef = useRef(0);
  const lastTimeRef = useRef<number | null>(null);
  const seriesKeyRef = useRef(`${symbol}:${interval}`);
  const [isLight, setIsLight] = useState(false);
  const paletteRef = useRef(palette(false));

  // Follow the theme class on <html> so the chart repaints when the user toggles.
  useEffect(() => {
    const root = document.documentElement;
    const read = () => setIsLight(root.classList.contains("light"));
    read();
    const obs = new MutationObserver(read);
    obs.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  // Create chart once; size follows the container via ResizeObserver.
  useEffect(() => {
    if (!ref.current) return;
    const p = paletteRef.current;
    const chart = createChart(ref.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: p.text, fontFamily: "IBM Plex Mono, ui-monospace, monospace", fontSize: 11 },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      crosshair: { vertLine: { color: p.crosshair, labelBackgroundColor: p.crosshair }, horzLine: { color: p.crosshair, labelBackgroundColor: p.crosshair } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.1, bottom: 0.2 }, entireTextOnly: true },
      timeScale: { borderVisible: false, rightOffset: 4, lockVisibleTimeRangeOnResize: true, timeVisible: true, secondsVisible: false },
      handleScroll: { vertTouchDrag: false },
      width: ref.current.clientWidth,
      height: ref.current.clientHeight || height,
    });
    chartRef.current = chart;

    const candle = chart.addCandlestickSeries({ upColor: p.up, downColor: p.down, borderVisible: false, wickUpColor: p.up, wickDownColor: p.down, lastValueVisible: true, priceLineVisible: true });
    const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const lineOpts = { lineWidth: 1 as const, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    const ema20 = chart.addLineSeries({ color: p.ema20, ...lineOpts });
    const ema50 = chart.addLineSeries({ color: p.ema50, ...lineOpts });
    const ema200 = chart.addLineSeries({ color: p.ema200, ...lineOpts });
    seriesRef.current = { candle, volume, ema20, ema50, ema200 };

    const el = ref.current;
    const ro = new ResizeObserver(() => {
      if (!el) return;
      chart.applyOptions({ width: el.clientWidth, height: el.clientHeight || height });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lastLenRef.current = 0;
      lastTimeRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Theme repaint without recreating the chart.
  useEffect(() => {
    const p = palette(isLight);
    paletteRef.current = p;
    const chart = chartRef.current;
    const s = seriesRef.current;
    if (!chart || !s) return;
    chart.applyOptions({
      layout: { textColor: p.text },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      crosshair: { vertLine: { color: p.crosshair, labelBackgroundColor: p.crosshair }, horzLine: { color: p.crosshair, labelBackgroundColor: p.crosshair } },
    });
    s.candle.applyOptions({ upColor: p.up, downColor: p.down, wickUpColor: p.up, wickDownColor: p.down });
    s.ema50.applyOptions({ color: p.ema50 });
    s.ema200.applyOptions({ color: p.ema200 });
    if (candles.length) s.volume.setData(candles.map((c) => mapVolume(c, p)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLight]);

  useEffect(() => {
    const s = seriesRef.current;
    if (!s) return;
    s.ema20.applyOptions({ visible: showEma });
    s.ema50.applyOptions({ visible: showEma });
    s.ema200.applyOptions({ visible: showEma });
  }, [showEma]);

  // Incremental candle / indicator updates — never fitContent on live ticks.
  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;
    const p = paletteRef.current;
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
    const needsFullReplace = symbolChanged || prevLen === 0 || candles.length + 5 < prevLen || (prevTime != null && last.time < prevTime);

    if (needsFullReplace) {
      series.candle.applyOptions({ priceFormat: priceFormat(candles) });
      series.candle.setData(candles.map(mapCandle));
      series.volume.setData(candles.map((c) => mapVolume(c, p)));
      chart.timeScale().fitContent();
    } else if (prevTime === last.time) {
      series.candle.update(mapCandle(last));
      series.volume.update(mapVolume(last, p));
    } else if (prevTime != null && last.time > prevTime) {
      const start = Math.max(0, prevLen - 1);
      for (let i = start; i < candles.length; i += 1) {
        series.candle.update(mapCandle(candles[i]));
        series.volume.update(mapVolume(candles[i], p));
      }
    } else {
      series.candle.setData(candles.map(mapCandle));
      series.volume.setData(candles.map((c) => mapVolume(c, p)));
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
      className="relative w-full shrink-0 overflow-hidden rounded-lg border border-border/60 bg-card/40"
      style={{ height }}
      role="img"
      aria-label={`${symbol} ${intervalLabel(interval)} candle chart${live ? ", streaming" : ", stream stale"}`}
    >
      <div className="absolute right-2 top-2 z-10 rounded border border-border/50 bg-background/80 px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
        {live ? <span className="text-profit">Stream connected</span> : <span className="text-warning">Stream stale</span>}
      </div>
      {candles.length === 0 ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-muted-foreground">
          Waiting for public market candles…
        </div>
      ) : null}
      <div ref={ref} className="h-full w-full" />
      {showEma ? (
        <p className="pointer-events-none absolute bottom-1 left-2 flex gap-2 font-mono text-[9px] text-muted-foreground/90">
          <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-[#F7A600]" aria-hidden /> EMA20</span>
          <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-info" aria-hidden /> EMA50</span>
          <span><span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground" aria-hidden /> EMA200</span>
          <span>· volume</span>
        </p>
      ) : null}
    </div>
  );
}
