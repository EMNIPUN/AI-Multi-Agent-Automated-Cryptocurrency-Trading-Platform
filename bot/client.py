from pybit.unified_trading import HTTP

from bot.config import API_KEY, API_SECRET, USE_DEMO, USE_TESTNET


def create_session() -> HTTP:
    return HTTP(
        testnet=USE_TESTNET and not USE_DEMO,
        demo=USE_DEMO,
        api_key=API_KEY,
        api_secret=API_SECRET,
        timeout=30,
        # Retry on ConnectionReset / timeout / SSL blips
        force_retry=True,
        max_retries=5,
        retry_delay=1,
        recv_window=10000,
    )
