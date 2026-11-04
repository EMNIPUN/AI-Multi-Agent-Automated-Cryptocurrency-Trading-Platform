from dataclasses import dataclass

from pybit.unified_trading import HTTP


@dataclass(frozen=True)
class Candle:
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_candles(
    session: HTTP,
    category: str,
    symbol: str,
    interval: str,
    limit: int = 120,
) -> list[Candle]:
    """Return oldest→newest candles for indicator math."""
    response = session.get_kline(
        category=category,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )
    if response.get("retCode") != 0:
        raise RuntimeError(response.get("retMsg") or "kline error")

    rows = (response.get("result") or {}).get("list") or []
    candles: list[Candle] = []
    # Bybit returns newest first
    for row in reversed(rows):
        candles.append(
            Candle(
                start=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    return candles


def ema(values: list[float], period: int) -> list[float | None]:
    if period <= 0 or not values:
        return [None] * len(values)
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    mult = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * mult + prev
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100 - (100 / (1 + rs))
    return out


def get_equity(session: HTTP) -> float | None:
    try:
        response = session.get_wallet_balance(accountType="UNIFIED")
        if response.get("retCode") != 0:
            return None
        accounts = (response.get("result") or {}).get("list") or []
        if not accounts:
            return None
        return float(accounts[0].get("totalEquity") or 0)
    except Exception:
        return None


def get_last_price(session: HTTP, category: str, symbol: str) -> float | None:
    try:
        response = session.get_tickers(category=category, symbol=symbol)
        if response.get("retCode") != 0:
            return None
        items = (response.get("result") or {}).get("list") or []
        if not items:
            return None
        return float(items[0].get("lastPrice") or 0) or None
    except Exception:
        return None


def get_position(session: HTTP, category: str, symbol: str) -> dict | None:
    """Return open position dict for linear, or spot-like holdings summary."""
    if category == "linear":
        try:
            response = session.get_positions(category="linear", symbol=symbol)
            if response.get("retCode") != 0:
                return None
            for pos in (response.get("result") or {}).get("list") or []:
                size = float(pos.get("size") or 0)
                if size > 0:
                    return {
                        "symbol": symbol,
                        "side": pos.get("side"),
                        "size": size,
                        "avgPrice": float(pos.get("avgPrice") or 0),
                        "unrealisedPnl": float(pos.get("unrealisedPnl") or 0),
                    }
            return None
        except Exception:
            return None

    # Spot: treat base wallet > 0 as a long inventory position
    from bot.market import split_symbol

    base, _ = split_symbol(symbol)
    try:
        response = session.get_wallet_balance(accountType="UNIFIED", coin=base)
        if response.get("retCode") != 0:
            return None
        accounts = (response.get("result") or {}).get("list") or []
        if not accounts:
            return None
        for coin in accounts[0].get("coin") or []:
            if coin.get("coin") == base:
                size = float(coin.get("walletBalance") or 0)
                if size > 0:
                    return {
                        "symbol": symbol,
                        "side": "Buy",
                        "size": size,
                        "avgPrice": 0.0,
                        "unrealisedPnl": 0.0,
                    }
        return None
    except Exception:
        return None
