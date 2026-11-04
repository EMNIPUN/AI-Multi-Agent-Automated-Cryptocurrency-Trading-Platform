from bot.client import create_session
from bot.config import API_KEY, API_SECRET, env_label


def main() -> None:
    if not API_KEY or not API_SECRET:
        raise SystemExit(
            "Missing API credentials. Copy .env.example to .env and fill keys."
        )

    session = create_session()
    label = env_label()

    try:
        public = session.get_server_time()
        if public.get("retCode") != 0:
            raise SystemExit(f"Public API error: {public.get('retMsg')}")

        private = session.get_api_key_information()
        if private.get("retCode") != 0:
            raise SystemExit(
                f"Auth failed on {label}: {private.get('retMsg')}\n"
                "Keys must match the environment "
                "(testnet ≠ mainnet ≠ demo)."
            )

        print(f"Connected to Bybit {label} successfully (authenticated).")
    except SystemExit:
        raise
    except Exception as error:
        print("Connection failed:", error)


if __name__ == "__main__":
    main()
