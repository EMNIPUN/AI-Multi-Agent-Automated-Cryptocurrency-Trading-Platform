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
}: {
  candles: CandleBar[];
  markers: SignalMarker[];
  sample: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

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

    const series: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: isLight ? "#0f766e" : "#10b981",
      downColor: isLight ? "#dc2626" : "#ef4444",
      borderVisible: false,
      wickUpColor: isLight ? "#0f766e" : "#10b981",
      wickDownColor: isLight ? "#dc2626" : "#ef4444",
    });

    series.setData(
      candles.map((c) => ({
        time: c.time as Time,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );

    const seriesMarkers: SeriesMarker<Time>[] = markers.map((m) => ({
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
    };
  }, [candles, markers, sample]);

  return (
    <div className="relative h-[320px] w-full overflow-hidden rounded-lg border border-border/60 bg-card/40">
      {sample ? (
        <div className="absolute right-2 top-2 z-10 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] text-amber-400">
          SAMPLE CHART
        </div>
      ) : null}
      <div ref={ref} className="h-full w-full" />
    </div>
  );
}
