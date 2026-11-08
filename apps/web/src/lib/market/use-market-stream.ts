"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchKlines,
  fetchOrderBook,
  fetchTickers,
  fetchTrades,
} from "@/lib/market/api";
import { applyCandleUpdate } from "@/lib/market/candles";
import { computeOverlayIndicators } from "@/lib/market/indicators";
import { marketStreamWsUrl } from "@/lib/market/ws-url";
import type {
  MarketCandle,
  MarketCategory,
  MarketConnectionState,
  MarketIndicators,
  MarketTicker,
  OrderBookView,
  PublicTradeView,
} from "@/lib/market/types";

export type StreamMode = "connecting" | "streaming" | "rest_fallback" | "disconnected";

type Options = {
  category: MarketCategory;
  symbol: string;
  interval: string;
  watchlist: readonly string[];
};

const REST_FALLBACK_MS = 8_000;
const RECONNECT_BASE_MS = 800;
const RECONNECT_MAX_MS = 20_000;
const REST_SEED_MIN_MS = 3_000;
const BOOK_RESYNC_MIN_MS = 8_000;

/** Ignore collapsed WS books that would flash empty rows (delta-as-snapshot artifact). */
function preferStableOrderBook(
  prev: OrderBookView | null,
  next: OrderBookView,
): OrderBookView {
  if (!prev) return next;
  const prevCount = prev.bids.length + prev.asks.length;
  const nextCount = next.bids.length + next.asks.length;
  if (prev.synced && next.synced && prevCount >= 8 && nextCount > 0 && nextCount < 4) {
    return prev;
  }
  return next;
}

export function useMarketStream(opts: Options) {
  const [candles, setCandles] = useState<MarketCandle[]>([]);
  const [indicators, setIndicators] = useState<MarketIndicators | null>(null);
  const [tickers, setTickers] = useState<MarketTicker[]>([]);
  const [book, setBook] = useState<OrderBookView | null>(null);
  const [trades, setTrades] = useState<PublicTradeView[]>([]);
  const [connectionState, setConnectionState] =
    useState<MarketConnectionState>("disconnected");
  const [streamMode, setStreamMode] = useState<StreamMode>("disconnected");
  const [stale, setStale] = useState(false);
  const [dataPath, setDataPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const aliveRef = useRef(true);
  const attemptRef = useRef(0);
  const restTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastBookResyncRef = useRef(0);
  const lastRestSeedRef = useRef(0);
  const lastBumpRef = useRef(0);
  const skipOptsEffectRef = useRef(true);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const bumpUpdated = () => {
    const now = Date.now();
    // Throttle clock label so live ticks do not thrash the whole page.
    if (now - lastBumpRef.current < 1_000) return;
    lastBumpRef.current = now;
    setUpdatedAt(new Date().toLocaleTimeString());
  };

  const recomputeIndicators = useCallback((bars: MarketCandle[]) => {
    const forInd = bars.filter((b) => b.confirmed !== false);
    const series = forInd.length > 0 ? forInd : bars;
    const closes = series.map((c) => c.close);
    setIndicators(computeOverlayIndicators(closes));
  }, []);

  const loadRestSnapshot = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastRestSeedRef.current < REST_SEED_MIN_MS) {
      return true;
    }
    lastRestSeedRef.current = now;
    const { category, symbol, interval, watchlist } = optsRef.current;
    try {
      const [tk, kl, ob, tr] = await Promise.all([
        fetchTickers(category, [...watchlist]),
        fetchKlines(category, symbol, interval, 200),
        fetchOrderBook(category, symbol, 50),
        fetchTrades(category, symbol, 25),
      ]);
      if (!aliveRef.current) return false;
      setTickers(tk.tickers);
      setCandles(kl.candles);
      setIndicators(kl.indicators);
      setBook(ob);
      setTrades(tr.trades);
      setDataPath(kl.data_path || tk.data_path || "public_rest_only");
      setError(null);
      bumpUpdated();
      return true;
    } catch (err) {
      if (!aliveRef.current) return false;
      setError(err instanceof Error ? err.message : "rest_fallback_failed");
      return false;
    }
  }, []);

  const startRestFallback = useCallback(() => {
    setStreamMode("rest_fallback");
    setConnectionState("disconnected");
    setDataPath((p) => (p.includes("ws") ? "public_rest_fallback" : p || "public_rest_fallback"));
    void loadRestSnapshot(true);
    if (restTimerRef.current) clearInterval(restTimerRef.current);
    restTimerRef.current = setInterval(() => {
      void loadRestSnapshot(true);
    }, REST_FALLBACK_MS);
  }, [loadRestSnapshot]);

  const stopRestFallback = useCallback(() => {
    if (restTimerRef.current) {
      clearInterval(restTimerRef.current);
      restTimerRef.current = null;
    }
  }, []);

  const sendSubscribe = useCallback((ws: WebSocket) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    const { category, symbol, interval, watchlist } = optsRef.current;
    ws.send(
      JSON.stringify({
        op: "subscribe",
        category,
        symbols: [...new Set([symbol, ...watchlist])],
        interval,
      }),
    );
  }, []);

  // Keep one socket for the page lifetime; reconnect only on transport failure.
  useEffect(() => {
    aliveRef.current = true;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const cleanupWs = () => {
      if (wsRef.current) {
        try {
          wsRef.current.onopen = null;
          wsRef.current.onclose = null;
          wsRef.current.onerror = null;
          wsRef.current.onmessage = null;
          wsRef.current.close();
        } catch {
          // ignore
        }
        wsRef.current = null;
      }
    };

    const connect = () => {
      if (!aliveRef.current) return;
      cleanupWs();
      setStreamMode("connecting");
      setConnectionState("connecting");
      let ws: WebSocket;
      try {
        ws = new WebSocket(marketStreamWsUrl());
      } catch {
        startRestFallback();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        stopRestFallback();
        setStreamMode("streaming");
        setConnectionState("connected");
        setStale(false);
        setDataPath("public_ws_live");
        setError(null);
        void loadRestSnapshot(false).then(() => {
          if (ws.readyState === WebSocket.OPEN) sendSubscribe(ws);
        });
      };

      ws.onmessage = (ev) => {
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        const type = String(msg.type || msg.op || "");
        if (type === "pong" || msg.op === "pong") return;
        if (type === "error") {
          setError(String(msg.reason || "stream_error"));
          return;
        }
        if (type === "status") {
          const state = String(msg.connection_state || "connected") as MarketConnectionState;
          setConnectionState(state);
          setStale(Boolean(msg.stale) || state === "stale");
          bumpUpdated();
          return;
        }
        if (type === "ticker") {
          const symbol = String(msg.symbol || "");
          const last = Number(msg.last_price);
          if (!symbol || !Number.isFinite(last)) return;
          setTickers((prev) => {
            const row: MarketTicker = {
              symbol,
              category: (msg.category as MarketCategory) || optsRef.current.category,
              last_price: last,
              bid1: msg.bid1 as number | null | undefined,
              ask1: msg.ask1 as number | null | undefined,
              high_24h: msg.high_24h as number | null | undefined,
              low_24h: msg.low_24h as number | null | undefined,
              volume_24h: msg.volume_24h as number | null | undefined,
              turnover_24h: msg.turnover_24h as number | null | undefined,
              price_24h_pct: msg.price_24h_pct as number | null | undefined,
            };
            const idx = prev.findIndex((t) => t.symbol === symbol);
            if (idx === -1) return [...prev, row];
            const next = prev.slice();
            next[idx] = row;
            return next;
          });
          bumpUpdated();
          return;
        }
        if (type === "kline") {
          const candle = msg.candle as MarketCandle | undefined;
          if (!candle || candle.time == null) return;
          if (String(msg.symbol) !== optsRef.current.symbol) return;
          if (String(msg.interval) !== optsRef.current.interval) return;
          setCandles((prev) => {
            const { bars } = applyCandleUpdate(prev, {
              ...candle,
              confirmed: Boolean(candle.confirmed),
            });
            recomputeIndicators(bars);
            return bars;
          });
          bumpUpdated();
          return;
        }
        if (type === "orderbook") {
          if (String(msg.symbol) !== optsRef.current.symbol) return;
          const bookPayload = msg.book as OrderBookView | undefined;
          if (bookPayload) {
            setBook((prev) => preferStableOrderBook(prev, bookPayload));
            if (bookPayload.stale) setStale(true);
            bumpUpdated();
          }
          return;
        }
        if (type === "orderbook_resync") {
          const now = Date.now();
          if (now - lastBookResyncRef.current < BOOK_RESYNC_MIN_MS) return;
          lastBookResyncRef.current = now;
          void fetchOrderBook(optsRef.current.category, optsRef.current.symbol, 50).then((ob) => {
            if (aliveRef.current) setBook(ob);
          });
          return;
        }
        if (type === "trade") {
          if (String(msg.symbol) !== optsRef.current.symbol) return;
          const trade: PublicTradeView = {
            trade_id: String(msg.trade_id || ""),
            price: Number(msg.price),
            size: Number(msg.size),
            side: (msg.side as PublicTradeView["side"]) || "Unknown",
            timestamp_ms: Number(msg.timestamp_ms) || 0,
          };
          setTrades((prev) => [trade, ...prev].slice(0, 40));
          bumpUpdated();
        }
      };

      ws.onerror = () => {
        setError("websocket_error");
      };

      ws.onclose = () => {
        wsRef.current = null;
        if (!aliveRef.current) return;
        setConnectionState("reconnecting");
        setStreamMode("connecting");
        startRestFallback();
        const attempt = attemptRef.current + 1;
        attemptRef.current = attempt;
        const exp = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** (attempt - 1));
        const jitter = Math.random() * exp * 0.25;
        reconnectTimer = setTimeout(connect, exp + jitter);
      };
    };

    void loadRestSnapshot(true).then(() => {
      if (aliveRef.current) connect();
    });

    return () => {
      aliveRef.current = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      stopRestFallback();
      cleanupWs();
    };
  }, [
    loadRestSnapshot,
    recomputeIndicators,
    sendSubscribe,
    startRestFallback,
    stopRestFallback,
  ]);

  // Symbol / interval / category changes: REST seed + resubscribe without tearing the socket.
  // Skip the mount pass — the connect effect already seeds once.
  useEffect(() => {
    if (skipOptsEffectRef.current) {
      skipOptsEffectRef.current = false;
      return;
    }
    void loadRestSnapshot(true);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendSubscribe(ws);
    }
  }, [opts.category, opts.symbol, opts.interval, loadRestSnapshot, sendSubscribe]);

  const live = streamMode === "streaming" && !stale;

  return {
    candles,
    indicators,
    tickers,
    book,
    trades,
    connectionState,
    streamMode,
    stale,
    dataPath,
    error,
    updatedAt,
    live,
    refreshRest: loadRestSnapshot,
  };
}
