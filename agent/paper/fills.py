"""Deterministic fill and SL/TP simulation — no look-ahead beyond available bars."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from agent.paper.accounting import adverse_slippage_price, fee_amount, notional, q
from agent.paper.config import PaperBrokerConfig, d
from agent.paper.models import ExitReason, PaperCandle


@dataclass(frozen=True)
class SimulatedFillResult:
    price: Decimal
    fee: Decimal
    slippage: Decimal
    candle_start_ms: int


@dataclass(frozen=True)
class ExitTriggerResult:
    reason: ExitReason
    reference_price: Decimal
    fill: SimulatedFillResult


def simulate_entry_fill(
    *,
    candle: PaperCandle,
    side: str,
    quantity: Decimal,
    config: PaperBrokerConfig,
) -> SimulatedFillResult | None:
    """MVP: fill at next eligible confirmed candle open + adverse slippage."""
    if not candle.valid():
        return None
    fill_price = adverse_slippage_price(
        side=side,
        reference_price=candle.open,
        slippage_bps=config.slippage_bps,
    )
    slip = q(abs(fill_price - candle.open))
    n = notional(quantity, fill_price)
    fee = fee_amount(n, config.fee_rate)
    return SimulatedFillResult(
        price=fill_price,
        fee=fee,
        slippage=slip,
        candle_start_ms=candle.start_ms,
    )


def simulate_exit_fill(
    *,
    candle: PaperCandle,
    side: str,
    quantity: Decimal,
    reference_price: Decimal,
    config: PaperBrokerConfig,
    use_reference_as_base: bool = False,
) -> SimulatedFillResult | None:
    """Exit fill with adverse slippage. Gap model may use candle.open as base."""
    if not candle.valid():
        return None
    base = d(reference_price) if use_reference_as_base else candle.open
    # For SL/TP hits we price from the trigger reference (or gap open).
    fill_price = adverse_slippage_price(
        side=side,
        reference_price=base,
        slippage_bps=config.slippage_bps,
    )
    slip = q(abs(fill_price - base))
    n = notional(quantity, fill_price)
    fee = fee_amount(n, config.fee_rate)
    return SimulatedFillResult(
        price=fill_price,
        fee=fee,
        slippage=slip,
        candle_start_ms=candle.start_ms,
    )


def evaluate_long_exit(
    *,
    candle: PaperCandle,
    quantity: Decimal,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    config: PaperBrokerConfig,
) -> ExitTriggerResult | None:
    """
    Long SL/TP on confirmed OHLC.

    Same-bar collision: stop-loss first (conservative; no LTF ordering).
    Gap through stop: executable at open with adverse slippage (not guaranteed SL).
    """
    if not candle.valid():
        return None

    sl = d(stop_loss) if stop_loss is not None else None
    tp = d(take_profit) if take_profit is not None else None

    touched_sl = sl is not None and candle.low <= sl
    touched_tp = tp is not None and candle.high >= tp

    if touched_sl and touched_tp:
        # Conservative: assume SL first when both touched in one bar.
        gap = candle.open < sl
        ref = candle.open if gap else sl
        fill = simulate_exit_fill(
            candle=candle,
            side="SELL",
            quantity=quantity,
            reference_price=ref,
            config=config,
            use_reference_as_base=True,
        )
        if fill is None:
            return None
        return ExitTriggerResult(
            reason=ExitReason.STOP_LOSS, reference_price=ref, fill=fill
        )

    if touched_sl:
        assert sl is not None
        gap = candle.open < sl
        ref = candle.open if gap else sl
        fill = simulate_exit_fill(
            candle=candle,
            side="SELL",
            quantity=quantity,
            reference_price=ref,
            config=config,
            use_reference_as_base=True,
        )
        if fill is None:
            return None
        return ExitTriggerResult(
            reason=ExitReason.STOP_LOSS, reference_price=ref, fill=fill
        )

    if touched_tp:
        assert tp is not None
        # Gap above TP: still fill at TP + adverse sell slippage (conservative).
        gap = candle.open > tp
        ref = candle.open if gap else tp
        fill = simulate_exit_fill(
            candle=candle,
            side="SELL",
            quantity=quantity,
            reference_price=ref,
            config=config,
            use_reference_as_base=True,
        )
        if fill is None:
            return None
        return ExitTriggerResult(
            reason=ExitReason.TAKE_PROFIT, reference_price=ref, fill=fill
        )

    return None
