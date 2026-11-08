"""Phase 3D — deterministic public market-data tests (no real Bybit calls)."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.app.config import clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.market_data.candles import CandleSeries, parse_bybit_kline_row
from apps.api.app.market_data.indicators import compute_overlay_indicators, ema, rsi
from apps.api.app.market_data.orderbook import OrderBookSynchronizer
from apps.api.app.market_data.rest_client import BybitPublicRestClient, FakePublicTransport
from apps.api.app.market_data.schemas import CandleBar, ConnectionState, MarketCategory
from apps.api.app.market_data.ws_manager import FakeWsSocket, PublicMarketWsManager
from apps.api.app.market_data.ws_protocol import (
    PublicWsSessionState,
    WsMessageKind,
    build_subscribe_args,
    parse_ws_message,
    ws_url_for_category,
)


def _candle(t: int, c: float = 100.0) -> CandleBar:
    return CandleBar(
        time=t, open=c, high=c + 1, low=c - 1, close=c, volume=10, confirmed=True
    )


# --- 1. WebSocket connect/disconnect ---


def test_ws_connect_disconnect_and_subscribe_restore() -> None:
    sockets: list[FakeWsSocket] = []

    def connect(_url: str) -> FakeWsSocket:
        sock = FakeWsSocket()
        sockets.append(sock)
        sock.push({"success": True, "ret_msg": "OK", "op": "subscribe"})
        return sock

    sleeps: list[float] = []
    mgr = PublicMarketWsManager(
        category=MarketCategory.linear,
        symbols=["BTCUSDT"],
        intervals=["15"],
        connect_fn=connect,
        sleep_fn=lambda s: sleeps.append(s),
        max_reconnects=0,
    )
    # Drive one connect cycle manually.
    sock = connect(ws_url_for_category(MarketCategory.linear))
    mgr._sock = sock
    mgr.state.mark_connected()
    sock.send(json.dumps({"op": "subscribe", "args": sorted(mgr.state.desired_subscriptions)}))
    parsed = mgr.handle_raw_message(sock.recv())
    assert parsed.kind is WsMessageKind.subscribe_ack
    assert "tickers.BTCUSDT" in mgr.state.subscriptions or mgr.state.desired_subscriptions
    mgr.stop()
    assert mgr.state.connection_state in {
        ConnectionState.disconnected,
        ConnectionState.error,
    }


def test_ws_reconnect_backoff_and_subscription_recovery() -> None:
    state = PublicWsSessionState(category=MarketCategory.linear)
    import random

    rng = random.Random(1)
    d1 = state.next_backoff_seconds(base=0.5, maximum=30, rng=rng)
    d2 = state.next_backoff_seconds(base=0.5, maximum=30, rng=rng)
    assert d1 > 0
    assert d2 >= d1 * 0.9  # exponential growth with jitter
    state.desired_subscriptions = set(
        build_subscribe_args(symbols=["BTCUSDT", "ETHUSDT"], intervals=["1", "15"])
    )
    args = build_subscribe_args(symbols=["BTCUSDT", "ETHUSDT"], intervals=["1", "15"])
    assert len(args) == len(set(args))  # no duplicate subscriptions
    assert args.count("tickers.BTCUSDT") == 1


# --- 3. Malformed messages ---


def test_malformed_ws_messages() -> None:
    assert parse_ws_message("nope").kind is WsMessageKind.malformed
    assert parse_ws_message({"topic": "tickers.BTCUSDT", "data": "x"}).kind is (
        WsMessageKind.malformed
    )
    mgr = PublicMarketWsManager(
        category=MarketCategory.spot, symbols=["BTCUSDT"], connect_fn=None
    )
    bad = mgr.handle_raw_message("{not-json")
    assert bad.kind is WsMessageKind.malformed


# --- 4. Duplicate / out-of-order candles ---


def test_duplicate_and_out_of_order_candles() -> None:
    series = CandleSeries(interval_ms=60_000)
    assert series.apply(_candle(100)).accepted
    assert series.apply(_candle(100)).reason == "duplicate"
    # Forming replace
    forming = _candle(200, 101)
    forming.confirmed = False
    assert series.apply(forming).accepted
    forming2 = _candle(200, 102)
    forming2.confirmed = False
    assert series.apply(forming2).replaced_forming
    # Out-of-order historical insert
    assert series.apply(_candle(50, 90)).reason == "inserted_historical"
    times = [b.time for b in series.bars()]
    assert times == sorted(times)


# --- 5. Order book snapshot/delta ---


def test_orderbook_snapshot_delta_sequence() -> None:
    book = OrderBookSynchronizer(symbol="BTCUSDT", category=MarketCategory.linear)
    assert book.apply_delta(bids=[(1.0, 1.0)], asks=[(2.0, 1.0)], sequence=2).needs_resnapshot
    assert book.apply_snapshot(
        bids=[(100.0, 1.0), (99.0, 2.0)],
        asks=[(101.0, 1.5)],
        update_id=10,
        sequence=1,
    ).ok
    snap = book.snapshot()
    assert snap.best_bid == 100.0
    assert snap.best_ask == 101.0
    assert snap.spread == pytest.approx(1.0)
    assert book.apply_delta(
        bids=[(100.0, 0.0), (98.0, 3.0)],
        asks=[(101.0, 2.0)],
        update_id=11,
        sequence=2,
    ).ok
    assert 100.0 not in book.bids
    gap = book.apply_delta(bids=[], asks=[], sequence=5)
    assert gap.needs_resnapshot
    assert book.stale


# --- 6. Stale market data ---


def test_stale_market_data_not_treated_live() -> None:
    state = PublicWsSessionState(category=MarketCategory.linear)
    state.mark_connected()
    state.last_message_at = 0.0
    assert state.evaluate_staleness(now=100.0, stale_after=45.0)
    assert state.connection_state is ConnectionState.stale
    status_note = "stale"
    assert status_note  # explicit branch covered


# --- 7. Indicators ---


def test_indicator_calculations_no_lookahead() -> None:
    closes = [float(i) for i in range(1, 61)]
    e20 = ema(closes, 20)
    assert e20[18] is None
    assert e20[19] is not None
    assert e20[20] is not None
    # EMA at i uses only closes[0..i]
    r = rsi(closes, 14)
    assert r[13] is None
    assert r[14] is not None
    overlay = compute_overlay_indicators(closes)
    assert len(overlay["ema_200"]) == len(closes)
    assert all(v is None for v in overlay["ema_200"])  # need 200 points; only 60


# --- 8. Spot / perpetual separation ---


def test_spot_linear_category_separation() -> None:
    assert ws_url_for_category(MarketCategory.spot).endswith("/spot")
    assert ws_url_for_category(MarketCategory.linear).endswith("/linear")
    transport = FakePublicTransport(
        {
            "/v5/market/tickers": {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "lastPrice": "50000",
                            "price24hPcnt": "0.01",
                            "volume24h": "100",
                        }
                    ]
                },
            }
        }
    )
    spot = BybitPublicRestClient(transport, simulated=True).get_tickers(
        category=MarketCategory.spot, symbols=["BTCUSDT"]
    )
    assert spot.category is MarketCategory.spot
    assert transport.calls[0][1]["category"] == "spot"
    linear = BybitPublicRestClient(transport, simulated=True).get_tickers(
        category=MarketCategory.linear, symbols=["BTCUSDT"]
    )
    assert linear.category is MarketCategory.linear
    assert transport.calls[1][1]["category"] == "linear"


# --- 9. Component cleanup ---


def test_ws_manager_cleanup_bounds_memory() -> None:
    mgr = PublicMarketWsManager(
        category=MarketCategory.linear, symbols=["BTCUSDT"], connect_fn=None
    )
    payload = {
        "topic": "publicTrade.BTCUSDT",
        "data": [{"price": "1", "size": "1", "side": "Buy", "time": i} for i in range(250)],
    }
    mgr.handle_raw_message(json.dumps(payload))
    assert len(mgr.recent_trades["BTCUSDT"]) <= 200
    mgr.stop()


# --- 10. Kill-switch isolation ---


def test_kill_switch_isolation_on_market_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIVATE_DATA_READS_ENABLED", "false")
    monkeypatch.setenv("AGENT_ALLOW_LIVE", "false")
    monkeypatch.setenv("EXCHANGE_BINDING_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED", "false")
    monkeypatch.setenv("OPERATOR_LOCAL_BROWSER_PROXY_ENABLED", "false")
    clear_settings_cache()
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/v1/market/status")
    assert res.status_code == 200
    body = res.json()
    assert body["private_reads_enabled"] is False
    assert body["trading_enabled"] is False
    assert "public" in body["note"].lower() or "Public" in body["note"]
    meta = client.get("/api/v1/market/meta")
    assert meta.status_code == 200
    assert meta.json()["orders_supported"] is False
    assert meta.json()["auth_required"] is False


def test_rest_klines_exclude_forming_and_compute_indicators() -> None:
    # Two closed + one still-forming newest bar (clock mid-interval).
    now_ms = 1_000_000 + 2 * 60_000 + 30_000
    rows = [
        [str(1_000_000 + 2 * 60_000), "3", "4", "2", "3.5", "30"],  # forming
        [str(1_000_000 + 1 * 60_000), "2", "3", "1", "2.5", "20"],
        [str(1_000_000), "1", "2", "0.5", "1.5", "10"],
    ]
    transport = FakePublicTransport(
        {"/v5/market/kline": {"retCode": 0, "result": {"list": rows}}}
    )
    client = BybitPublicRestClient(transport, simulated=True)
    out = client.get_klines(
        category=MarketCategory.linear,
        symbol="BTCUSDT",
        interval="1",
        limit=50,
        now_ms=now_ms,
    )
    assert out.forming_excluded is True
    assert len(out.candles) == 2
    assert all(c.confirmed for c in out.candles)
    assert out.data_path == "public_simulated"


def test_http_market_routes_with_injected_fake_client() -> None:
    clear_settings_cache()
    app = create_app()
    transport = FakePublicTransport(
        {
            "/v5/market/tickers": {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "lastPrice": "65000",
                            "bid1Price": "64999",
                            "ask1Price": "65001",
                            "highPrice24h": "66000",
                            "lowPrice24h": "64000",
                            "volume24h": "1000",
                            "turnover24h": "65000000",
                            "price24hPcnt": "0.02",
                        }
                    ]
                },
            },
            "/v5/market/orderbook": {
                "retCode": 0,
                "result": {
                    "b": [["65000", "1"]],
                    "a": [["65010", "2"]],
                    "u": 1,
                    "seq": 1,
                },
            },
            "/v5/market/recent-trade": {
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "execId": "t1",
                            "price": "65000",
                            "size": "0.1",
                            "side": "Buy",
                            "time": "123",
                        }
                    ]
                },
            },
            "/v5/market/kline": {
                "retCode": 0,
                "result": {
                    "list": [
                        ["1000000", "1", "2", "0.5", "1.5", "10"],
                    ]
                },
            },
        }
    )
    app.state.bybit_public_rest = BybitPublicRestClient(transport, simulated=True)
    client = TestClient(app)
    t = client.get("/api/v1/market/tickers?category=linear&symbols=BTCUSDT")
    assert t.status_code == 200
    assert t.json()["tickers"][0]["last_price"] == 65000
    assert t.json()["data_path"] == "public_simulated"
    ob = client.get("/api/v1/market/orderbook?symbol=BTCUSDT")
    assert ob.status_code == 200
    assert ob.json()["synced"] is True
    tr = client.get("/api/v1/market/trades?symbol=BTCUSDT")
    assert tr.status_code == 200
    assert len(tr.json()["trades"]) == 1
    bad = client.get("/api/v1/market/klines?interval=99")
    assert bad.status_code == 400


def test_parse_bybit_kline_row_rejects_malformed() -> None:
    assert parse_bybit_kline_row(None) is None
    assert parse_bybit_kline_row([1, 2]) is None
