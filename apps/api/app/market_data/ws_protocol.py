"""Public WebSocket protocol helpers — reconnect, validation, subscriptions."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from apps.api.app.market_data.constants import (
    BYBIT_PUBLIC_WS_LINEAR,
    BYBIT_PUBLIC_WS_SPOT,
    WS_RECONNECT_BASE_SECONDS,
    WS_RECONNECT_MAX_SECONDS,
    WS_STALE_AFTER_SECONDS,
)
from apps.api.app.market_data.schemas import ConnectionState, MarketCategory


class WsMessageKind(str, Enum):
    subscribe_ack = "subscribe_ack"
    ping = "ping"
    pong = "pong"
    ticker = "ticker"
    kline = "kline"
    orderbook = "orderbook"
    trade = "trade"
    malformed = "malformed"
    unknown = "unknown"


@dataclass
class ParsedWsMessage:
    kind: WsMessageKind
    topic: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class PublicWsSessionState:
    category: MarketCategory
    connection_state: ConnectionState = ConnectionState.disconnected
    subscriptions: set[str] = field(default_factory=set)
    desired_subscriptions: set[str] = field(default_factory=set)
    reconnect_attempt: int = 0
    last_message_at: float | None = None
    last_pong_at: float | None = None
    connected_url: str | None = None
    error: str | None = None

    def mark_connecting(self, url: str) -> None:
        self.connection_state = ConnectionState.connecting
        self.connected_url = url
        self.error = None

    def mark_connected(self) -> None:
        self.connection_state = ConnectionState.connected
        self.reconnect_attempt = 0
        self.last_message_at = time.monotonic()
        self.error = None

    def mark_disconnected(self, *, reconnecting: bool = False) -> None:
        self.connection_state = (
            ConnectionState.reconnecting if reconnecting else ConnectionState.disconnected
        )
        self.subscriptions.clear()

    def mark_error(self, reason: str) -> None:
        self.connection_state = ConnectionState.error
        self.error = reason

    def note_message(self) -> None:
        self.last_message_at = time.monotonic()
        if self.connection_state == ConnectionState.stale:
            self.connection_state = ConnectionState.connected

    def evaluate_staleness(
        self, *, now: float | None = None, stale_after: float = WS_STALE_AFTER_SECONDS
    ) -> bool:
        clock = now if now is not None else time.monotonic()
        if self.connection_state not in {
            ConnectionState.connected,
            ConnectionState.stale,
        }:
            return False
        if self.last_message_at is None:
            return False
        if clock - self.last_message_at > stale_after:
            self.connection_state = ConnectionState.stale
            return True
        return False

    def next_backoff_seconds(
        self,
        *,
        base: float = WS_RECONNECT_BASE_SECONDS,
        maximum: float = WS_RECONNECT_MAX_SECONDS,
        rng: random.Random | None = None,
    ) -> float:
        self.reconnect_attempt += 1
        exp = min(maximum, base * (2 ** (self.reconnect_attempt - 1)))
        jitter_src = rng or random.Random()
        jitter = jitter_src.uniform(0, exp * 0.25)
        return min(maximum, exp + jitter)


def ws_url_for_category(category: MarketCategory) -> str:
    if category is MarketCategory.spot:
        return BYBIT_PUBLIC_WS_SPOT
    if category is MarketCategory.linear:
        return BYBIT_PUBLIC_WS_LINEAR
    raise ValueError(f"unsupported_category:{category}")


def build_subscribe_args(
    *,
    symbols: list[str],
    intervals: list[str] | None = None,
    depth: int = 50,
    include_tickers: bool = True,
    include_orderbook: bool = True,
    include_trades: bool = True,
    include_klines: bool = True,
) -> list[str]:
    """Build unique Bybit V5 public topic list (no duplicates)."""
    args: list[str] = []
    seen: set[str] = set()
    intervals = intervals or ["15"]
    for raw in symbols:
        symbol = raw.upper()
        topics: list[str] = []
        if include_tickers:
            topics.append(f"tickers.{symbol}")
        if include_orderbook:
            topics.append(f"orderbook.{depth}.{symbol}")
        if include_trades:
            topics.append(f"publicTrade.{symbol}")
        if include_klines:
            for interval in intervals:
                topics.append(f"kline.{interval}.{symbol}")
        for topic in topics:
            if topic not in seen:
                seen.add(topic)
                args.append(topic)
    return args


def subscribe_payload(args: list[str]) -> dict[str, Any]:
    return {"op": "subscribe", "args": list(dict.fromkeys(args))}


def parse_ws_message(raw: object) -> ParsedWsMessage:
    if not isinstance(raw, dict):
        return ParsedWsMessage(kind=WsMessageKind.malformed, reason="not_object")

    op = raw.get("op")
    if op == "ping":
        return ParsedWsMessage(kind=WsMessageKind.ping, payload=raw)
    if op == "pong" or raw.get("ret_msg") == "pong":
        return ParsedWsMessage(kind=WsMessageKind.pong, payload=raw)
    if op == "subscribe":
        return ParsedWsMessage(kind=WsMessageKind.subscribe_ack, payload=raw)

    topic = raw.get("topic")
    data = raw.get("data")
    if not isinstance(topic, str) or not topic:
        # Some acks omit topic.
        if "success" in raw:
            return ParsedWsMessage(kind=WsMessageKind.subscribe_ack, payload=raw)
        return ParsedWsMessage(kind=WsMessageKind.malformed, reason="missing_topic")

    if topic.startswith("tickers."):
        if not isinstance(data, (dict, list)):
            return ParsedWsMessage(
                kind=WsMessageKind.malformed, topic=topic, reason="bad_ticker_data"
            )
        return ParsedWsMessage(kind=WsMessageKind.ticker, topic=topic, payload=raw)
    if topic.startswith("kline."):
        if not isinstance(data, list):
            return ParsedWsMessage(
                kind=WsMessageKind.malformed, topic=topic, reason="bad_kline_data"
            )
        return ParsedWsMessage(kind=WsMessageKind.kline, topic=topic, payload=raw)
    if topic.startswith("orderbook."):
        if not isinstance(data, dict):
            return ParsedWsMessage(
                kind=WsMessageKind.malformed, topic=topic, reason="bad_orderbook_data"
            )
        return ParsedWsMessage(kind=WsMessageKind.orderbook, topic=topic, payload=raw)
    if topic.startswith("publicTrade."):
        if not isinstance(data, list):
            return ParsedWsMessage(
                kind=WsMessageKind.malformed, topic=topic, reason="bad_trade_data"
            )
        return ParsedWsMessage(kind=WsMessageKind.trade, topic=topic, payload=raw)
    return ParsedWsMessage(kind=WsMessageKind.unknown, topic=topic, payload=raw)


def is_orderbook_snapshot(msg: dict[str, Any]) -> bool:
    return str(msg.get("type") or "").lower() == "snapshot"
