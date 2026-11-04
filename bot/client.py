from pybit.unified_trading import HTTP

from bot.config import API_KEY, API_SECRET, USE_DEMO, USE_TESTNET


def create_session(
    *,
    force_retry: bool = True,
    max_retries: int = 5,
    timeout: int = 30,
) -> HTTP:
    """
    Build a Bybit HTTP session.

    Default retains read-friendly retries. For order *creation*, prefer
    ``create_write_session()`` so ambiguous network errors are not blindly
    retried (duplicate fill risk).
    """
    return HTTP(
        testnet=USE_TESTNET and not USE_DEMO,
        demo=USE_DEMO,
        api_key=API_KEY,
        api_secret=API_SECRET,
        timeout=timeout,
        force_retry=force_retry,
        max_retries=max_retries,
        retry_delay=1,
        recv_window=10000,
    )


def create_write_session(*, timeout: int = 30) -> HTTP:
    """
    Session for non-idempotent writes (place_order).

    force_retry=False and max_retries=1: a single attempt. Callers must treat
    timeouts as UNKNOWN and reconcile — never assume failure.
    """
    return create_session(force_retry=False, max_retries=1, timeout=timeout)
