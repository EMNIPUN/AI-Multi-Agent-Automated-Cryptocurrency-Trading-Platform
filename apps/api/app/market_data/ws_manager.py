"""Resilient public Bybit WebSocket manager (injectable I/O for tests)."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.api.app.market_data.candles import CandleSeries, interval_to_ms, parse_bybit_kline_row
from apps.api.app.market_data.constants import DATA_PATH_PUBLIC_LIVE, WS_PING_INTERVAL_SECONDS
from apps.api.app.market_data.orderbook import OrderBookSynchronizer, parse_levels
from apps.api.app.market_data.schemas import (
    ConnectionState,
    MarketCategory,
    MarketStatus,
)
from apps.api.app.market_data.ws_protocol import (
    ParsedWsMessage,
    PublicWsSessionState,
    WsMessageKind,
    build_subscribe_args,
    is_orderbook_snapshot,
    parse_ws_message,
    subscribe_payload,
    ws_url_for_category,
)

logger = logging.getLogger(__name__)


class WsSocket(Protocol):
    def send(self, data: str) -> None: ...

    def recv(self, timeout: float | None = None) -> str: ...

    def close(self) -> None: ...


WsConnectFn = Callable[[str], WsSocket]
# Normalized fan-out events for browser bridge (no secrets).
MarketEventListener = Callable[[dict[str, Any]], None]


@dataclass
class PublicMarketWsManager:
    """
    Single-category public WS session with reconnect + subscription restore.

    Does not open private streams. Does not place orders.
    """

    category: MarketCategory
    symbols: list[str]
    intervals: list[str] = field(default_factory=lambda: ["15"])
    connect_fn: WsConnectFn | None = None
    sleep_fn: Callable[[float], None] = time.sleep
    monotonic_fn: Callable[[], float] = time.monotonic
    rng_seed: int | None = 7
    max_reconnects: int | None = None
    on_event: MarketEventListener | None = None

    state: PublicWsSessionState = field(init=False)
    orderbooks: dict[str, OrderBookSynchronizer] = field(default_factory=dict)
    candles: dict[tuple[str, str], CandleSeries] = field(default_factory=dict)
    last_tickers: dict[str, dict[str, Any]] = field(default_factory=dict)
    recent_trades: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = field(default=None, init=False)
    _sock: WsSocket | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _resync_emitted: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.state = PublicWsSessionState(category=self.category)
        self.state.desired_subscriptions = set(
            build_subscribe_args(
                symbols=self.symbols,
                intervals=self.intervals,
            )
        )
        for symbol in self.symbols:
            self.orderbooks[symbol.upper()] = OrderBookSynchronizer(
                symbol=symbol.upper(), category=self.category
            )
            for interval in self.intervals:
                self.candles[(symbol.upper(), interval)] = CandleSeries(
                    interval_ms=interval_to_ms(interval)
                )

    def status(self) -> MarketStatus:
        self.state.evaluate_staleness(now=self.monotonic_fn())
        return MarketStatus(
            connection_state=self.state.connection_state,
            data_path=DATA_PATH_PUBLIC_LIVE,
            category=self.category,
            symbols=[s.upper() for s in self.symbols],
            last_message_at=self.state.last_message_at,
            reconnect_attempt=self.state.reconnect_attempt,
            subscriptions=sorted(self.state.subscriptions),
            stale=self.state.connection_state is ConnectionState.stale,
            private_reads_enabled=False,
            trading_enabled=False,
        )

    def start(self) -> None:
        if self.connect_fn is None:
            raise RuntimeError("connect_fn_required")
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name=f"bybit-public-ws-{self.category.value}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.state.mark_disconnected(reconnecting=False)

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:  # noqa: BLE001 — never break the socket loop
            logger.debug("market_ws_listener_error", exc_info=True)

    def emit_status(self) -> None:
        st = self.status()
        self._emit(
            {
                "type": "status",
                "category": self.category.value,
                "connection_state": st.connection_state.value,
                "data_path": st.data_path,
                "symbols": st.symbols,
                "stale": st.stale,
                "reconnect_attempt": st.reconnect_attempt,
                "subscriptions": st.subscriptions,
                "private_reads_enabled": False,
                "trading_enabled": False,
                "stream_mode": "public_ws",
            }
        )

    def handle_raw_message(self, raw_text: str) -> ParsedWsMessage:
        """Parse + apply one message (also used by unit tests without a socket)."""
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError:
            return ParsedWsMessage(kind=WsMessageKind.malformed, reason="invalid_json")
        parsed = parse_ws_message(raw)
        self.state.note_message()
        if parsed.kind is WsMessageKind.malformed:
            logger.debug("market_ws_malformed reason=%s", parsed.reason)
            self._emit(
                {
                    "type": "malformed",
                    "category": self.category.value,
                    "reason": parsed.reason,
                }
            )
            return parsed
        if parsed.kind is WsMessageKind.ping:
            if self._sock is not None:
                self._sock.send(json.dumps({"op": "pong"}))
            return parsed
        if parsed.kind is WsMessageKind.pong:
            self.state.last_pong_at = self.monotonic_fn()
            return parsed
        if parsed.kind is WsMessageKind.subscribe_ack:
            success = bool(parsed.payload.get("success", True))
            if success:
                # Restore tracking from desired set after ack.
                self.state.subscriptions |= set(self.state.desired_subscriptions)
            self.emit_status()
            return parsed
        if parsed.kind is WsMessageKind.ticker:
            self._apply_ticker(parsed.payload)
        elif parsed.kind is WsMessageKind.kline:
            self._apply_kline(parsed.payload)
        elif parsed.kind is WsMessageKind.orderbook:
            self._apply_orderbook(parsed.payload)
        elif parsed.kind is WsMessageKind.trade:
            self._apply_trade(parsed.payload)
        return parsed

    def _run_loop(self) -> None:
        assert self.connect_fn is not None
        import random

        rng = random.Random(self.rng_seed)
        while not self._stop.is_set():
            if self.max_reconnects is not None and self.state.reconnect_attempt >= self.max_reconnects:
                self.state.mark_error("max_reconnects")
                return
            url = ws_url_for_category(self.category)
            self.state.mark_connecting(url)
            try:
                sock = self.connect_fn(url)
            except Exception as exc:  # noqa: BLE001
                self.state.mark_disconnected(reconnecting=True)
                delay = self.state.next_backoff_seconds(rng=rng)
                logger.info(
                    "market_ws_connect_failed category=%s err=%s backoff=%.2f",
                    self.category.value,
                    type(exc).__name__,
                    delay,
                )
                self.sleep_fn(delay)
                continue

            self._sock = sock
            self.state.mark_connected()
            self.emit_status()
            try:
                args = sorted(self.state.desired_subscriptions)
                sock.send(json.dumps(subscribe_payload(args)))
                last_ping = self.monotonic_fn()
                last_stale_emit = 0.0
                while not self._stop.is_set():
                    became_stale = self.state.evaluate_staleness(now=self.monotonic_fn())
                    now = self.monotonic_fn()
                    if became_stale and now - last_stale_emit > 5.0:
                        self.emit_status()
                        last_stale_emit = now
                    if now - last_ping >= WS_PING_INTERVAL_SECONDS:
                        sock.send(json.dumps({"op": "ping"}))
                        last_ping = now
                    try:
                        raw_text = sock.recv(timeout=1.0)
                    except TimeoutError:
                        continue
                    except Exception:
                        break
                    self.handle_raw_message(raw_text)
            finally:
                try:
                    sock.close()
                except Exception:  # noqa: BLE001
                    pass
                self._sock = None
                if self._stop.is_set():
                    self.state.mark_disconnected(reconnecting=False)
                    self.emit_status()
                    return
                self.state.mark_disconnected(reconnecting=True)
                self.emit_status()
                delay = self.state.next_backoff_seconds(rng=rng)
                self.sleep_fn(delay)

    def _apply_ticker(self, payload: dict[str, Any]) -> None:
        data = payload.get("data")
        rows = data if isinstance(data, list) else [data]
        with self._lock:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").upper()
                if not symbol:
                    continue
                self.last_tickers[symbol] = row
                try:
                    last = float(row.get("lastPrice") or 0)
                except (TypeError, ValueError):
                    continue
                if last <= 0:
                    continue
                pct = row.get("price24hPcnt")
                try:
                    pct_f = float(pct) * 100.0 if pct not in (None, "") else None
                except (TypeError, ValueError):
                    pct_f = None
                self._emit(
                    {
                        "type": "ticker",
                        "category": self.category.value,
                        "symbol": symbol,
                        "last_price": last,
                        "bid1": _safe_float(row.get("bid1Price")),
                        "ask1": _safe_float(row.get("ask1Price")),
                        "high_24h": _safe_float(row.get("highPrice24h")),
                        "low_24h": _safe_float(row.get("lowPrice24h")),
                        "volume_24h": _safe_float(row.get("volume24h")),
                        "turnover_24h": _safe_float(row.get("turnover24h")),
                        "price_24h_pct": pct_f,
                        "ts_ms": int(row.get("ts") or 0) or None,
                    }
                )

    def _apply_kline(self, payload: dict[str, Any]) -> None:
        topic = str(payload.get("topic") or "")
        parts = topic.split(".")
        if len(parts) < 3:
            return
        interval, symbol = parts[1], parts[2].upper()
        series = self.candles.get((symbol, interval))
        if series is None:
            return
        data = payload.get("data")
        if not isinstance(data, list):
            return
        for row in data:
            if not isinstance(row, dict):
                continue
            # WS kline object uses start/open/high/low/close/volume/confirm
            try:
                start_ms = int(row["start"])
                bar_list = [
                    start_ms,
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("volume") or 0,
                ]
                confirmed = bool(row.get("confirm"))
                candle = parse_bybit_kline_row(bar_list, confirmed=confirmed)
                if candle is None:
                    continue
                result = series.apply(candle, allow_forming_replace=True)
                if not result.accepted and result.reason == "duplicate":
                    continue
                self._emit(
                    {
                        "type": "kline",
                        "category": self.category.value,
                        "symbol": symbol,
                        "interval": interval,
                        "candle": candle.model_dump(),
                        "update_reason": result.reason,
                    }
                )
            except (KeyError, TypeError, ValueError):
                continue

    def _emit_orderbook_resync(self, *, symbol: str, reason: str, topic: str) -> None:
        if symbol in self._resync_emitted:
            return
        self._resync_emitted.add(symbol)
        logger.info(
            "market_ws_orderbook_resync symbol=%s reason=%s",
            symbol,
            reason,
        )
        self._emit(
            {
                "type": "orderbook_resync",
                "category": self.category.value,
                "symbol": symbol,
                "reason": reason,
            }
        )
        # Force Bybit to send a fresh snapshot; deltas must never replace the book.
        self._resubscribe_orderbook_topic(topic)

    def _resubscribe_orderbook_topic(self, topic: str) -> None:
        sock = self._sock
        if sock is None or not topic:
            return
        try:
            sock.send(json.dumps({"op": "unsubscribe", "args": [topic]}))
            sock.send(json.dumps(subscribe_payload([topic])))
        except Exception:  # noqa: BLE001
            logger.info(
                "market_ws_orderbook_resubscribe_failed topic=%s",
                topic,
                exc_info=True,
            )

    def _apply_orderbook(self, payload: dict[str, Any]) -> None:
        topic = str(payload.get("topic") or "")
        parts = topic.split(".")
        if len(parts) < 3:
            return
        symbol = parts[-1].upper()
        book = self.orderbooks.get(symbol)
        if book is None:
            return
        data = payload.get("data")
        if not isinstance(data, dict):
            return
        bids = parse_levels(data.get("b"))
        asks = parse_levels(data.get("a"))
        if bids is None or asks is None:
            return
        u = data.get("u")
        seq = data.get("seq")
        update_id = int(u) if u is not None else None
        sequence = int(seq) if seq is not None else None

        # Only explicit snapshots may replace the book. Treating a post-gap delta
        # as a snapshot collapses depth to a few levels and makes the UI flicker.
        if is_orderbook_snapshot(payload):
            book.apply_snapshot(
                bids=bids, asks=asks, update_id=update_id, sequence=sequence
            )
            self._resync_emitted.discard(symbol)
        elif not book.synced:
            self._emit_orderbook_resync(
                symbol=symbol, reason="awaiting_snapshot", topic=topic
            )
            return
        else:
            result = book.apply_delta(
                bids=bids, asks=asks, update_id=update_id, sequence=sequence
            )
            if result.needs_resnapshot:
                self._emit_orderbook_resync(
                    symbol=symbol, reason=result.reason, topic=topic
                )
                return
        snap = book.snapshot()
        self._emit(
            {
                "type": "orderbook",
                "category": self.category.value,
                "symbol": symbol,
                "book": snap.model_dump(),
            }
        )

    def _apply_trade(self, payload: dict[str, Any]) -> None:
        topic = str(payload.get("topic") or "")
        symbol = topic.split(".")[-1].upper() if topic else ""
        data = payload.get("data")
        if not symbol or not isinstance(data, list):
            return
        emitted: list[dict[str, Any]] = []
        with self._lock:
            bucket = self.recent_trades.setdefault(symbol, [])
            for row in data:
                if isinstance(row, dict):
                    bucket.append(row)
                    emitted.append(row)
            # Bound memory.
            if len(bucket) > 200:
                del bucket[:-200]
        for row in emitted:
            side_raw = str(row.get("S") or row.get("side") or "")
            side = (
                "Buy"
                if side_raw in {"Buy", "buy"}
                else "Sell"
                if side_raw in {"Sell", "sell"}
                else "Unknown"
            )
            try:
                self._emit(
                    {
                        "type": "trade",
                        "category": self.category.value,
                        "symbol": symbol,
                        "trade_id": str(row.get("i") or row.get("execId") or ""),
                        "price": float(row.get("p") or row.get("price") or 0),
                        "size": float(row.get("v") or row.get("size") or 0),
                        "side": side,
                        "timestamp_ms": int(row.get("T") or row.get("time") or 0),
                    }
                )
            except (TypeError, ValueError):
                continue


def _safe_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class FakeWsSocket:
    """In-memory socket for deterministic WS tests."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self._inbox: list[str] = []
        self.closed = False

    def push(self, message: dict[str, Any] | str) -> None:
        if isinstance(message, str):
            self._inbox.append(message)
        else:
            self._inbox.append(json.dumps(message))

    def send(self, data: str) -> None:
        if self.closed:
            raise RuntimeError("socket_closed")
        self.sent.append(data)

    def recv(self, timeout: float | None = None) -> str:  # noqa: ARG002
        if self.closed:
            raise RuntimeError("socket_closed")
        if not self._inbox:
            raise TimeoutError()
        return self._inbox.pop(0)

    def close(self) -> None:
        self.closed = True
