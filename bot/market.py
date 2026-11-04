import time
from decimal import Decimal

from pybit.unified_trading import HTTP

from bot.api import call_api
from bot.utils import ask, floor_to_step, format_decimal, print_kv, to_decimal

_instrument_cache: dict[tuple[str, str], dict] = {}


def get_symbol(default: str = "BTCUSDT") -> str:
    return ask("Trading pair", default).upper()


def show_ticker(session: HTTP, category: str) -> None:
    symbol = get_symbol()
    data = call_api(
        "Ticker",
        session.get_tickers,
        category=category,
        symbol=symbol,
    )
    if not data or not data.get("list"):
        print("No ticker data. Check the symbol and market.")
        return

    ticker = data["list"][0]
    print("Symbol:", symbol)
    print_kv(
        ticker,
        (
            "lastPrice",
            "highPrice24h",
            "lowPrice24h",
            "turnover24h",
            "bid1Price",
            "ask1Price",
        ),
    )
    print("24h change (%):", Decimal(ticker.get("price24hPcnt", "0")) * 100)
    if category == "linear":
        print_kv(ticker, ("markPrice", "fundingRate", "openInterest"))


def show_orderbook(session: HTTP, category: str) -> None:
    symbol = get_symbol()
    data = call_api(
        "Order book",
        session.get_orderbook,
        category=category,
        symbol=symbol,
        limit=10,
    )
    if not data:
        return

    print("\nTop asks (price, quantity)")
    for price, qty in reversed(data.get("a", [])):
        print(price, qty)

    print("\nTop bids (price, quantity)")
    for price, qty in data.get("b", []):
        print(price, qty)


def show_candles(session: HTTP, category: str) -> None:
    symbol = get_symbol()
    interval = ask("Interval (1,3,5,15,60,D)", "15")
    data = call_api(
        "Candles",
        session.get_kline,
        category=category,
        symbol=symbol,
        interval=interval,
        limit=10,
    )
    if not data or not data.get("list"):
        print("No candle data.")
        return

    print("Time (ms) | Open | High | Low | Close | Volume")
    for candle in reversed(data["list"]):
        print(" | ".join(str(value) for value in candle[:6]))


def get_instrument(session: HTTP, category: str, symbol: str) -> dict | None:
    cache_key = (category, symbol)
    if cache_key in _instrument_cache:
        return _instrument_cache[cache_key]

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = session.get_instruments_info(
                category=category,
                symbol=symbol,
            )
            if response.get("retCode") != 0:
                print("API error:", response.get("retMsg"))
                return None
            items = (response.get("result") or {}).get("list") or []
            if not items:
                print("Unknown symbol for this market.")
                return None
            _instrument_cache[cache_key] = items[0]
            return items[0]
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                print(f"Network blip loading symbol rules ({attempt}/3), retrying...")
                time.sleep(attempt)
                continue
            print("Request failed:", last_error)
            return None
    return None


def normalize_qty(session: HTTP, category: str, symbol: str, qty: Decimal) -> str | None:
    instrument = get_instrument(session, category, symbol)
    if not instrument:
        return None

    lot = instrument.get("lotSizeFilter") or {}
    step = Decimal(lot.get("qtyStep") or lot.get("basePrecision") or "0.0001")
    min_qty = Decimal(lot.get("minOrderQty") or "0")
    max_qty = Decimal(lot.get("maxOrderQty") or "0")

    rounded = floor_to_step(qty, step)
    if rounded < min_qty:
        print(f"Quantity too small. Minimum is {min_qty}, step is {step}.")
        return None
    if max_qty > 0 and rounded > max_qty:
        print(f"Quantity too large. Maximum is {max_qty}.")
        return None
    return format_decimal(rounded)


def normalize_price(session: HTTP, category: str, symbol: str, price: Decimal) -> str | None:
    instrument = get_instrument(session, category, symbol)
    if not instrument:
        return None

    tick = Decimal((instrument.get("priceFilter") or {}).get("tickSize") or "0.01")
    rounded = floor_to_step(price, tick)
    if rounded <= 0:
        print("Price too small after rounding.")
        return None
    return format_decimal(rounded)


def get_last_price(session: HTTP, category: str, symbol: str) -> Decimal | None:
    try:
        response = session.get_tickers(category=category, symbol=symbol)
        if response.get("retCode") != 0:
            return None
        items = (response.get("result") or {}).get("list") or []
        if not items:
            return None
        return Decimal(items[0].get("lastPrice") or "0")
    except Exception:
        return None


def split_symbol(symbol: str) -> tuple[str, str]:
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, ""


def ask_qty(
    session: HTTP,
    category: str,
    symbol: str,
    *,
    allow_all: bool = False,
) -> str | None:
    base, quote = split_symbol(symbol)
    last = get_last_price(session, category, symbol)
    instrument = get_instrument(session, category, symbol)
    min_qty = None
    if instrument:
        lot = instrument.get("lotSizeFilter") or {}
        min_qty = lot.get("minOrderQty")
        if min_qty:
            print(f"Minimum qty for {symbol}: {min_qty} {base}")

    if last and last > 0:
        print(
            f"{symbol} last ≈ {format_decimal(last)} {quote or ''}. "
            f"Quantity is in {base} (not {quote or 'USDT'})."
        )
        example = Decimal("5") / last
        if min_qty:
            example = max(example, Decimal(min_qty))
        print(f"Example: enter {format_decimal(example)} {base}")

    hint = f"Quantity ({base} amount"
    if allow_all:
        hint += ", or 'all' to use full position"
    hint += ")"
    raw = ask(hint)
    if raw.lower() == "all":
        if not allow_all:
            print("'all' is only for closing/reducing a position. Enter a number.")
            return None
        return "ALL"

    qty = to_decimal(raw, "quantity")
    if qty is None:
        return None

    normalized = normalize_qty(session, category, symbol, qty)
    if not normalized or not last or last <= 0:
        return normalized

    notional = Decimal(normalized) * last
    print(f"≈ {format_decimal(notional)} {quote or 'USDT'} notional at last price")
    if category == "linear":
        print("(Futures: margin used is roughly notional / leverage)")
    if notional > Decimal("50"):
        print("Warning: that is a large notional vs a small account — double-check units.")
    return normalized


def ask_price(session: HTTP, category: str, symbol: str) -> str | None:
    raw = ask("Limit price")
    price = to_decimal(raw, "price")
    if price is None:
        return None
    return normalize_price(session, category, symbol, price)
