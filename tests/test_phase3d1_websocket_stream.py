"""Phase 3D.1 — public market WebSocket stream tests (deterministic mocks)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient
from starlette.websockets import WebSocketDisconnect

from apps.api.app.config import clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.market_data.real_ws import connect_bybit_public
from apps.api.app.market_data.schemas import MarketCategory
from apps.api.app.market_data.stream_hub import (
    MarketStreamHub,
    reset_market_stream_hub_for_tests,
)
from apps.api.app.market_data.ws_manager import FakeWsSocket, PublicMarketWsManager
from apps.api.app.market_data.ws_protocol import ws_url_for_category


def test_real_connect_rejects_non_allowlisted_url() -> None:
    with pytest.raises(ValueError, match="upstream_url_not_allowlisted"):
        connect_bybit_public("wss://evil.example/hack")


def test_spot_linear_stream_urls_isolated() -> None:
    assert ws_url_for_category(MarketCategory.spot).endswith("/spot")
    assert ws_url_for_category(MarketCategory.linear).endswith("/linear")
    assert "/private" not in ws_url_for_category(MarketCategory.linear)


def test_hub_subscribe_allowlist_and_reject_unknown_symbol() -> None:
    hub = MarketStreamHub(connect_fn=lambda url: FakeWsSocket())
    sub = hub.validate_subscribe(
        category="linear", symbols=["BTCUSDT"], interval="15"
    )
    assert sub.category is MarketCategory.linear
    with pytest.raises(ValueError, match="symbol_not_allowlisted"):
        hub.validate_subscribe(
            category="linear", symbols=["HACKUSDT"], interval="15"
        )
    with pytest.raises(ValueError, match="unsupported_interval"):
        hub.validate_subscribe(category="linear", symbols=["BTCUSDT"], interval="3")


def test_hub_backpressure_drops_oldest() -> None:
    hub = reset_market_stream_hub_for_tests(
        MarketStreamHub(connect_fn=lambda url: FakeWsSocket())
    )

    async def _run() -> int:
        loop = asyncio.get_running_loop()
        client = hub.register_client("c1", loop)
        # Fill beyond max.
        for i in range(300):
            hub._enqueue("c1", {"type": "ticker", "n": i})
            await asyncio.sleep(0)
        # Drain remaining
        count = 0
        while not client.queue.empty():
            client.queue.get_nowait()
            count += 1
        hub.unregister_client("c1")
        return count

    remaining = asyncio.run(_run())
    assert remaining <= 256
    assert hub.client_count() == 0


def test_manager_emits_events_and_cleanup() -> None:
    events: list[dict[str, Any]] = []
    mgr = PublicMarketWsManager(
        category=MarketCategory.linear,
        symbols=["BTCUSDT"],
        intervals=["15"],
        connect_fn=None,
        on_event=events.append,
    )
    mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "tickers.BTCUSDT",
                "data": {
                    "symbol": "BTCUSDT",
                    "lastPrice": "65000",
                    "price24hPcnt": "0.01",
                    "volume24h": "10",
                },
            }
        )
    )
    assert any(e.get("type") == "ticker" for e in events)
    # Order book gap recovery signal
    book_mgr = mgr
    book_mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "snapshot",
                "data": {"b": [["100", "1"]], "a": [["101", "1"]], "u": 1, "seq": 1},
            }
        )
    )
    book_mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "delta",
                "data": {"b": [], "a": [], "u": 2, "seq": 9},
            }
        )
    )
    assert any(e.get("type") == "orderbook_resync" for e in events)
    mgr.stop()


def test_orderbook_delta_while_unsynced_does_not_wipe_depth() -> None:
    """Regression: post-gap deltas must not be applied as snapshots (UI flicker)."""
    events: list[dict[str, Any]] = []
    sock = FakeWsSocket()
    mgr = PublicMarketWsManager(
        category=MarketCategory.linear,
        symbols=["BTCUSDT"],
        intervals=["15"],
        connect_fn=None,
        on_event=events.append,
    )
    mgr._sock = sock

    deep_bids = [[str(100 - i), "1"] for i in range(8)]
    deep_asks = [[str(101 + i), "1"] for i in range(8)]
    mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "snapshot",
                "data": {"b": deep_bids, "a": deep_asks, "u": 1, "seq": 1},
            }
        )
    )
    book = mgr.orderbooks["BTCUSDT"]
    assert book.synced
    assert len(book.bids) >= 8
    assert len(book.asks) >= 8

    # Sequence gap → unsynced + resync signal (no book emit of collapsed depth).
    mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "delta",
                "data": {"b": [["99", "2"]], "a": [], "u": 2, "seq": 9},
            }
        )
    )
    assert not book.synced
    assert any(e.get("type") == "orderbook_resync" for e in events)
    assert any("unsubscribe" in s for s in sock.sent)
    assert any('"op": "subscribe"' in s or '"op":"subscribe"' in s for s in sock.sent)

    before_bids = dict(book.bids)
    before_asks = dict(book.asks)
    events.clear()

    # Sparse delta while awaiting snapshot must not replace the book.
    mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "delta",
                "data": {"b": [["99", "3"]], "a": [["101", "0.001"]], "u": 3, "seq": 10},
            }
        )
    )
    assert book.bids == before_bids
    assert book.asks == before_asks
    assert not any(e.get("type") == "orderbook" for e in events)

    # Real snapshot restores sync and full depth.
    mgr.handle_raw_message(
        json.dumps(
            {
                "topic": "orderbook.50.BTCUSDT",
                "type": "snapshot",
                "data": {"b": deep_bids, "a": deep_asks, "u": 10, "seq": 20},
            }
        )
    )
    assert book.synced
    assert len(book.bids) >= 8
    assert any(e.get("type") == "orderbook" for e in events)
    mgr.stop()


def test_duplicate_out_of_order_kline_events() -> None:
    events: list[dict[str, Any]] = []
    mgr = PublicMarketWsManager(
        category=MarketCategory.spot,
        symbols=["ETHUSDT"],
        intervals=["1"],
        on_event=events.append,
    )
    kline = {
        "topic": "kline.1.ETHUSDT",
        "data": [
            {
                "start": 1_000_000,
                "open": "1",
                "high": "2",
                "low": "0.5",
                "close": "1.5",
                "volume": "10",
                "confirm": True,
            }
        ],
    }
    mgr.handle_raw_message(json.dumps(kline))
    mgr.handle_raw_message(json.dumps(kline))  # duplicate
    klines = [e for e in events if e.get("type") == "kline"]
    assert len(klines) == 1
    mgr.stop()


def test_stream_ws_protocol_and_no_private_exposure() -> None:
    clear_settings_cache()
    sockets: list[FakeWsSocket] = []

    def connect(url: str) -> FakeWsSocket:
        assert url.startswith("wss://stream.bybit.com/")
        sock = FakeWsSocket()
        sockets.append(sock)
        sock.push({"success": True, "ret_msg": "OK", "op": "subscribe"})
        return sock

    reset_market_stream_hub_for_tests(MarketStreamHub(connect_fn=connect))
    app = create_app()
    client = TestClient(app)

    # Public meta still no private.
    meta = client.get("/api/v1/market/meta").json()
    assert meta["orders_supported"] is False
    assert meta["private_endpoints"] is False
    assert meta["stream_path"] == "/api/v1/market/stream"

    # Wallet is a separate HTTP route — not on market stream path.
    root = client.get("/").json()
    assert root["market_public_stream"] == "/api/v1/market/stream"
    assert "exchange_wallet" in root

    with client.websocket_connect("/api/v1/market/stream") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["private_reads_enabled"] is False
        assert hello["trading_enabled"] is False

        # Reject upstream URL injection.
        ws.send_json(
            {
                "op": "subscribe",
                "category": "linear",
                "symbols": ["BTCUSDT"],
                "interval": "15",
                "ws_url": "wss://evil.example",
            }
        )
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["reason"] == "upstream_url_fields_forbidden"

        ws.send_json(
            {
                "op": "subscribe",
                "category": "linear",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "interval": "15",
            }
        )
        sub = ws.receive_json()
        assert sub["type"] == "subscribed"
        assert sub["stream_mode"] == "public_ws"

        # status may arrive from manager
        # ping/pong
        ws.send_json({"op": "ping"})
        pong = ws.receive_json()
        assert pong.get("op") == "pong" or pong.get("type") == "status"

    reset_market_stream_hub_for_tests()


def test_disconnect_cleanup_stops_unused_manager() -> None:
    sockets: list[FakeWsSocket] = []

    def connect(url: str) -> FakeWsSocket:
        sock = FakeWsSocket()
        sockets.append(sock)
        sock.push({"success": True, "op": "subscribe", "ret_msg": "OK"})
        return sock

    hub = reset_market_stream_hub_for_tests(MarketStreamHub(connect_fn=connect))
    clear_settings_cache()
    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/api/v1/market/stream") as ws:
        ws.receive_json()  # hello
        ws.send_json(
            {
                "op": "subscribe",
                "category": "linear",
                "symbols": ["BTCUSDT"],
                "interval": "15",
            }
        )
        ws.receive_json()  # subscribed / status
    assert hub.client_count() == 0
    # Manager should be stopped/removed after last client.
    assert MarketCategory.linear not in hub._managers
    reset_market_stream_hub_for_tests()


def test_rest_routes_still_isolated_from_wallet_gate() -> None:
    clear_settings_cache()
    reset_market_stream_hub_for_tests()
    app = create_app()
    client = TestClient(app)
    # Market status does not enable private reads.
    st = client.get("/api/v1/market/status").json()
    assert st["private_reads_enabled"] is False
    assert st["trading_enabled"] is False
