from decimal import Decimal

from pybit.unified_trading import HTTP

from bot.api import call_api
from bot.market import get_symbol
from bot.utils import print_kv


def get_coin_wallet(session: HTTP, coin: str) -> Decimal | None:
    """Return wallet balance for a coin, or None if the request fails."""
    try:
        response = session.get_wallet_balance(accountType="UNIFIED", coin=coin)
        if response.get("retCode") != 0:
            return None
        accounts = (response.get("result") or {}).get("list") or []
        if not accounts:
            return None
        for item in accounts[0].get("coin") or []:
            if item.get("coin") == coin:
                return Decimal(item.get("walletBalance") or "0")
        return Decimal("0")
    except Exception:
        return None


def show_balance(session: HTTP) -> None:
    data = call_api(
        "Unified account balance",
        session.get_wallet_balance,
        accountType="UNIFIED",
    )
    if not data or not data.get("list"):
        print("No account data returned.")
        return

    account = data["list"][0]
    print_kv(
        account,
        (
            "totalEquity",
            "totalWalletBalance",
            "totalAvailableBalance",
            "totalPerpUPL",
            "totalInitialMargin",
            "totalMaintenanceMargin",
        ),
    )

    print("\nAssets with balance")
    for coin in account.get("coin", []):
        wallet = Decimal(coin.get("walletBalance") or "0")
        if wallet == 0:
            continue
        print(
            coin.get("coin"),
            "wallet =", coin.get("walletBalance"),
            "available =", coin.get("availableToWithdraw") or coin.get("equity"),
            "equity =", coin.get("equity"),
            "uPnL =", coin.get("unrealisedPnl"),
        )


def show_positions(session: HTTP, ask_for_symbol: bool = True) -> None:
    kwargs = {"category": "linear", "settleCoin": "USDT"}
    if ask_for_symbol:
        symbol = get_symbol()
        if symbol:
            kwargs = {"category": "linear", "symbol": symbol}

    data = call_api("USDT perpetual positions", session.get_positions, **kwargs)
    if not data:
        return

    open_positions = [
        pos for pos in data.get("list", [])
        if Decimal(pos.get("size") or "0") != 0
    ]
    if not open_positions:
        print("No open positions.")
        return

    for pos in open_positions:
        print()
        print_kv(
            pos,
            (
                "symbol",
                "side",
                "size",
                "avgPrice",
                "markPrice",
                "liqPrice",
                "leverage",
                "unrealisedPnl",
                "takeProfit",
                "stopLoss",
            ),
        )


def show_open_orders(session: HTTP, category: str) -> None:
    symbol = get_symbol()
    data = call_api(
        "Open orders",
        session.get_open_orders,
        category=category,
        symbol=symbol,
        openOnly=0,
        limit=50,
    )
    if not data:
        return

    orders = data.get("list") or []
    if not orders:
        print("No open orders.")
        return

    for order in orders:
        print(
            order.get("orderId"),
            order.get("side"),
            order.get("orderType"),
            "qty=", order.get("qty"),
            "price=", order.get("price"),
            "status=", order.get("orderStatus"),
        )
