import time
from typing import Any, Callable

from bot.config import env_label

_TRANSIENT = (
    "Connection aborted",
    "ConnectionResetError",
    "RemoteDisconnected",
    "Read timed out",
    "Connection reset",
    "Max retries exceeded",
)


def _is_transient(message: str) -> bool:
    return any(token in message for token in _TRANSIENT)


def call_api(
    label: str,
    func: Callable[..., dict],
    *,
    retries: int = 3,
    **kwargs: Any,
) -> dict | None:
    """Call a Bybit API method and return result dict, or None on failure."""
    print(f"\n--- {label} ---")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = func(**kwargs)
            if response.get("retCode") != 0:
                print("API error:", response.get("retMsg"))
                return None
            return response.get("result") or {}
        except Exception as exc:
            last_error = exc
            message = str(exc)
            if _is_transient(message) and attempt < retries:
                print(f"Network blip (attempt {attempt}/{retries}), retrying...")
                time.sleep(attempt)
                continue

            print("Request failed:", message)
            if "401" in message or "10003" in message:
                print(
                    f"Hint: API key does not match {env_label()}. "
                    "Create keys on that environment, or change "
                    "BYBIT_TESTNET / BYBIT_DEMO in .env."
                )
            return None

    if last_error:
        print("Request failed:", last_error)
    return None
