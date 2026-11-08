"""Align signed Bybit request timestamps with exchange server time.

Windows clocks that run a few seconds ahead of Bybit trigger ErrCode 10002
(timestamp / recv_window). Bybit allows only ~1s into the future, so raising
recv_window does not help — we must subtract local skew.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_offset_ms = 0
_last_sync_mono = 0.0
_SYNC_TTL_S = 300.0
_BYBIT_TIME_URL = "https://api.bybit.com/v5/market/time"


def get_time_offset_ms() -> int:
    return _offset_ms


def synced_timestamp_ms() -> int:
    """Millisecond timestamp adjusted toward Bybit server time."""
    return int(time.time() * 1000) + _offset_ms


def sync_bybit_clock(*, force: bool = False, timeout: float = 5.0) -> int:
    """
    Refresh local→Bybit offset. Safe to call often; sync is cached briefly.
    Returns offset_ms (server - local), so ahead clocks get a negative offset.
    """
    global _offset_ms, _last_sync_mono
    now = time.monotonic()
    with _lock:
        if not force and _last_sync_mono and (now - _last_sync_mono) < _SYNC_TTL_S:
            return _offset_ms
    try:
        with httpx.Client(timeout=timeout) as client:
            payload: dict[str, Any] = client.get(_BYBIT_TIME_URL).json()
        result = payload.get("result") or {}
        # Prefer nano/ms fields when present; fall back to seconds.
        if result.get("timeNano"):
            server_ms = int(result["timeNano"]) // 1_000_000
        elif result.get("timeSecond"):
            server_ms = int(result["timeSecond"]) * 1000
        else:
            raise ValueError("bybit_time_missing")
        local_ms = int(time.time() * 1000)
        offset = server_ms - local_ms
        with _lock:
            _offset_ms = offset
            _last_sync_mono = time.monotonic()
        if abs(offset) > 500:
            logger.warning(
                "bybit_clock_skew_corrected offset_ms=%s (local ahead if negative)",
                offset,
            )
        return offset
    except Exception as exc:  # noqa: BLE001 — keep prior offset; wallet may still fail
        logger.warning("bybit_clock_sync_failed error=%s", type(exc).__name__)
        return _offset_ms


def install_pybit_timestamp_patch() -> None:
    """Patch pybit timestamp generator so signed requests use synced time."""
    import pybit._helpers as helpers

    if getattr(helpers.generate_timestamp, "_cryptonova_synced", False):
        return

    def _generate_timestamp() -> int:
        # Soft refresh; never block wallet forever if sync fails.
        sync_bybit_clock(force=False)
        return synced_timestamp_ms()

    _generate_timestamp._cryptonova_synced = True  # type: ignore[attr-defined]
    helpers.generate_timestamp = _generate_timestamp  # type: ignore[assignment]
