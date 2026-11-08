"""Bybit V5 public REST client — no API keys, injectable transport for tests."""

from __future__ import annotations

import time
from typing import Any, Protocol

import httpx

from apps.api.app.market_data.candles import (
    interval_to_ms,
    parse_bybit_kline_row,
)
from apps.api.app.market_data.constants import (
    BYBIT_PUBLIC_REST_BASE,
    DATA_PATH_PUBLIC_LIVE,
    DATA_PATH_PUBLIC_SIMULATED,
    INTERVAL_LABELS,
    KLINE_LIMIT_DEFAULT,
    KLINE_LIMIT_MAX,
    ORDERBOOK_DEPTH_DEFAULT,
    REST_MIN_INTERVAL_SECONDS,
    TRADES_LIMIT_DEFAULT,
    TRADES_LIMIT_MAX,
)
from apps.api.app.market_data.indicators import compute_overlay_indicators
from apps.api.app.market_data.orderbook import OrderBookSynchronizer, parse_levels
from apps.api.app.market_data.schemas import (
    IndicatorSeries,
    KlinesResponse,
    MarketCategory,
    OrderBookSnapshot,
    PublicTrade,
    TickerSnapshot,
    TickersResponse,
    TradesResponse,
)


class HttpTransport(Protocol):
    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]: ...


class HttpxPublicTransport:
    """Real outbound transport to Bybit public REST (local development)."""

    def __init__(
        self,
        *,
        base_url: str = BYBIT_PUBLIC_REST_BASE,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._last_call = 0.0

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_call
        if elapsed < REST_MIN_INTERVAL_SECONDS:
            time.sleep(REST_MIN_INTERVAL_SECONDS - elapsed)
        response = self._client.get(path, params=params)
        self._last_call = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("malformed_exchange_response")
        return payload

    def close(self) -> None:
        if self._owns:
            self._client.close()


class FakePublicTransport:
    """Deterministic in-memory responses for unit tests (no network)."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((path, dict(params)))
        key = path
        if key not in self.responses:
            raise KeyError(f"no_fake_response_for:{path}")
        return self.responses[key]


class BybitPublicRestClient:
    """Read-only public market data. Never attaches API keys."""

    def __init__(
        self,
        transport: HttpTransport,
        *,
        simulated: bool = False,
    ) -> None:
        self._transport = transport
        self._simulated = simulated

    @property
    def data_path(self) -> str:
        return DATA_PATH_PUBLIC_SIMULATED if self._simulated else DATA_PATH_PUBLIC_LIVE

    def _require_ok(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("retCode") != 0:
            raise RuntimeError(str(payload.get("retMsg") or "bybit_error"))
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("malformed_result")
        return result

    def get_tickers(
        self,
        *,
        category: MarketCategory,
        symbols: list[str] | None = None,
    ) -> TickersResponse:
        params: dict[str, Any] = {"category": category.value}
        if symbols and len(symbols) == 1:
            params["symbol"] = symbols[0]
        result = self._require_ok(
            self._transport.get("/v5/market/tickers", params)
        )
        rows = result.get("list") or []
        if not isinstance(rows, list):
            raise ValueError("malformed_ticker_list")
        wanted = {s.upper() for s in symbols} if symbols else None
        tickers: list[TickerSnapshot] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if wanted is not None and symbol not in wanted:
                continue
            try:
                last = float(row.get("lastPrice") or 0)
            except (TypeError, ValueError):
                continue
            if last <= 0:
                continue
            tickers.append(
                TickerSnapshot(
                    symbol=symbol,
                    category=category,
                    last_price=last,
                    bid1=_f(row.get("bid1Price")),
                    ask1=_f(row.get("ask1Price")),
                    high_24h=_f(row.get("highPrice24h")),
                    low_24h=_f(row.get("lowPrice24h")),
                    volume_24h=_f(row.get("volume24h")),
                    turnover_24h=_f(row.get("turnover24h")),
                    price_24h_pct=_pct(row.get("price24hPcnt")),
                    mark_price=_f(row.get("markPrice")),
                    funding_rate=_f(row.get("fundingRate")),
                    open_interest=_f(row.get("openInterest")),
                )
            )
        return TickersResponse(
            category=category, data_path=self.data_path, tickers=tickers
        )

    def get_klines(
        self,
        *,
        category: MarketCategory,
        symbol: str,
        interval: str,
        limit: int = KLINE_LIMIT_DEFAULT,
        now_ms: int | None = None,
    ) -> KlinesResponse:
        if interval not in INTERVAL_LABELS:
            raise ValueError(f"unsupported_interval:{interval}")
        lim = max(1, min(int(limit), KLINE_LIMIT_MAX))
        result = self._require_ok(
            self._transport.get(
                "/v5/market/kline",
                {
                    "category": category.value,
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": lim,
                },
            )
        )
        rows = result.get("list") or []
        if not isinstance(rows, list):
            raise ValueError("malformed_kline_list")
        interval_ms = interval_to_ms(interval)
        clock = now_ms if now_ms is not None else int(time.time() * 1000)
        candles = []
        # Bybit returns newest first.
        for row in reversed(rows):
            start_ms = None
            try:
                if isinstance(row, (list, tuple)) and row:
                    start_ms = int(row[0])
            except (TypeError, ValueError):
                continue
            confirmed = True
            if start_ms is not None:
                confirmed = clock >= start_ms + interval_ms
            bar = parse_bybit_kline_row(row, confirmed=confirmed)
            if bar is None:
                continue
            # Exclude still-forming bar from strategy-grade series.
            if not confirmed:
                continue
            candles.append(bar)
        closes = [c.close for c in candles]
        ind = compute_overlay_indicators(closes)
        return KlinesResponse(
            category=category,
            symbol=symbol.upper(),
            interval=interval,
            interval_label=INTERVAL_LABELS[interval],
            data_path=self.data_path,
            candles=candles,
            indicators=IndicatorSeries(
                ema_20=ind["ema_20"],
                ema_50=ind["ema_50"],
                ema_200=ind["ema_200"],
                rsi_14=ind["rsi_14"],
            ),
            forming_excluded=True,
        )

    def get_orderbook(
        self,
        *,
        category: MarketCategory,
        symbol: str,
        limit: int = ORDERBOOK_DEPTH_DEFAULT,
    ) -> OrderBookSnapshot:
        lim = max(1, min(int(limit), 200))
        result = self._require_ok(
            self._transport.get(
                "/v5/market/orderbook",
                {
                    "category": category.value,
                    "symbol": symbol.upper(),
                    "limit": lim,
                },
            )
        )
        bids = parse_levels(result.get("b"))
        asks = parse_levels(result.get("a"))
        if bids is None or asks is None:
            raise ValueError("malformed_orderbook")
        sync = OrderBookSynchronizer(
            symbol=symbol.upper(), category=category, depth=lim
        )
        u = result.get("u")
        seq = result.get("seq")
        sync.apply_snapshot(
            bids=bids,
            asks=asks,
            update_id=int(u) if u is not None else None,
            sequence=int(seq) if seq is not None else None,
        )
        return sync.snapshot()

    def get_recent_trades(
        self,
        *,
        category: MarketCategory,
        symbol: str,
        limit: int = TRADES_LIMIT_DEFAULT,
    ) -> TradesResponse:
        lim = max(1, min(int(limit), TRADES_LIMIT_MAX))
        result = self._require_ok(
            self._transport.get(
                "/v5/market/recent-trade",
                {
                    "category": category.value,
                    "symbol": symbol.upper(),
                    "limit": lim,
                },
            )
        )
        rows = result.get("list") or []
        if not isinstance(rows, list):
            raise ValueError("malformed_trades")
        trades: list[PublicTrade] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                side_raw = str(row.get("side") or "")
                side = (
                    "Buy"
                    if side_raw == "Buy"
                    else "Sell"
                    if side_raw == "Sell"
                    else "Unknown"
                )
                trades.append(
                    PublicTrade(
                        symbol=symbol.upper(),
                        category=category,
                        trade_id=str(row.get("execId") or row.get("tradeId") or ""),
                        price=float(row["price"]),
                        size=float(row["size"]),
                        side=side,  # type: ignore[arg-type]
                        timestamp_ms=int(row.get("time") or 0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return TradesResponse(
            category=category,
            symbol=symbol.upper(),
            data_path=self.data_path,
            trades=trades,
        )


def _f(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pct(value: object) -> float | None:
    raw = _f(value)
    if raw is None:
        return None
    # Bybit price24hPcnt is a fraction (0.01 = 1%).
    return raw * 100.0
