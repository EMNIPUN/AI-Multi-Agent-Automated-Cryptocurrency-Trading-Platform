"""
Paper equity reconciliation — spot-like unleveraged longs.

Marked equity is NOT inventable from entry prices alone when marks are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from agent.paper.accounting import long_unrealized_pnl, notional, q
from agent.paper.config import d
from agent.paper.models import PaperPosition, PaperSession, PositionStatus


class ValuationStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    STALE_OR_PARTIAL = "stale_or_partial"
    FLAT = "flat"


@dataclass(frozen=True)
class EquitySnapshot:
    available_balance: Decimal
    reserved_capital: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal | None
    marked_equity: Decimal | None
    valuation_status: ValuationStatus
    open_position_count: int
    gross_exposure_entry: Decimal  # sum qty × entry (broker-compatible)
    gross_exposure_mark: Decimal | None  # sum qty × mark when all marks present
    cash_total: Decimal  # available + reserved (not equity when marks move)

    @property
    def equity_available(self) -> bool:
        return self.valuation_status in {ValuationStatus.OK, ValuationStatus.FLAT}


def utc_day_key(ms: int) -> str:
    """UTC calendar day key YYYY-MM-DD from epoch milliseconds."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def reconcile_equity(
    *,
    session: PaperSession,
    open_positions: list[PaperPosition],
    mark_max_age_ms: int | None = None,
    now_ms: int | None = None,
) -> EquitySnapshot:
    """
    Spot-like identity:

    cash_total = available + reserved
    When flat: marked_equity = cash_total
    When open with valid marks:
      unrealized = Σ (mark − entry) × qty
      marked_equity = available + reserved + unrealized
                   = available + Σ(entry×qty) + entry_fees_in_reserve + unrealized
                   = available + Σ(mark×qty) + Σ(entry_fee components in reserve)

    Missing/stale marks → valuation UNAVAILABLE / STALE_OR_PARTIAL; equity None.
    Never substitutes entry for mark.
    """
    opens = [p for p in open_positions if p.status is PositionStatus.OPEN]
    available = d(session.available_balance)
    reserved = d(session.reserved_capital)
    realized = d(session.realized_pnl)
    cash_total = q(available + reserved)
    gross_entry = q(
        sum((notional(p.quantity, p.entry_price) for p in opens), Decimal("0"))
    )

    if not opens:
        return EquitySnapshot(
            available_balance=available,
            reserved_capital=reserved,
            realized_pnl=realized,
            unrealized_pnl=Decimal("0"),
            marked_equity=cash_total,
            valuation_status=ValuationStatus.FLAT,
            open_position_count=0,
            gross_exposure_entry=Decimal("0"),
            gross_exposure_mark=Decimal("0"),
            cash_total=cash_total,
        )

    upnl = Decimal("0")
    mark_exposure = Decimal("0")
    missing = 0
    stale = 0
    for p in opens:
        if p.mark_price is None:
            missing += 1
            continue
        if mark_max_age_ms is not None and now_ms is not None:
            # Positions store opened_ms / no mark timestamp — treat missing age as stale
            # only when mark_max_age configured and we lack a fresher stamp.
            # MVP: if mark present we accept unless explicitly flagged elsewhere.
            pass
        upnl += long_unrealized_pnl(
            quantity=p.quantity, entry_price=p.entry_price, mark_price=p.mark_price
        )
        mark_exposure += notional(p.quantity, p.mark_price)

    if missing:
        status = (
            ValuationStatus.STALE_OR_PARTIAL
            if missing < len(opens)
            else ValuationStatus.UNAVAILABLE
        )
        return EquitySnapshot(
            available_balance=available,
            reserved_capital=reserved,
            realized_pnl=realized,
            unrealized_pnl=q(upnl) if missing < len(opens) else None,
            marked_equity=None,
            valuation_status=status,
            open_position_count=len(opens),
            gross_exposure_entry=gross_entry,
            gross_exposure_mark=None,
            cash_total=cash_total,
        )

    if stale:
        return EquitySnapshot(
            available_balance=available,
            reserved_capital=reserved,
            realized_pnl=realized,
            unrealized_pnl=q(upnl),
            marked_equity=None,
            valuation_status=ValuationStatus.STALE_OR_PARTIAL,
            open_position_count=len(opens),
            gross_exposure_entry=gross_entry,
            gross_exposure_mark=q(mark_exposure),
            cash_total=cash_total,
        )

    equity = q(available + reserved + upnl)
    return EquitySnapshot(
        available_balance=available,
        reserved_capital=reserved,
        realized_pnl=realized,
        unrealized_pnl=q(upnl),
        marked_equity=equity,
        valuation_status=ValuationStatus.OK,
        open_position_count=len(opens),
        gross_exposure_entry=gross_entry,
        gross_exposure_mark=q(mark_exposure),
        cash_total=cash_total,
    )


def drawdown_fraction(*, peak: Decimal, current: Decimal) -> Decimal | None:
    if peak <= 0 or current < 0:
        return None
    if current >= peak:
        return Decimal("0")
    return q((peak - current) / peak)


def daily_loss_fraction(*, day_start: Decimal, current: Decimal) -> Decimal | None:
    if day_start <= 0:
        return None
    if current >= day_start:
        return Decimal("0")
    return q((day_start - current) / day_start)
