"""Decimal-safe fee, notional, and PnL helpers for paper simulation."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from agent.paper.config import d

MONEY_QUANT = Decimal("0.00000001")


def q(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def notional(quantity: Decimal, price: Decimal) -> Decimal:
    return q(d(quantity) * d(price))


def fee_amount(notional_value: Decimal, fee_rate: Decimal) -> Decimal:
    return q(d(notional_value) * d(fee_rate))


def adverse_slippage_price(
    *,
    side: str,
    reference_price: Decimal,
    slippage_bps: Decimal,
) -> Decimal:
    """Apply adverse slippage: BUY pays up, SELL receives less."""
    ref = d(reference_price)
    bps = d(slippage_bps) / Decimal("10000")
    if side.upper() == "BUY":
        return q(ref * (Decimal("1") + bps))
    return q(ref * (Decimal("1") - bps))


def long_gross_pnl(
    *,
    quantity: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
) -> Decimal:
    return q((d(exit_price) - d(entry_price)) * d(quantity))


def long_net_pnl(
    *,
    quantity: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
    entry_fee: Decimal,
    exit_fee: Decimal,
) -> Decimal:
    gross = long_gross_pnl(
        quantity=quantity, entry_price=entry_price, exit_price=exit_price
    )
    return q(gross - d(entry_fee) - d(exit_fee))


def long_unrealized_pnl(
    *,
    quantity: Decimal,
    entry_price: Decimal,
    mark_price: Decimal,
) -> Decimal:
    return long_gross_pnl(
        quantity=quantity, entry_price=entry_price, exit_price=mark_price
    )


def capital_to_reserve(*, quantity: Decimal, fill_price: Decimal, fee: Decimal) -> Decimal:
    """Spot-like long: reserve entry notional + entry fee from available cash."""
    return q(notional(quantity, fill_price) + d(fee))
