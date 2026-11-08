"""Ordered candle series with duplicate / out-of-order protection."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.api.app.market_data.schemas import CandleBar


@dataclass
class CandleUpdateResult:
    accepted: bool
    reason: str
    replaced_forming: bool = False


@dataclass
class CandleSeries:
    """Newest candle may be forming; confirmed bars are immutable once closed."""

    interval_ms: int
    max_bars: int = 1000
    _bars: dict[int, CandleBar] = field(default_factory=dict)
    _order: list[int] = field(default_factory=list)

    def bars(self) -> list[CandleBar]:
        return [self._bars[t] for t in self._order]

    def confirmed_bars(self, *, now_ms: int | None = None) -> list[CandleBar]:
        """Drop the still-forming open candle when interval is known."""
        bars = self.bars()
        if not bars or self.interval_ms <= 0:
            return [b.model_copy(update={"confirmed": True}) for b in bars]
        if now_ms is None:
            # Without clock, treat last bar as potentially forming.
            if len(bars) <= 1:
                return []
            return [b.model_copy(update={"confirmed": True}) for b in bars[:-1]]
        out: list[CandleBar] = []
        for b in bars:
            close_ms = b.time * 1000 + self.interval_ms
            confirmed = now_ms >= close_ms
            if confirmed:
                out.append(b.model_copy(update={"confirmed": True}))
        return out

    def apply(self, candle: CandleBar, *, allow_forming_replace: bool = True) -> CandleUpdateResult:
        t = int(candle.time)
        if t <= 0:
            return CandleUpdateResult(False, "invalid_time")
        if t in self._bars:
            existing = self._bars[t]
            # Same open time: allow OHLC refresh for forming bar only.
            if allow_forming_replace and not existing.confirmed:
                self._bars[t] = candle
                return CandleUpdateResult(True, "replaced_forming", replaced_forming=True)
            if (
                existing.open == candle.open
                and existing.high == candle.high
                and existing.low == candle.low
                and existing.close == candle.close
                and existing.volume == candle.volume
            ):
                return CandleUpdateResult(False, "duplicate")
            if existing.confirmed:
                return CandleUpdateResult(False, "immutable_confirmed")
            self._bars[t] = candle
            return CandleUpdateResult(True, "replaced_forming", replaced_forming=True)

        if self._order and t < self._order[-1]:
            # Out-of-order older bar: accept only if missing gap fill and before tip.
            if t in self._bars:
                return CandleUpdateResult(False, "duplicate")
            # Insert chronologically; reject if would rewrite confirmed tip without gap intent.
            insert_at = 0
            while insert_at < len(self._order) and self._order[insert_at] < t:
                insert_at += 1
            if insert_at == len(self._order):
                self._order.append(t)
            else:
                self._order.insert(insert_at, t)
            self._bars[t] = candle
            self._trim()
            return CandleUpdateResult(True, "inserted_historical")

        self._order.append(t)
        self._bars[t] = candle
        self._trim()
        return CandleUpdateResult(True, "appended")

    def replace_all(self, candles: list[CandleBar]) -> None:
        ordered = sorted(candles, key=lambda c: c.time)
        self._bars = {int(c.time): c for c in ordered}
        self._order = [int(c.time) for c in ordered]
        self._trim()

    def _trim(self) -> None:
        while len(self._order) > self.max_bars:
            old = self._order.pop(0)
            self._bars.pop(old, None)


def interval_to_ms(interval: str) -> int:
    if interval == "D":
        return 86_400_000
    try:
        minutes = int(interval)
    except ValueError as exc:
        raise ValueError(f"unsupported_interval:{interval}") from exc
    if minutes <= 0:
        raise ValueError(f"unsupported_interval:{interval}")
    return minutes * 60_000


def parse_bybit_kline_row(row: object, *, confirmed: bool = True) -> CandleBar | None:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        return None
    try:
        start_ms = int(row[0])
        return CandleBar(
            time=start_ms // 1000,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            confirmed=confirmed,
        )
    except (TypeError, ValueError):
        return None
