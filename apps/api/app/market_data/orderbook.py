"""Order-book snapshot / delta synchronizer with sequence protection."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.api.app.market_data.schemas import MarketCategory, OrderBookLevel, OrderBookSnapshot


@dataclass
class OrderBookSyncResult:
    ok: bool
    reason: str
    needs_resnapshot: bool = False


@dataclass
class OrderBookSynchronizer:
    symbol: str
    category: MarketCategory
    depth: int = 50
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    update_id: int | None = None
    sequence: int | None = None
    synced: bool = False
    stale: bool = False

    def apply_snapshot(
        self,
        *,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        update_id: int | None = None,
        sequence: int | None = None,
    ) -> OrderBookSyncResult:
        self.bids = {p: s for p, s in bids if s > 0}
        self.asks = {p: s for p, s in asks if s > 0}
        self.update_id = update_id
        self.sequence = sequence
        self.synced = True
        self.stale = False
        self._trim()
        return OrderBookSyncResult(True, "snapshot")

    def apply_delta(
        self,
        *,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        update_id: int | None = None,
        sequence: int | None = None,
    ) -> OrderBookSyncResult:
        if not self.synced:
            return OrderBookSyncResult(False, "no_snapshot", needs_resnapshot=True)

        if sequence is not None and self.sequence is not None:
            if sequence <= self.sequence:
                return OrderBookSyncResult(False, "duplicate_or_old_sequence")
            if sequence > self.sequence + 1:
                self.synced = False
                self.stale = True
                return OrderBookSyncResult(
                    False, "sequence_gap", needs_resnapshot=True
                )

        if update_id is not None and self.update_id is not None:
            if update_id < self.update_id:
                return OrderBookSyncResult(False, "stale_update_id")
            # Bybit often sends u == prior u+1 continuous; gap ⇒ resync.
            if update_id > self.update_id + 1 and sequence is None:
                self.synced = False
                self.stale = True
                return OrderBookSyncResult(
                    False, "update_id_gap", needs_resnapshot=True
                )

        for price, size in bids:
            if size <= 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size
        for price, size in asks:
            if size <= 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size

        if update_id is not None:
            self.update_id = update_id
        if sequence is not None:
            self.sequence = sequence
        self._trim()
        return OrderBookSyncResult(True, "delta")

    def mark_stale(self) -> None:
        self.stale = True

    def snapshot(self) -> OrderBookSnapshot:
        bid_levels = [
            OrderBookLevel(price=p, size=s)
            for p, s in sorted(self.bids.items(), key=lambda x: x[0], reverse=True)
        ]
        ask_levels = [
            OrderBookLevel(price=p, size=s)
            for p, s in sorted(self.asks.items(), key=lambda x: x[0])
        ]
        best_bid = bid_levels[0].price if bid_levels else None
        best_ask = ask_levels[0].price if ask_levels else None
        spread = None
        spread_bps = None
        if best_bid is not None and best_ask is not None:
            spread = best_ask - best_bid
            mid = (best_ask + best_bid) / 2
            if mid > 0:
                spread_bps = (spread / mid) * 10_000
        return OrderBookSnapshot(
            symbol=self.symbol,
            category=self.category,
            bids=bid_levels,
            asks=ask_levels,
            update_id=self.update_id,
            sequence=self.sequence,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            spread_bps=spread_bps,
            synced=self.synced and not self.stale,
            stale=self.stale or not self.synced,
        )

    def _trim(self) -> None:
        if len(self.bids) > self.depth:
            keep = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[
                : self.depth
            ]
            self.bids = dict(keep)
        if len(self.asks) > self.depth:
            keep = sorted(self.asks.items(), key=lambda x: x[0])[: self.depth]
            self.asks = dict(keep)


def parse_levels(raw: object) -> list[tuple[float, float]] | None:
    if not isinstance(raw, list):
        return None
    out: list[tuple[float, float]] = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            return None
        try:
            out.append((float(row[0]), float(row[1])))
        except (TypeError, ValueError):
            return None
    return out
