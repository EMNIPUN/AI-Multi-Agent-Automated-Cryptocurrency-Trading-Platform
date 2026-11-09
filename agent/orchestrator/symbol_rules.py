"""Bybit linear qty/price rounding for orchestrator live orders."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Any

# Fallbacks when instruments-info is unavailable (HYPE: qtyStep 0.01, tick 0.001).
_DEFAULT_QTY_STEP: dict[str, str] = {
    "HYPEUSDT": "0.01",
    "BTCUSDT": "0.001",
    "ETHUSDT": "0.01",
    "SOLUSDT": "0.1",
    "BNBUSDT": "0.01",
    "XRPUSDT": "0.1",
    "DOGEUSDT": "1",
}
_DEFAULT_TICK: dict[str, str] = {
    "HYPEUSDT": "0.001",
    "BTCUSDT": "0.1",
    "ETHUSDT": "0.01",
    "SOLUSDT": "0.01",
    "BNBUSDT": "0.01",
    "XRPUSDT": "0.0001",
    "DOGEUSDT": "0.00001",
}
_DEFAULT_MIN_QTY: dict[str, str] = {
    "HYPEUSDT": "0.01",
    "BTCUSDT": "0.001",
    "ETHUSDT": "0.01",
}
_DEFAULT_MIN_NOTIONAL = Decimal("5")


def _dec(value: Any, fallback: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal(fallback)


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def rules_for(symbol: str, instrument: dict[str, Any] | None = None) -> dict[str, Decimal]:
    sym = str(symbol or "").upper()
    lot = (instrument or {}).get("lotSizeFilter") if isinstance(instrument, dict) else None
    price_filter = (instrument or {}).get("priceFilter") if isinstance(instrument, dict) else None
    lot = lot if isinstance(lot, dict) else {}
    price_filter = price_filter if isinstance(price_filter, dict) else {}
    return {
        "qty_step": _dec(lot.get("qtyStep") or _DEFAULT_QTY_STEP.get(sym, "0.01"), "0.01"),
        "min_qty": _dec(lot.get("minOrderQty") or _DEFAULT_MIN_QTY.get(sym, "0.01"), "0.01"),
        "min_notional": _dec(lot.get("minNotionalValue") or _DEFAULT_MIN_NOTIONAL, "5"),
        "tick_size": _dec(price_filter.get("tickSize") or _DEFAULT_TICK.get(sym, "0.01"), "0.01"),
    }


def fetch_instrument_public(symbol: str, category: str = "linear") -> dict[str, Any] | None:
    """Best-effort public instruments-info (no API key)."""
    try:
        import httpx

        response = httpx.get(
            "https://api.bybit.com/v5/market/instruments-info",
            params={"category": category or "linear", "symbol": str(symbol).upper()},
            timeout=8.0,
        )
        payload = response.json()
        if int(payload.get("retCode", -1)) != 0:
            return None
        rows = (payload.get("result") or {}).get("list") or []
        return rows[0] if rows and isinstance(rows[0], dict) else None
    except Exception:  # noqa: BLE001
        return None


def normalize_qty(
    symbol: str,
    qty: Any,
    *,
    price: float | None = None,
    instrument: dict[str, Any] | None = None,
) -> str | None:
    """Floor qty to Bybit qtyStep; enforce min qty / min notional when possible."""
    raw = _dec(qty, "0")
    if raw <= 0:
        return None
    rules = rules_for(symbol, instrument)
    stepped = _floor_to_step(raw, rules["qty_step"])
    if stepped < rules["min_qty"]:
        stepped = rules["min_qty"]
    if price and price > 0 and rules["min_notional"] > 0:
        notional = stepped * _dec(price)
        if notional < rules["min_notional"]:
            need = rules["min_notional"] / _dec(price)
            stepped = _floor_to_step(need, rules["qty_step"])
            if stepped * _dec(price) < rules["min_notional"]:
                stepped = stepped + rules["qty_step"]
            if stepped < rules["min_qty"]:
                stepped = rules["min_qty"]
    if stepped <= 0:
        return None
    return _fmt(stepped)


def normalize_price(
    symbol: str,
    price: Any,
    *,
    instrument: dict[str, Any] | None = None,
) -> str | None:
    raw = _dec(price, "0")
    if raw <= 0:
        return None
    rules = rules_for(symbol, instrument)
    stepped = _floor_to_step(raw, rules["tick_size"])
    if stepped <= 0:
        return None
    return _fmt(stepped)
