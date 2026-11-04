from decimal import Decimal

from pybit.unified_trading import HTTP

from bot.account import get_coin_wallet
from bot.api import call_api
from bot.config import env_label, is_live_mainnet
from bot.market import (
    ask_price,
    ask_qty,
    get_last_price,
    get_symbol,
    normalize_qty,
    split_symbol,
)
from bot.utils import ask, ask_choice, confirm, format_decimal, to_decimal


def _confirm_order(summary: str) -> bool:
    print("\nOrder preview")
    print(summary)
    print(f"Environment: {env_label()}")
    if is_live_mainnet():
        print("WARNING: This is LIVE MAINNET — real funds will be used.")
        return confirm("Place this live order?", require_yes=True)
    return confirm("Place this order?")


def place_spot_order(session: HTTP) -> None:
    symbol = get_symbol()
    base, quote = split_symbol(symbol)
    side_key = ask_choice(
        "Side",
        {"1": "Buy", "2": "Sell"},
    )
    if side_key is None:
        return
    side = "Buy" if side_key == "1" else "Sell"

    type_key = ask_choice(
        "Order type",
        {"1": "Market", "2": "Limit"},
    )
    if type_key is None:
        return
    order_type = "Market" if type_key == "1" else "Limit"

    wallet = get_coin_wallet(session, base if side == "Sell" else (quote or "USDT"))
    if wallet is not None:
        print(
            f"Available {base if side == 'Sell' else (quote or 'USDT')}: "
            f"{format_decimal(wallet)}"
        )

    qty = ask_qty(session, "spot", symbol, allow_all=(side == "Sell"))
    if not qty:
        return

    if qty == "ALL":
        if wallet is None or wallet <= 0:
            print(f"No {base} balance to sell.")
            return
        qty = normalize_qty(session, "spot", symbol, wallet)
        if not qty:
            return
        print(f"Using full balance: {qty} {base}")

    qty_dec = Decimal(qty)
    if side == "Sell" and wallet is not None and qty_dec > wallet:
        print(
            f"Not enough {base}. You have {format_decimal(wallet)}, "
            f"but asked to sell {qty}."
        )
        print(f"Tip: use quantity like {format_decimal(wallet)} or type 'all'.")
        return

    if side == "Buy" and wallet is not None:
        last = get_last_price(session, "spot", symbol)
        if last and last > 0:
            cost = qty_dec * last
            if cost > wallet:
                print(
                    f"Not enough {quote or 'USDT'}. Need ≈ {format_decimal(cost)}, "
                    f"have {format_decimal(wallet)}."
                )
                max_qty = normalize_qty(session, "spot", symbol, wallet / last)
                if max_qty:
                    print(f"Max affordable ≈ {max_qty} {base}")
                return

    params = {
        "category": "spot",
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": qty,
        "timeInForce": "GTC" if order_type == "Limit" else "IOC",
    }

    if order_type == "Limit":
        price = ask_price(session, "spot", symbol)
        if not price:
            return
        params["price"] = price

    last = get_last_price(session, "spot", symbol)
    est = ""
    if last and last > 0:
        est = f" (≈ {format_decimal(qty_dec * last)} {quote or 'USDT'})"

    summary = (
        f"SPOT {side} {order_type} {qty} {base}{est}"
        + (f" @ {params.get('price')}" if "price" in params else "")
    )
    if not _confirm_order(summary):
        return

    result = call_api("Place spot order", session.place_order, **params)
    if result:
        print("Order submitted.")
        print("orderId:", result.get("orderId"))
        print("orderLinkId:", result.get("orderLinkId"))


def _get_position_size(session: HTTP, symbol: str) -> tuple[Decimal, str | None]:
    """Return (size, side) for an open linear position, or (0, None)."""
    try:
        response = session.get_positions(category="linear", symbol=symbol)
        if response.get("retCode") != 0:
            return Decimal("0"), None
        for pos in (response.get("result") or {}).get("list") or []:
            size = Decimal(pos.get("size") or "0")
            if size > 0:
                return size, pos.get("side")
    except Exception:
        pass
    return Decimal("0"), None


def place_futures_order(session: HTTP) -> None:
    symbol = get_symbol()
    base, _ = split_symbol(symbol)
    side_key = ask_choice(
        "Side",
        {"1": "Buy / Long", "2": "Sell / Short"},
    )
    if side_key is None:
        return
    side = "Buy" if side_key == "1" else "Sell"

    type_key = ask_choice(
        "Order type",
        {"1": "Market", "2": "Limit"},
    )
    if type_key is None:
        return
    order_type = "Market" if type_key == "1" else "Limit"

    pos_size, pos_side = _get_position_size(session, symbol)
    if pos_size > 0:
        print(f"Open position: {pos_side} {format_decimal(pos_size)} {base}")
    else:
        print("No open position on this symbol.")
        print("To open a new trade: enter a numeric qty and reduce-only = n")
        print("To close a position: use menu option 4, or reduce-only = y")

    reduce_only = ask("Reduce-only? (y/n)", "n").lower() in {"y", "yes"}

    qty = ask_qty(session, "linear", symbol, allow_all=reduce_only)
    if not qty:
        return

    if qty == "ALL":
        if not reduce_only:
            print("'all' needs reduce-only = y (closing/reducing a position).")
            return
        if pos_size <= 0:
            print("No position to close. Open one first with a numeric qty.")
            return
        # Closing side must be opposite of position side
        needed_side = "Sell" if pos_side == "Buy" else "Buy"
        if side != needed_side:
            print(
                f"Position is {pos_side}. To reduce/close use side "
                f"{'2 Sell' if needed_side == 'Sell' else '1 Buy'}."
            )
            return
        qty = normalize_qty(session, "linear", symbol, pos_size)
        if not qty:
            return
        print(f"Using full position size: {qty} {base}")

    params = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": qty,
        "timeInForce": "GTC" if order_type == "Limit" else "IOC",
        "positionIdx": 0,  # one-way mode
    }

    if order_type == "Limit":
        price = ask_price(session, "linear", symbol)
        if not price:
            return
        params["price"] = price

    tp = ask("Take profit price (blank to skip)", "")
    sl = ask("Stop loss price (blank to skip)", "")
    if tp:
        params["takeProfit"] = tp
    if sl:
        params["stopLoss"] = sl

    if reduce_only:
        params["reduceOnly"] = True

    summary = (
        f"FUTURES {side} {order_type} {qty} {symbol}"
        + (f" @ {params.get('price')}" if "price" in params else "")
        + (f" TP={tp}" if tp else "")
        + (f" SL={sl}" if sl else "")
        + (" reduceOnly" if reduce_only else "")
    )
    if not _confirm_order(summary):
        return

    result = call_api("Place futures order", session.place_order, **params)
    if result:
        print("Order submitted.")
        print("orderId:", result.get("orderId"))
        print("orderLinkId:", result.get("orderLinkId"))


def set_leverage(session: HTTP) -> None:
    symbol = get_symbol()
    leverage = ask("Leverage (e.g. 5)", "5")
    if to_decimal(leverage, "leverage") is None:
        return

    if not confirm(f"Set {symbol} leverage to {leverage}x?"):
        print("Cancelled.")
        return

    print("\n--- Set leverage ---")
    try:
        response = session.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=leverage,
            sellLeverage=leverage,
        )
        code = response.get("retCode")
        # 110043 = leverage not modified (already set)
        if code in (0, 110043):
            print("Leverage ready:", leverage + "x")
        else:
            print("API error:", response.get("retMsg"))
    except Exception as exc:
        print("Request failed:", exc)


def close_futures_position(session: HTTP) -> None:
    symbol = get_symbol()
    data = call_api(
        "Current position",
        session.get_positions,
        category="linear",
        symbol=symbol,
    )
    if not data:
        return

    positions = [
        pos for pos in data.get("list", [])
        if Decimal(pos.get("size") or "0") != 0
    ]
    if not positions:
        print("No open position for this symbol.")
        return

    pos = positions[0]
    size = Decimal(pos.get("size") or "0")
    side = pos.get("side")
    close_side = "Sell" if side == "Buy" else "Buy"
    qty = normalize_qty(session, "linear", symbol, size)
    if not qty:
        return

    summary = f"CLOSE FUTURES position: {side} {qty} {symbol} via market {close_side}"
    if not _confirm_order(summary):
        return

    result = call_api(
        "Close position",
        session.place_order,
        category="linear",
        symbol=symbol,
        side=close_side,
        orderType="Market",
        qty=qty,
        timeInForce="IOC",
        reduceOnly=True,
        positionIdx=0,
    )
    if result:
        print("Close order submitted.")
        print("orderId:", result.get("orderId"))


def cancel_order(session: HTTP, category: str) -> None:
    symbol = get_symbol()
    order_id = ask("Order ID to cancel")
    if not order_id:
        print("Order ID required.")
        return

    if not confirm(f"Cancel order {order_id} on {symbol}?"):
        print("Cancelled.")
        return

    result = call_api(
        "Cancel order",
        session.cancel_order,
        category=category,
        symbol=symbol,
        orderId=order_id,
    )
    if result:
        print("Cancel requested for", result.get("orderId"))


def cancel_all_orders(session: HTTP, category: str) -> None:
    symbol = ask("Symbol (blank = all in category)", "")
    label = symbol or f"ALL {category}"
    if not confirm(f"Cancel ALL open {category} orders for {label}?"):
        print("Cancelled.")
        return

    params = {"category": category}
    if symbol:
        params["symbol"] = symbol.upper()

    result = call_api("Cancel all orders", session.cancel_all_orders, **params)
    if result is not None:
        print("Cancel-all submitted.")
