import type {
  MarketCandle,
  MarketCategory,
  MarketIndicators,
  MarketStatusView,
  MarketTicker,
  OrderBookView,
  PublicTradeView,
} from "@/lib/market/types";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : body?.detail?.error || `market_http_${res.status}`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchMarketStatus(): Promise<MarketStatusView> {
  return getJson("/api/market/status");
}

export async function fetchTickers(
  category: MarketCategory,
  symbols: string[],
): Promise<{ data_path: string; tickers: MarketTicker[] }> {
  const q = new URLSearchParams({
    category,
    symbols: symbols.join(","),
  });
  return getJson(`/api/market/tickers?${q}`);
}

export async function fetchKlines(
  category: MarketCategory,
  symbol: string,
  interval: string,
  limit = 200,
): Promise<{
  data_path: string;
  interval_label: string;
  candles: MarketCandle[];
  indicators: MarketIndicators;
  forming_excluded: boolean;
}> {
  const q = new URLSearchParams({
    category,
    symbol,
    interval,
    limit: String(limit),
  });
  return getJson(`/api/market/klines?${q}`);
}

export async function fetchOrderBook(
  category: MarketCategory,
  symbol: string,
  limit = 25,
): Promise<OrderBookView> {
  const q = new URLSearchParams({
    category,
    symbol,
    limit: String(limit),
  });
  return getJson(`/api/market/orderbook?${q}`);
}

export async function fetchTrades(
  category: MarketCategory,
  symbol: string,
  limit = 30,
): Promise<{ data_path: string; trades: PublicTradeView[] }> {
  const q = new URLSearchParams({
    category,
    symbol,
    limit: String(limit),
  });
  return getJson(`/api/market/trades?${q}`);
}
