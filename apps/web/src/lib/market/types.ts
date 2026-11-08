export type MarketCategory = "spot" | "linear";

export type MarketConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "stale"
  | "error";

export type MarketDataPath =
  | "public_live"
  | "public_simulated"
  | "public_rest_only"
  | "sample"
  | "replay";

export interface MarketCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  confirmed?: boolean;
}

export interface MarketIndicators {
  ema_20: Array<number | null>;
  ema_50: Array<number | null>;
  ema_200: Array<number | null>;
  rsi_14: Array<number | null>;
}

export interface MarketTicker {
  symbol: string;
  category: MarketCategory;
  last_price: number;
  bid1?: number | null;
  ask1?: number | null;
  high_24h?: number | null;
  low_24h?: number | null;
  volume_24h?: number | null;
  turnover_24h?: number | null;
  price_24h_pct?: number | null;
  mark_price?: number | null;
  funding_rate?: number | null;
}

export interface OrderBookLevel {
  price: number;
  size: number;
}

export interface OrderBookView {
  symbol: string;
  category: MarketCategory;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  best_bid?: number | null;
  best_ask?: number | null;
  spread?: number | null;
  spread_bps?: number | null;
  synced: boolean;
  stale: boolean;
}

export interface PublicTradeView {
  trade_id: string;
  price: number;
  size: number;
  side: "Buy" | "Sell" | "Unknown";
  timestamp_ms: number;
}

export interface MarketStatusView {
  connection_state: MarketConnectionState;
  data_path: string;
  category?: MarketCategory | null;
  symbols: string[];
  stale: boolean;
  private_reads_enabled: boolean;
  trading_enabled: boolean;
  note: string;
}

export const INTERVAL_OPTIONS = [
  { value: "1", label: "1m" },
  { value: "5", label: "5m" },
  { value: "15", label: "15m" },
  { value: "60", label: "1h" },
  { value: "240", label: "4h" },
  { value: "D", label: "1D" },
] as const;

export const DEFAULT_WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const;
