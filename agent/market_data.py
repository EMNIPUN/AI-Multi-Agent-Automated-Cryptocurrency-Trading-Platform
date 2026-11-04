from dataclasses import dataclass
from enum import Enum

from pybit.unified_trading import HTTP


@dataclass(frozen=True)
class Candle:
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class PositionStatus(str, Enum):
    """Confirmed exchange position state for fail-closed trading decisions."""

    FLAT = "flat"
    OPEN = "open"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PositionSnapshot:
    """Result of a position query. Only FLAT may be treated as no exposure."""

    status: PositionStatus
    position: dict | None = None
    reason: str = ""

    @property
    def is_flat(self) -> bool:
        return self.status is PositionStatus.FLAT

    @property
    def is_open(self) -> bool:
        return self.status is PositionStatus.OPEN

    @property
    def is_unknown(self) -> bool:
        return self.status is PositionStatus.UNKNOWN


def _unknown(reason: str) -> PositionSnapshot:
    return PositionSnapshot(status=PositionStatus.UNKNOWN, reason=reason)


def _open_position(symbol: str, side: str, size: float, avg_price: float, upnl: float) -> PositionSnapshot:
    return PositionSnapshot(
        status=PositionStatus.OPEN,
        position={
            "symbol": symbol,
            "side": side,
            "size": size,
            "avgPrice": avg_price,
            "unrealisedPnl": upnl,
        },
    )


def _parse_linear_row(symbol: str, pos: object) -> PositionSnapshot | None:
    """Return OPEN snapshot, None if size is flat, or UNKNOWN on bad row data."""
    if not isinstance(pos, dict):
        return _unknown("malformed position row: expected object")
    try:
        size = float(pos.get("size") or 0)
    except (TypeError, ValueError):
        return _unknown("malformed position row: invalid size")
    if size <= 0:
        return None
    side = pos.get("side")
    if side not in {"Buy", "Sell"}:
        return _unknown("malformed position row: invalid or missing side")
    try:
        avg_price = float(pos.get("avgPrice") or 0)
        upnl = float(pos.get("unrealisedPnl") or 0)
    except (TypeError, ValueError):
        return _unknown("malformed position row: invalid avgPrice/unrealisedPnl")
    return _open_position(symbol, side, size, avg_price, upnl)


def fetch_candles(
    session: HTTP,
    category: str,
    symbol: str,
    interval: str,
    limit: int = 120,
) -> list[Candle]:
    """
    Fetch Bybit V5 klines and return oldest→newest candles.

    IMPORTANT: The newest REST candle is often still *forming*. Never treat
    this series as closed-bar input. Callers must run
    ``filter_confirmed_candles`` (Phase 1D) before strategy evaluation.
    """
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
    # Bybit returns newest first; reverse to chronological order.
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


def get_position(session: HTTP, category: str, symbol: str) -> PositionSnapshot:
    """Query position state. Errors and ambiguous payloads are UNKNOWN, never FLAT."""
    if category == "linear":
        return _get_linear_position(session, symbol)
    if category == "spot":
        return _get_spot_inventory(session, symbol)
    return _unknown(f"unsupported category for position query: {category}")


def _get_linear_position(session: HTTP, symbol: str) -> PositionSnapshot:
    try:
        response = session.get_positions(category="linear", symbol=symbol)
    except TimeoutError as exc:
        return _unknown(f"position query timeout: {exc}")
    except OSError as exc:
        return _unknown(f"position query network error: {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001 — exchange client may raise varied types
        return _unknown(f"position query failed: {type(exc).__name__}")

    if not isinstance(response, dict):
        return _unknown("malformed position response: expected object")

    ret_code = response.get("retCode")
    if ret_code != 0:
        msg = response.get("retMsg") or "unknown api error"
        return _unknown(f"position api error retCode={ret_code}: {msg}")

    result = response.get("result")
    if not isinstance(result, dict):
        return _unknown("malformed position response: missing result object")

    if "list" not in result:
        return _unknown("malformed position response: missing result.list")

    items = result.get("list")
    if not isinstance(items, list):
        return _unknown("malformed position response: result.list is not a list")

    # Confirmed empty list from a successful API call => FLAT
    open_snapshot: PositionSnapshot | None = None
    for pos in items:
        parsed = _parse_linear_row(symbol, pos)
        if parsed is None:
            continue
        if parsed.is_unknown:
            return parsed
        if parsed.is_open:
            if open_snapshot is not None:
                return _unknown("ambiguous position response: multiple open rows")
            open_snapshot = parsed

    if open_snapshot is not None:
        return open_snapshot
    return PositionSnapshot(status=PositionStatus.FLAT)


def _get_spot_inventory(session: HTTP, symbol: str) -> PositionSnapshot:
    # Spot: treat base wallet > 0 as a long inventory position
    from bot.market import split_symbol

    base, _ = split_symbol(symbol)
    try:
        response = session.get_wallet_balance(accountType="UNIFIED", coin=base)
    except TimeoutError as exc:
        return _unknown(f"spot balance query timeout: {exc}")
    except OSError as exc:
        return _unknown(f"spot balance query network error: {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        return _unknown(f"spot balance query failed: {type(exc).__name__}")

    if not isinstance(response, dict):
        return _unknown("malformed spot balance response: expected object")

    ret_code = response.get("retCode")
    if ret_code != 0:
        msg = response.get("retMsg") or "unknown api error"
        return _unknown(f"spot balance api error retCode={ret_code}: {msg}")

    result = response.get("result")
    if not isinstance(result, dict):
        return _unknown("malformed spot balance response: missing result object")
    if "list" not in result:
        return _unknown("malformed spot balance response: missing result.list")

    accounts = result.get("list")
    if not isinstance(accounts, list):
        return _unknown("malformed spot balance response: result.list is not a list")
    if not accounts:
        return _unknown("ambiguous spot balance response: empty account list")

    account = accounts[0]
    if not isinstance(account, dict):
        return _unknown("malformed spot balance response: account row invalid")

    coins = account.get("coin")
    if coins is None:
        return _unknown("malformed spot balance response: missing coin list")
    if not isinstance(coins, list):
        return _unknown("malformed spot balance response: coin is not a list")

    for coin in coins:
        if not isinstance(coin, dict):
            return _unknown("malformed spot balance response: coin row invalid")
        if coin.get("coin") != base:
            continue
        try:
            size = float(coin.get("walletBalance") or 0)
        except (TypeError, ValueError):
            return _unknown("malformed spot balance response: invalid walletBalance")
        if size > 0:
            return _open_position(symbol, "Buy", size, 0.0, 0.0)
        return PositionSnapshot(status=PositionStatus.FLAT)

    # Successful response that does not list the base coin => confirmed zero inventory
    return PositionSnapshot(status=PositionStatus.FLAT)
