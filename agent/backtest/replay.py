"""Chronological candle replay helpers."""

from __future__ import annotations

from agent.market_data import Candle


def slice_available(candles: list[Candle], index: int) -> list[Candle]:
    """Candles visible at bar index (inclusive) — no future bars."""
    if index < 0:
        return []
    return candles[: index + 1]


def mutate_future_closes(
    candles: list[Candle],
    *,
    from_index: int,
    factor: float,
) -> list[Candle]:
    """
    Test helper: alter closes strictly after ``from_index``.

    Earlier bars remain byte-identical for look-ahead invariance tests.
    """
    out: list[Candle] = []
    for i, c in enumerate(candles):
        if i <= from_index:
            out.append(c)
            continue
        new_close = float(c.close) * float(factor)
        high = max(float(c.high), new_close, float(c.open))
        low = min(float(c.low), new_close, float(c.open))
        out.append(
            Candle(
                start=c.start,
                open=c.open,
                high=high,
                low=low,
                close=new_close,
                volume=c.volume,
            )
        )
    return out
