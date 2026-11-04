"""Bybit terminal trading bot — spot + USDT perpetual futures."""

from bot.account import show_balance, show_open_orders, show_positions
from bot.client import create_session
from bot.config import API_KEY, API_SECRET, env_label, is_live_mainnet
from bot.market import show_candles, show_orderbook, show_ticker
from bot.trading import (
    cancel_all_orders,
    cancel_order,
    close_futures_position,
    place_futures_order,
    place_spot_order,
    set_leverage,
)


def market_menu(session, category: str, title: str) -> None:
    while True:
        print(f"\n--- {title} market ---")
        print("1. Ticker")
        print("2. Order book")
        print("3. Candles")
        print("0. Back")
        choice = input("Choose: ").strip()
        if choice == "1":
            show_ticker(session, category)
        elif choice == "2":
            show_orderbook(session, category)
        elif choice == "3":
            show_candles(session, category)
        elif choice == "0":
            return
        else:
            print("Invalid choice.")


def spot_trade_menu(session) -> None:
    while True:
        print("\n--- Spot trading ---")
        print("1. Place order (market / limit)")
        print("2. Open orders")
        print("3. Cancel order")
        print("4. Cancel all spot orders")
        print("0. Back")
        choice = input("Choose: ").strip()
        if choice == "1":
            place_spot_order(session)
        elif choice == "2":
            show_open_orders(session, "spot")
        elif choice == "3":
            cancel_order(session, "spot")
        elif choice == "4":
            cancel_all_orders(session, "spot")
        elif choice == "0":
            return
        else:
            print("Invalid choice.")


def futures_trade_menu(session) -> None:
    while True:
        print("\n--- Futures trading (USDT perpetual) ---")
        print("1. Place order (long / short)")
        print("2. Set leverage")
        print("3. Open positions")
        print("4. Close position (market)")
        print("5. Open orders")
        print("6. Cancel order")
        print("7. Cancel all futures orders")
        print("0. Back")
        choice = input("Choose: ").strip()
        if choice == "1":
            place_futures_order(session)
        elif choice == "2":
            set_leverage(session)
        elif choice == "3":
            show_positions(session, ask_for_symbol=True)
        elif choice == "4":
            close_futures_position(session)
        elif choice == "5":
            show_open_orders(session, "linear")
        elif choice == "6":
            cancel_order(session, "linear")
        elif choice == "7":
            cancel_all_orders(session, "linear")
        elif choice == "0":
            return
        else:
            print("Invalid choice.")


def main() -> None:
    if not API_KEY or not API_SECRET:
        print("Missing credentials in .env (BYBIT_API_KEY / BYBIT_API_SECRET)")
        print("Copy .env.example to .env and fill in your keys.")
        return

    session = create_session()
    label = env_label()
    print(f"Using Bybit {label}")
    if is_live_mainnet():
        print("WARNING: LIVE MAINNET mode — orders use real money.")
        print("Prefer BYBIT_TESTNET=true or BYBIT_DEMO=true while learning.")

    while True:
        print(f"\n===== BYBIT TERMINAL TRADER ({label}) =====")
        print("1. Spot market data")
        print("2. Futures market data")
        print("3. Account balance")
        print("4. Futures positions")
        print("5. Spot trading")
        print("6. Futures trading")
        print("0. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "1":
            market_menu(session, "spot", "Spot")
        elif choice == "2":
            market_menu(session, "linear", "Futures")
        elif choice == "3":
            show_balance(session)
        elif choice == "4":
            show_positions(session, ask_for_symbol=False)
        elif choice == "5":
            spot_trade_menu(session)
        elif choice == "6":
            futures_trade_menu(session)
        elif choice == "0":
            print("Trader closed.")
            break
        else:
            print("Invalid choice. Select 0 to 6.")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nTrader stopped.")
