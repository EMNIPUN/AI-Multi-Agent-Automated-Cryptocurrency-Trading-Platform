"""Typed public market-data payloads."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class MarketCategory(str, Enum):
    spot = "spot"
    linear = "linear"


class ConnectionState(str, Enum):
    disconnected = "disconnected"
    connecting = "connecting"
    connected = "connected"
    reconnecting = "reconnecting"
    stale = "stale"
    error = "error"


class CandleBar(BaseModel):
    time: int = Field(description="Unix seconds (candle open)")
    open: float
    high: float
    low: float
    close: float
    volume: float
    confirmed: bool = True


class TickerSnapshot(BaseModel):
    symbol: str
    category: MarketCategory
    last_price: float
    bid1: float | None = None
    ask1: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    volume_24h: float | None = None
    turnover_24h: float | None = None
    price_24h_pct: float | None = None
    mark_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    updated_at_ms: int | None = None


class OrderBookLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    symbol: str
    category: MarketCategory
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    update_id: int | None = None
    sequence: int | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    spread_bps: float | None = None
    synced: bool = True
    stale: bool = False


class PublicTrade(BaseModel):
    symbol: str
    category: MarketCategory
    trade_id: str
    price: float
    size: float
    side: Literal["Buy", "Sell", "Unknown"] = "Unknown"
    timestamp_ms: int


class IndicatorSeries(BaseModel):
    ema_20: list[float | None]
    ema_50: list[float | None]
    ema_200: list[float | None]
    rsi_14: list[float | None]


class MarketStatus(BaseModel):
    connection_state: ConnectionState
    data_path: str
    category: MarketCategory | None = None
    symbols: list[str] = Field(default_factory=list)
    last_message_at: float | None = None
    reconnect_attempt: int = 0
    subscriptions: list[str] = Field(default_factory=list)
    stale: bool = False
    private_reads_enabled: bool = False
    trading_enabled: bool = False
    note: str = (
        "Public Bybit market data only — not private account connectivity."
    )


class KlinesResponse(BaseModel):
    category: MarketCategory
    symbol: str
    interval: str
    interval_label: str
    data_path: str
    candles: list[CandleBar]
    indicators: IndicatorSeries
    forming_excluded: bool = True


class TickersResponse(BaseModel):
    category: MarketCategory
    data_path: str
    tickers: list[TickerSnapshot]


class TradesResponse(BaseModel):
    category: MarketCategory
    symbol: str
    data_path: str
    trades: list[PublicTrade]
