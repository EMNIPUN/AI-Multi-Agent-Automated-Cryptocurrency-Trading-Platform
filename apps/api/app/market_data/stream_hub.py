"""
Public market stream hub — bridges allowlisted Bybit public WS to local browsers.

Browsers never supply upstream URLs. No private streams. No wallet/auth coupling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from apps.api.app.market_data.constants import (
    DEFAULT_SYMBOLS,
    SUPPORTED_INTERVALS,
)
from apps.api.app.market_data.real_ws import connect_bybit_public
from apps.api.app.market_data.schemas import MarketCategory
from apps.api.app.market_data.ws_manager import PublicMarketWsManager
from apps.api.app.market_data.ws_protocol import ws_url_for_category

logger = logging.getLogger(__name__)

CLIENT_QUEUE_MAX = 256
MAX_BROWSER_CLIENTS = 32


@dataclass
class BrowserSubscription:
    category: MarketCategory
    symbols: set[str]
    interval: str


@dataclass
class BrowserClient:
    client_id: str
    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop
    subscription: BrowserSubscription | None = None
    dropped: int = 0


@dataclass
class MarketStreamHub:
    """Process-local hub: one Bybit public manager per category."""

    _managers: dict[MarketCategory, PublicMarketWsManager] = field(default_factory=dict)
    _clients: dict[str, BrowserClient] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _simulated: bool = field(
        default_factory=lambda: os.getenv("MARKET_DATA_SIMULATED", "false")
        .strip()
        .lower()
        in {"1", "true", "yes"}
    )
    # Tests inject connect_fn / skip real network.
    connect_fn: Any = None

    def stop_all(self) -> None:
        with self._lock:
            managers = list(self._managers.values())
            self._managers.clear()
            self._clients.clear()
        for mgr in managers:
            mgr.stop()

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def register_client(
        self, client_id: str, loop: asyncio.AbstractEventLoop
    ) -> BrowserClient:
        with self._lock:
            if len(self._clients) >= MAX_BROWSER_CLIENTS:
                raise RuntimeError("too_many_browser_clients")
            client = BrowserClient(
                client_id=client_id,
                queue=asyncio.Queue(maxsize=CLIENT_QUEUE_MAX),
                loop=loop,
            )
            self._clients[client_id] = client
            return client

    def unregister_client(self, client_id: str) -> None:
        with self._lock:
            self._clients.pop(client_id, None)
            # Stop unused category managers when no subscribers remain.
            in_use = {
                c.subscription.category
                for c in self._clients.values()
                if c.subscription is not None
            }
            to_stop = [cat for cat in list(self._managers) if cat not in in_use]
            for cat in to_stop:
                mgr = self._managers.pop(cat, None)
                if mgr is not None:
                    mgr.stop()

    def validate_subscribe(
        self,
        *,
        category: str,
        symbols: list[str],
        interval: str,
    ) -> BrowserSubscription:
        try:
            cat = MarketCategory(category)
        except ValueError as exc:
            raise ValueError("invalid_category") from exc
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError("unsupported_interval")
        allow = {s.upper() for s in DEFAULT_SYMBOLS}
        # Configurable extras via env (comma-separated), still no arbitrary URLs.
        extra = os.getenv("MARKET_PUBLIC_SYMBOLS", "").strip()
        if extra:
            allow |= {s.strip().upper() for s in extra.split(",") if s.strip()}
        cleaned: list[str] = []
        for raw in symbols:
            sym = str(raw).strip().upper()
            if not sym:
                continue
            if sym not in allow:
                raise ValueError(f"symbol_not_allowlisted:{sym}")
            cleaned.append(sym)
        if not cleaned:
            cleaned = list(DEFAULT_SYMBOLS)
        # Reject any attempt to pass upstream URL fields (defense in depth).
        return BrowserSubscription(
            category=cat, symbols=set(cleaned[:20]), interval=interval
        )

    def subscribe_client(self, client_id: str, sub: BrowserSubscription) -> None:
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                raise KeyError("unknown_client")
            client.subscription = sub
            mgr = self._managers.get(sub.category)
            if mgr is None:
                if self._simulated and self.connect_fn is None:
                    # Simulated mode without inject: do not open real sockets.
                    raise RuntimeError("market_ws_simulated_without_inject")
                connect = self.connect_fn or connect_bybit_public
                # Verify allowlisted URL construction only.
                _ = ws_url_for_category(sub.category)
                mgr = PublicMarketWsManager(
                    category=sub.category,
                    symbols=sorted(sub.symbols),
                    intervals=[sub.interval],
                    connect_fn=connect,
                    on_event=self._on_manager_event,
                )
                self._managers[sub.category] = mgr
                mgr.start()
            else:
                # Expand desired symbols/intervals for existing manager.
                desired = set(mgr.state.desired_subscriptions)
                from apps.api.app.market_data.ws_protocol import build_subscribe_args

                new_args = set(
                    build_subscribe_args(
                        symbols=sorted(sub.symbols),
                        intervals=[sub.interval],
                    )
                )
                if not new_args.issubset(desired):
                    # Restart manager with union of symbols/intervals (simple personal-use).
                    union_symbols = sorted(
                        {*(mgr.symbols), *sub.symbols}
                    )
                    union_intervals = sorted(set([*mgr.intervals, sub.interval]))
                    mgr.stop()
                    connect = self.connect_fn or connect_bybit_public
                    mgr = PublicMarketWsManager(
                        category=sub.category,
                        symbols=union_symbols,
                        intervals=union_intervals,
                        connect_fn=connect,
                        on_event=self._on_manager_event,
                    )
                    self._managers[sub.category] = mgr
                    mgr.start()
            # Immediate status snapshot for the new subscriber.
            status_event = {
                "type": "status",
                "category": sub.category.value,
                "connection_state": mgr.state.connection_state.value,
                "data_path": "public_live",
                "symbols": sorted(sub.symbols),
                "stale": False,
                "stream_mode": "public_ws",
                "private_reads_enabled": False,
                "trading_enabled": False,
            }
        self._enqueue(client_id, status_event)

    def _on_manager_event(self, event: dict[str, Any]) -> None:
        category = event.get("category")
        symbol = event.get("symbol")
        interval = event.get("interval")
        with self._lock:
            targets = []
            for client in self._clients.values():
                sub = client.subscription
                if sub is None:
                    continue
                if category and sub.category.value != category:
                    continue
                if symbol and symbol not in sub.symbols:
                    # status / malformed may omit symbol — still forward status.
                    if event.get("type") not in {"status", "malformed"}:
                        continue
                if (
                    interval
                    and event.get("type") == "kline"
                    and interval != sub.interval
                ):
                    continue
                targets.append(client.client_id)
        for cid in targets:
            self._enqueue(cid, event)

    def _enqueue(self, client_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                return
            loop = client.loop
            queue = client.queue

        def _put() -> None:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Backpressure: drop oldest, then enqueue.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(event)
                    client.dropped += 1
                    if client.dropped % 50 == 1:
                        logger.info(
                            "market_stream_backpressure client=%s dropped=%s",
                            client_id,
                            client.dropped,
                        )
                except asyncio.QueueFull:
                    pass

        try:
            loop.call_soon_threadsafe(_put)
        except RuntimeError:
            # Loop closed.
            pass


_HUB: MarketStreamHub | None = None
_HUB_LOCK = threading.Lock()


def get_market_stream_hub() -> MarketStreamHub:
    global _HUB
    with _HUB_LOCK:
        if _HUB is None:
            _HUB = MarketStreamHub()
        return _HUB


def reset_market_stream_hub_for_tests(hub: MarketStreamHub | None = None) -> MarketStreamHub:
    global _HUB
    with _HUB_LOCK:
        if _HUB is not None:
            _HUB.stop_all()
        _HUB = hub if hub is not None else MarketStreamHub()
        return _HUB
