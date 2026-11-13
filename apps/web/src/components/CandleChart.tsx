"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

import type { CandleBar, SignalMarker } from "@/lib/observability/types";

/**
 * TradingView Lightweight Charts with Bybit-shaped OHLCV (unix seconds).
 * No paid TradingView MCP dependency.
 */
export function CandleChart({
  candles,
  markers,
  sample,
  focusTime,
}: {
  candles: CandleBar[];
  markers: SignalMarker[];
  sample: boolean;
  focusTime?: number | null;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const isLight = document.documentElement.classList.contains("light");
    const chart: IChartApi = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: isLight ? "#475569" : "#94a3b8",
        fontFamily: "IBM Plex Mono, monospace",
      },
      grid: {
        vertLines: { color: isLight ? "rgba(148,163,184,0.35)" : "rgba(51,65,85,0.45)" },
        horzLines: { color: isLight ? "rgba(148,163,184,0.35)" : "rgba(51,65,85,0.45)" },
      },
      rightPriceScale: { borderColor: isLight ? "rgba(148,163,184,0.7)" : "rgba(51,65,85,0.8)" },
      timeScale: { borderColor: isLight ? "rgba(148,163,184,0.7)" : "rgba(51,65,85,0.8)" },
      width: ref.current.clientWidth,
      height: 320,
    });
    chartRef.current = chart;

    const series: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: isLight ? "#0f766e" : "#10b981",
      downColor: isLight ? "#dc2626" : "#ef4444",
      borderVisible: false,
      wickUpColor: isLight ? "#0f766e" : "#10b981",
      wickDownColor: isLight ? "#dc2626" : "#ef4444",
    });

    if (candles.length > 0) {
      series.setData(
        candles.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        })),
      );
    }

    const verified = new Set(candles.map((c) => c.time));
    const seriesMarkers: SeriesMarker<Time>[] = markers
      .filter((m) => verified.has(m.time))
      .map((m) => ({
        time: m.time as Time,
        position: m.action === "SELL" ? "aboveBar" : "belowBar",
        color:
          m.action === "BUY" ? "#0f7a5f" : m.action === "SELL" ? "#b42318" : "#b45309",
        shape:
          m.action === "BUY" ? "arrowUp" : m.action === "SELL" ? "arrowDown" : "circle",
        text: sample || m.sample ? `SAMPLE ${m.action}` : m.label || m.action,
      }));
    series.setMarkers(seriesMarkers);
    chart.timeScale().fitContent();

    const onResize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, markers, sample]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || focusTime == null || candles.length === 0) return;
    const span = Math.max(8, Math.floor(candles.length / 6));
    chart.timeScale().setVisibleRange({
      from: (focusTime - span * 900) as Time,
      to: (focusTime + span * 900) as Time,
    });
  }, [focusTime, candles.length]);

  return (
    <div
      className="relative h-[320px] w-full overflow-hidden rounded-lg border border-border/60 bg-card/40"
      role="img"
      aria-label={
        candles.length === 0
          ? "Candle chart unavailable"
          : sample
            ? "Sample candle chart"
            : "Worker evidence candle chart"
      }
    >
      {sample ? (
        <div className="absolute right-2 top-2 z-10 rounded border border-warning/40 bg-warning/10 px-2 py-0.5 font-mono text-[10px] text-warning">
          SAMPLE CHART
        </div>
      ) : null}
      {candles.length === 0 ? (
        <div className="flex h-full items-center justify-center px-4 text-center text-sm text-muted-foreground">
          Candle series unavailable in this snapshot. Markers are not invented without verified bars.
        </div>
      ) : (
        <div ref={ref} className="h-full w-full" />
      )}
      <p className="absolute bottom-1 left-2 font-mono text-[9px] text-muted-foreground/80">
        Charting by TradingView Lightweight Charts
      </p>
    </div>
  );
}
