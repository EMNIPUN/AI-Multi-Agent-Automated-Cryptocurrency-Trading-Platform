"""Deterministic Bybit interval / candle close-time helpers (no network I/O)."""

from __future__ import annotations

from datetime import datetime, timezone

# Bybit V5 kline intervals commonly used by this agent.
SUPPORTED_INTERVALS = frozenset(
    {
        "1",
        "3",
        "5",
        "15",
        "30",
        "60",
        "120",
        "240",
        "360",
        "720",
        "D",
        "W",
        "M",
    }
)


class CandleTimeError(ValueError):
    """Invalid interval or timestamp for candle math."""


def normalize_ts_to_utc_ms(ts: int | float) -> int:
    """
    Normalize Bybit/local timestamps to UTC milliseconds.

    Values below 1e11 are treated as seconds; otherwise milliseconds.
    """
    try:
        value = int(ts)
    except (TypeError, ValueError) as exc:
        raise CandleTimeError("timestamp not an integer") from exc
    if value <= 0:
        raise CandleTimeError("timestamp must be positive")
    if value < 100_000_000_000:  # ~ March 1973 in ms; below => seconds
        value *= 1000
    return value


def assert_supported_interval(interval: str) -> str:
    key = (interval or "").strip()
    # Allow lowercase d/w/m from config typos
    if key in {"d", "w", "m"}:
        key = key.upper()
    if key not in SUPPORTED_INTERVALS:
        raise CandleTimeError(f"unsupported interval: {interval!r}")
    return key


def _dt_utc_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def candle_close_ms(start_ms: int, interval: str) -> int:
    """
    Expected exclusive close time (UTC ms) for a candle that opened at start_ms.

    Minute/hour intervals: start + duration.
    D/W/M: calendar boundaries in UTC (Bybit-style).
    """
    start_ms = normalize_ts_to_utc_ms(start_ms)
    interval = assert_supported_interval(interval)
    start = _dt_utc_ms(start_ms)

    if interval.isdigit():
        minutes = int(interval)
        return start_ms + minutes * 60_000

    if interval == "D":
        # Daily bar opens at 00:00 UTC; closes at next 00:00 UTC.
        day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if start != day_start:
            # Ambiguous non-aligned daily open — still advance one UTC day from open.
            return _ms(day_start) + 86_400_000
        return start_ms + 86_400_000

    if interval == "W":
        # Weekly: 7 * 24h from open (Bybit W bars are typically Monday 00:00 UTC).
        return start_ms + 7 * 86_400_000

    if interval == "M":
        year, month = start.year, start.month
        if month == 12:
            nxt = start.replace(
                year=year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            nxt = start.replace(
                year=year, month=month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        # If open is mid-month, close at next month start; if already month start, same.
        if start.day != 1 or start.hour or start.minute or start.second or start.microsecond:
            return _ms(nxt)
        return _ms(nxt)

    raise CandleTimeError(f"unsupported interval: {interval!r}")


def is_candle_confirmed(
    start_ms: int,
    interval: str,
    *,
    now_ms: int,
    grace_ms: int,
) -> bool:
    """True iff now is at/after expected close + grace."""
    close_ms = candle_close_ms(start_ms, interval)
    now_ms = normalize_ts_to_utc_ms(now_ms)
    return now_ms >= close_ms + max(0, grace_ms)


def default_staleness_ms(interval: str) -> int:
    """Max age of newest confirmed close before data is considered stale."""
    interval = assert_supported_interval(interval)
    if interval.isdigit():
        return int(interval) * 60_000 * 3
    if interval == "D":
        return 3 * 86_400_000
    if interval == "W":
        return 3 * 7 * 86_400_000
    if interval == "M":
        # ~92 days
        return 92 * 86_400_000
    return 86_400_000
