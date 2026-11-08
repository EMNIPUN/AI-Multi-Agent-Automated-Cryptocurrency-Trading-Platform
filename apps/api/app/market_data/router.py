"""Public market-data HTTP API (no private credentials, no orders)."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.market_data.constants import (
    DEFAULT_SYMBOLS,
    INTERVAL_LABELS,
    KLINE_LIMIT_DEFAULT,
    ORDERBOOK_DEPTH_DEFAULT,
    SUPPORTED_INTERVALS,
    TRADES_LIMIT_DEFAULT,
)
from apps.api.app.market_data.rest_client import (
    BybitPublicRestClient,
    FakePublicTransport,
    HttpxPublicTransport,
)
from apps.api.app.market_data.schemas import (
    ConnectionState,
    KlinesResponse,
    MarketCategory,
    MarketStatus,
    OrderBookSnapshot,
    TickersResponse,
    TradesResponse,
)
from apps.api.app.market_data.ws_manager import PublicMarketWsManager

router = APIRouter(prefix="/api/v1/market", tags=["market-public"])


def _parse_category(raw: str) -> MarketCategory:
    try:
        return MarketCategory(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_category",
                "message": "category must be spot or linear (USDT perpetual)",
            },
        ) from exc


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return list(DEFAULT_SYMBOLS)
    symbols = [s.strip().upper() for s in raw.split(",") if s.strip()]
    if not symbols:
        return list(DEFAULT_SYMBOLS)
    # Soft cap for personal use.
    return symbols[:20]


def get_public_rest_client(request: Request) -> BybitPublicRestClient:
    existing = getattr(request.app.state, "bybit_public_rest", None)
    if existing is not None:
        return existing  # type: ignore[no-any-return]
    simulated = os.getenv("MARKET_DATA_SIMULATED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if simulated:
        client = BybitPublicRestClient(FakePublicTransport({}), simulated=True)
    else:
        client = BybitPublicRestClient(HttpxPublicTransport(), simulated=False)
    request.app.state.bybit_public_rest = client
    return client


@router.get("/status", response_model=MarketStatus)
def market_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> MarketStatus:
    manager: PublicMarketWsManager | None = getattr(
        request.app.state, "bybit_public_ws", None
    )
    if manager is not None:
        status = manager.status()
    else:
        status = MarketStatus(
            connection_state=ConnectionState.disconnected,
            data_path="public_rest_only",
            symbols=list(DEFAULT_SYMBOLS),
        )
    # Kill-switch isolation: never imply private/live trading from public path.
    status.private_reads_enabled = bool(settings.private_data_reads_enabled)
    status.trading_enabled = False
    return status


@router.get("/tickers", response_model=TickersResponse)
def market_tickers(
    client: Annotated[BybitPublicRestClient, Depends(get_public_rest_client)],
    category: str = Query(default="linear"),
    symbols: str | None = Query(default=None),
) -> TickersResponse:
    cat = _parse_category(category)
    try:
        return client.get_tickers(category=cat, symbols=_parse_symbols(symbols))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "ticker_fetch_failed", "type": type(exc).__name__},
        ) from exc


@router.get("/klines", response_model=KlinesResponse)
def market_klines(
    client: Annotated[BybitPublicRestClient, Depends(get_public_rest_client)],
    category: str = Query(default="linear"),
    symbol: str = Query(default="BTCUSDT"),
    interval: str = Query(default="15"),
    limit: int = Query(default=KLINE_LIMIT_DEFAULT, ge=1, le=1000),
) -> KlinesResponse:
    cat = _parse_category(category)
    if interval not in SUPPORTED_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_interval",
                "supported": list(SUPPORTED_INTERVALS),
                "labels": INTERVAL_LABELS,
            },
        )
    try:
        return client.get_klines(
            category=cat, symbol=symbol.upper(), interval=interval, limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "kline_fetch_failed", "type": type(exc).__name__},
        ) from exc


@router.get("/orderbook", response_model=OrderBookSnapshot)
def market_orderbook(
    client: Annotated[BybitPublicRestClient, Depends(get_public_rest_client)],
    category: str = Query(default="linear"),
    symbol: str = Query(default="BTCUSDT"),
    limit: int = Query(default=ORDERBOOK_DEPTH_DEFAULT, ge=1, le=200),
) -> OrderBookSnapshot:
    cat = _parse_category(category)
    try:
        return client.get_orderbook(
            category=cat, symbol=symbol.upper(), limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "orderbook_fetch_failed", "type": type(exc).__name__},
        ) from exc


@router.get("/trades", response_model=TradesResponse)
def market_trades(
    client: Annotated[BybitPublicRestClient, Depends(get_public_rest_client)],
    category: str = Query(default="linear"),
    symbol: str = Query(default="BTCUSDT"),
    limit: int = Query(default=TRADES_LIMIT_DEFAULT, ge=1, le=1000),
) -> TradesResponse:
    cat = _parse_category(category)
    try:
        return client.get_recent_trades(
            category=cat, symbol=symbol.upper(), limit=limit
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "trades_fetch_failed", "type": type(exc).__name__},
        ) from exc


@router.get("/meta")
def market_meta() -> dict[str, object]:
    return {
        "default_symbols": list(DEFAULT_SYMBOLS),
        "categories": {
            "spot": "Spot",
            "linear": "USDT perpetual",
        },
        "intervals": INTERVAL_LABELS,
        "auth_required": False,
        "private_endpoints": False,
        "orders_supported": False,
        "stream_path": "/api/v1/market/stream",
        "stream_note": "Public WS fan-out; browser cannot supply upstream URLs.",
        "note": (
            "Public Bybit V5 market data only. Not private wallet / binding / live trading."
        ),
    }
