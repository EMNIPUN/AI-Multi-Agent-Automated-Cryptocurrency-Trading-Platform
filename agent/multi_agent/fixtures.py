"""Deterministic OHLCV builders for Phase 4A replay tests."""

from __future__ import annotations

from agent.market_data import Candle

# 15m interval ms
INTERVAL_15M_MS = 15 * 60_000


def make_series(
    closes: list[float],
    *,
    start_ms: int = 1_700_000_000_000,
    interval_ms: int = INTERVAL_15M_MS,
    volume: float = 100.0,
) -> list[Candle]:
    out: list[Candle] = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        high = max(prev, close) * 1.001
        low = min(prev, close) * 0.999
        out.append(
            Candle(
                start=start_ms + i * interval_ms,
                open=prev,
                high=high,
                low=low,
                close=close,
                volume=volume * (1.0 + (i % 5) * 0.05),
            )
        )
    return out


def bullish_trend_closes(n: int = 220, start: float = 100.0) -> list[float]:
    """Steadily rising series with mild noise."""
    out: list[float] = []
    px = start
    for i in range(n):
        px = px * (1.0015 if i % 7 != 0 else 1.0002)
        out.append(px)
    return out


def bearish_trend_closes(n: int = 220, start: float = 100.0) -> list[float]:
    out: list[float] = []
    px = start
    for i in range(n):
        px = px * (0.9985 if i % 7 != 0 else 0.9998)
        out.append(px)
    return out


def sideways_closes(n: int = 220, start: float = 100.0) -> list[float]:
    out: list[float] = []
    px = start
    for i in range(n):
        px = start * (1.0 + (0.002 if i % 2 == 0 else -0.002))
        out.append(px)
    return out


def series_now_ms(candles: list[Candle], interval_ms: int = INTERVAL_15M_MS, grace_ms: int = 5_000) -> int:
    """Clock after the last candle is fully confirmed."""
    if not candles:
        return 0
    return candles[-1].start + interval_ms + grace_ms
