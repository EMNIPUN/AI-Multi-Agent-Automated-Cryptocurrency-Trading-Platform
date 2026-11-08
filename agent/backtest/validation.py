"""Historical candle and timestamp validation — no silent repair."""

from __future__ import annotations

import math
from dataclasses import dataclass

from agent.candle_time import assert_supported_interval, candle_close_ms
from agent.market_data import Candle


class CandleValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidationReport:
    candles: tuple[Candle, ...]
    warnings: tuple[str, ...]
    gap_starts_ms: tuple[int, ...]


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CandleValidationError("malformed_ohlcv", f"{name} not numeric")
    f = float(value)
    if not math.isfinite(f):
        raise CandleValidationError("malformed_ohlcv", f"{name} not finite")
    return f


def validate_ohlc_candle(c: Candle) -> None:
    o = _finite_number("open", c.open)
    h = _finite_number("high", c.high)
    low = _finite_number("low", c.low)
    cl = _finite_number("close", c.close)
    vol = _finite_number("volume", c.volume)
    if vol < 0:
        raise CandleValidationError("negative_volume", "volume must be >= 0")
    if h < low:
        raise CandleValidationError("invalid_ohlc", "high < low")
    if h < o or h < cl:
        raise CandleValidationError("invalid_ohlc", "high below open/close")
    if low > o or low > cl:
        raise CandleValidationError("invalid_ohlc", "low above open/close")
    if int(c.start) <= 0:
        raise CandleValidationError("invalid_timestamp", "start must be positive")


def expected_interval_ms(interval: str) -> int | None:
    key = assert_supported_interval(interval)
    if key.isdigit():
        return int(key) * 60_000
    return None  # D/W/M use candle_close_ms calendar math


def validate_candle_series(
    candles: list[Candle],
    *,
    interval: str,
    allow_gaps: bool = True,
) -> ValidationReport:
    """
    Validate chronological OHLCV series.

    - Rejects invalid OHLC, duplicates, and non-monotonic timestamps.
    - Detects missing intervals as warnings (never forward-fills).
    - Zero volume is allowed and distinguished from gaps.
    """
    if not candles:
        raise CandleValidationError("empty_dataset", "no candles provided")

    assert_supported_interval(interval)
    warnings: list[str] = []
    gap_starts: list[int] = []
    out: list[Candle] = []
    seen: set[int] = set()
    step = expected_interval_ms(interval)

    for i, raw in enumerate(candles):
        validate_ohlc_candle(raw)
        start = int(raw.start)
        if start in seen:
            raise CandleValidationError(
                "duplicate_timestamp",
                f"duplicate candle start_ms={start} at index {i}",
            )
        seen.add(start)
        if out and start <= out[-1].start:
            raise CandleValidationError(
                "non_monotonic",
                f"candle start_ms={start} is not strictly after prior {out[-1].start}",
            )
        if out:
            prev = out[-1]
            expected_next = candle_close_ms(prev.start, interval) if step is None else prev.start + step
            if start != expected_next:
                if not allow_gaps:
                    raise CandleValidationError(
                        "missing_interval",
                        f"gap after {prev.start}: expected {expected_next}, got {start}",
                    )
                msg = f"missing_interval after {prev.start}: expected {expected_next}, got {start}"
                warnings.append(msg)
                gap_starts.append(prev.start)
                # Zero-volume bars are not gaps — only timestamp discontinuities are.
        out.append(raw)

    zero_vol = sum(1 for c in out if float(c.volume) == 0.0)
    if zero_vol:
        warnings.append(f"zero_volume_bars={zero_vol} (not treated as gaps)")

    return ValidationReport(
        candles=tuple(out),
        warnings=tuple(warnings),
        gap_starts_ms=tuple(gap_starts),
    )
