"""Closed-candle filtering — pure validation, no network I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass

from agent.candle_time import (
    CandleTimeError,
    assert_supported_interval,
    candle_close_ms,
    default_staleness_ms,
    is_candle_confirmed,
    normalize_ts_to_utc_ms,
)
from agent.market_data import Candle


@dataclass(frozen=True)
class ConfirmedCandleSeries:
    candles: list[Candle]  # oldest → newest, all confirmed
    interval: str
    newest_close_ms: int
    skipped_forming: int
    reason: str = ""


@dataclass(frozen=True)
class CandleFilterReject:
    reason: str


def _valid_ohlcv(c: Candle) -> str | None:
    for name, value in (
        ("open", c.open),
        ("high", c.high),
        ("low", c.low),
        ("close", c.close),
        ("volume", c.volume),
    ):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"malformed OHLCV: {name} not numeric"
        if not math.isfinite(float(value)):
            return f"malformed OHLCV: {name} not finite"
    if c.volume < 0:
        return "malformed OHLCV: negative volume"
    if c.high < c.low:
        return "malformed OHLCV: high < low"
    if c.high < c.open or c.high < c.close:
        return "malformed OHLCV: high below open/close"
    if c.low > c.open or c.low > c.close:
        return "malformed OHLCV: low above open/close"
    return None


def filter_confirmed_candles(
    candles: list[Candle],
    interval: str,
    *,
    now_ms: int,
    grace_ms: int = 2_000,
    max_clock_skew_ms: int = 5_000,
    max_staleness_ms: int | None = None,
    min_bars: int = 1,
) -> ConfirmedCandleSeries | CandleFilterReject:
    """
    Validate and retain only candles whose close+grace is in the past.

    Never assumes a newly fetched REST candle is already closed: confirmation
    requires ``now_ms >= expected_close_ms + grace_ms`` using a caller-supplied
    UTC clock (typically ``datetime.now(timezone.utc)``).

    Input may be newest-first or oldest-first; output is oldest→newest.
    """
    try:
        interval = assert_supported_interval(interval)
        now_ms = normalize_ts_to_utc_ms(now_ms)
    except CandleTimeError as exc:
        return CandleFilterReject(reason=str(exc))

    if not candles:
        return CandleFilterReject(reason="no candles in market data response")

    normalized: list[Candle] = []
    for raw in candles:
        try:
            start = normalize_ts_to_utc_ms(raw.start)
        except CandleTimeError as exc:
            return CandleFilterReject(reason=str(exc))
        if start - now_ms > max_clock_skew_ms:
            return CandleFilterReject(
                reason=f"candle start in future beyond clock skew ({start} > {now_ms})"
            )
        candle = Candle(
            start=start,
            open=float(raw.open),
            high=float(raw.high),
            low=float(raw.low),
            close=float(raw.close),
            volume=float(raw.volume),
        )
        err = _valid_ohlcv(candle)
        if err:
            return CandleFilterReject(reason=err)
        normalized.append(candle)

    # Order oldest → newest
    ordered = sorted(normalized, key=lambda c: c.start)
    if len({c.start for c in ordered}) != len(ordered):
        return CandleFilterReject(reason="duplicate candle timestamps")
    for i in range(1, len(ordered)):
        if ordered[i].start <= ordered[i - 1].start:
            return CandleFilterReject(reason="candle timestamps not strictly increasing")

    confirmed: list[Candle] = []
    skipped_forming = 0
    for candle in ordered:
        try:
            if is_candle_confirmed(
                candle.start, interval, now_ms=now_ms, grace_ms=grace_ms
            ):
                confirmed.append(candle)
            else:
                skipped_forming += 1
        except CandleTimeError as exc:
            return CandleFilterReject(reason=str(exc))

    if len(confirmed) < min_bars:
        return CandleFilterReject(
            reason=(
                f"insufficient confirmed bars ({len(confirmed)} < {min_bars}); "
                f"forming_skipped={skipped_forming}"
            )
        )

    newest = confirmed[-1]
    newest_close = candle_close_ms(newest.start, interval)
    staleness_limit = (
        max_staleness_ms
        if max_staleness_ms is not None
        else default_staleness_ms(interval)
    )
    age = now_ms - newest_close
    if age > staleness_limit:
        return CandleFilterReject(
            reason=(
                f"stale market data: newest confirmed close age {age}ms "
                f"> {staleness_limit}ms"
            )
        )

    return ConfirmedCandleSeries(
        candles=confirmed,
        interval=interval,
        newest_close_ms=newest_close,
        skipped_forming=skipped_forming,
    )
