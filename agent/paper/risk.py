"""
Deterministic portfolio risk evaluator for local paper trading.

Independent of LLM clients and live exchange adapters.
Does not override SignalPipeline coordinator scores or prior VETO/BLOCKED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any

from agent.paper.accounting import (
    adverse_slippage_price,
    fee_amount,
    notional,
    q,
)
from agent.paper.config import d
from agent.paper.equity import (
    EquitySnapshot,
    ValuationStatus,
    daily_loss_fraction,
    drawdown_fraction,
    reconcile_equity,
)
from agent.paper.models import PaperPosition, PaperSession, PositionStatus
from agent.paper.risk_config import PortfolioRiskConfig


class PortfolioRiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    HALTED = "HALTED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass(frozen=True)
class ProposedEntry:
    symbol: str
    category: str
    side: str  # BUY only for new exposure
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    requested_quantity: Decimal | None = None
    requested_notional: Decimal | None = None


@dataclass(frozen=True)
class PortfolioRiskStateView:
    """Persisted halt / peak / day reference (immutable input)."""

    halted: bool = False
    halt_reason: str | None = None
    peak_marked_equity: Decimal | None = None
    day_key: str | None = None
    day_start_equity: Decimal | None = None


@dataclass(frozen=True)
class PortfolioRiskResult:
    verdict: PortfolioRiskVerdict
    reason_codes: tuple[str, ...]
    explanation: str
    sized_quantity: Decimal | None = None
    sized_notional: Decimal | None = None
    expected_entry_fill: Decimal | None = None
    expected_stop_fill: Decimal | None = None
    expected_tp_fill: Decimal | None = None
    estimated_net_risk: Decimal | None = None
    estimated_net_reward: Decimal | None = None
    gross_rr: Decimal | None = None
    net_rr: Decimal | None = None
    marked_equity: Decimal | None = None
    open_exposure: Decimal | None = None
    proposed_exposure: Decimal | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.verdict is PortfolioRiskVerdict.APPROVED


def _finite_positive(value: Decimal) -> bool:
    try:
        v = float(value)
        return math.isfinite(v) and v > 0
    except Exception:  # noqa: BLE001
        return False


def _floor_qty(qty: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        step = Decimal("0.00000001")
    # Never round up.
    units = (d(qty) / step).to_integral_value(rounding=ROUND_DOWN)
    return q(units * step)


def estimate_long_fills(
    *,
    entry_ref: Decimal,
    stop_ref: Decimal,
    tp_ref: Decimal,
    config: PortfolioRiskConfig,
) -> tuple[Decimal, Decimal, Decimal]:
    entry_fill = adverse_slippage_price(
        side="BUY", reference_price=entry_ref, slippage_bps=config.slippage_bps
    )
    # Conservative stop: adverse sell from stop (or worse if already adverse).
    stop_fill = adverse_slippage_price(
        side="SELL", reference_price=stop_ref, slippage_bps=config.slippage_bps
    )
    tp_fill = adverse_slippage_price(
        side="SELL", reference_price=tp_ref, slippage_bps=config.slippage_bps
    )
    return entry_fill, stop_fill, tp_fill


def per_unit_net_stop_risk(
    *,
    entry_fill: Decimal,
    stop_fill: Decimal,
    fee_rate: Decimal,
) -> Decimal:
    """
    Modeled per-unit loss if stopped out (not a guaranteed max loss).

    Includes adverse stop fill distance + entry fee/unit + exit fee/unit at stop.
    """
    price_risk = d(entry_fill) - d(stop_fill)
    if price_risk <= 0:
        return Decimal("0")
    entry_fee_pu = d(entry_fill) * d(fee_rate)
    exit_fee_pu = d(stop_fill) * d(fee_rate)
    return q(price_risk + entry_fee_pu + exit_fee_pu)


def evaluate_portfolio_entry(
    *,
    session: PaperSession,
    open_positions: list[PaperPosition],
    pending_buy_exposure: Decimal,
    proposed: ProposedEntry,
    config: PortfolioRiskConfig,
    risk_state: PortfolioRiskStateView | None = None,
    now_ms: int | None = None,
) -> PortfolioRiskResult:
    """
    Evaluate a proposed LONG entry against reconciled paper portfolio state.

    Prior signal VETO/BLOCKED must be enforced by the caller — this function
    never resurrects a vetoed signal.
    """
    risk_state = risk_state or PortfolioRiskStateView()
    evidence: dict[str, Any] = {}

    if risk_state.halted:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.HALTED,
            reason_codes=("PORTFOLIO_HALTED", risk_state.halt_reason or "HALTED"),
            explanation="Portfolio risk halt active — new entries blocked",
            evidence={"halt_reason": risk_state.halt_reason},
        )

    side = (proposed.side or "").upper()
    if side != "BUY":
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("UNSUPPORTED_SIDE",),
            explanation="Portfolio risk entry supports BUY (long) only",
        )

    if config.allow_short:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("SHORTS_NOT_SUPPORTED",),
            explanation="Shorts are not implemented for paper portfolio risk",
        )
    if config.allow_leverage:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("LEVERAGE_NOT_SUPPORTED",),
            explanation="Leverage is not implemented for paper portfolio risk",
        )

    cat = (proposed.category or "").strip().lower()
    allowed = {c.lower() for c in config.allowed_entry_categories}
    if cat not in allowed:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("UNSUPPORTED_CATEGORY", "FUTURES_OR_NON_SPOT"),
            explanation=(
                f"Category '{proposed.category}' not allowed for paper portfolio "
                f"entries; allowed={sorted(allowed)}"
            ),
        )

    for label, val in (
        ("entry_price", proposed.entry_price),
        ("stop_loss", proposed.stop_loss),
        ("take_profit", proposed.take_profit),
    ):
        if val is None or not _finite_positive(d(val)):
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.REJECTED,
                reason_codes=("INVALID_PRICE", label.upper()),
                explanation=f"Non-finite or non-positive {label}",
            )

    if d(proposed.stop_loss) >= d(proposed.entry_price):
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("INVALID_STOP",),
            explanation="Long stop must be strictly below entry",
        )
    if d(proposed.take_profit) <= d(proposed.entry_price):
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("INVALID_TAKE_PROFIT",),
            explanation="Long take-profit must be strictly above entry",
        )

    opens = [p for p in open_positions if p.status is PositionStatus.OPEN]
    equity = reconcile_equity(session=session, open_positions=opens, now_ms=now_ms)
    evidence["valuation_status"] = equity.valuation_status.value
    evidence["cash_total"] = str(equity.cash_total)
    evidence["available"] = str(equity.available_balance)

    if config.require_valid_marks_for_entries and opens:
        if equity.valuation_status in {
            ValuationStatus.UNAVAILABLE,
            ValuationStatus.STALE_OR_PARTIAL,
        }:
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.DATA_UNAVAILABLE,
                reason_codes=("MARKS_UNAVAILABLE", equity.valuation_status.value.upper()),
                explanation="Cannot size risk capacity without valid marks on open positions",
                open_exposure=equity.gross_exposure_entry,
                evidence=evidence,
            )

    if equity.marked_equity is None or not equity.equity_available:
        if opens:
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.DATA_UNAVAILABLE,
                reason_codes=("EQUITY_UNAVAILABLE",),
                explanation="Marked equity unavailable",
                open_exposure=equity.gross_exposure_entry,
                evidence=evidence,
            )
        # Flat without equity should not happen; treat cash as equity.
        marked = equity.cash_total
    else:
        marked = equity.marked_equity

    evidence["marked_equity"] = str(marked)

    # Daily loss / drawdown using persisted references when provided
    if risk_state.day_start_equity is not None and marked is not None:
        dloss = daily_loss_fraction(
            day_start=d(risk_state.day_start_equity), current=marked
        )
        evidence["daily_loss_fraction"] = str(dloss) if dloss is not None else None
        if dloss is not None and dloss >= config.max_daily_loss_fraction:
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.HALTED,
                reason_codes=("DAILY_LOSS_LIMIT",),
                explanation="Daily marked-equity loss limit breached",
                marked_equity=marked,
                evidence=evidence,
            )

    peak = risk_state.peak_marked_equity
    if peak is None:
        peak = marked
    dd = drawdown_fraction(peak=d(peak), current=marked)
    evidence["peak_equity"] = str(peak)
    evidence["drawdown_fraction"] = str(dd) if dd is not None else None
    if dd is not None and dd >= config.max_drawdown_fraction:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.HALTED,
            reason_codes=("MAX_DRAWDOWN_LIMIT",),
            explanation="Maximum drawdown limit breached",
            marked_equity=marked,
            evidence=evidence,
        )

    if len(opens) >= config.max_open_positions:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("MAX_OPEN_POSITIONS",),
            explanation=f"Open positions {len(opens)} >= max {config.max_open_positions}",
            marked_equity=marked,
            open_exposure=equity.gross_exposure_entry,
            evidence=evidence,
        )

    if config.one_position_per_symbol:
        if any(p.symbol == proposed.symbol for p in opens):
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.REJECTED,
                reason_codes=("SYMBOL_ALREADY_OPEN",),
                explanation="One-position-per-symbol: symbol already open",
                marked_equity=marked,
                evidence=evidence,
            )

    if session.available_balance < 0:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("NEGATIVE_AVAILABLE_BALANCE",),
            explanation="Available balance is negative",
            marked_equity=marked,
            evidence=evidence,
        )

    entry_fill, stop_fill, tp_fill = estimate_long_fills(
        entry_ref=d(proposed.entry_price),
        stop_ref=d(proposed.stop_loss),
        tp_ref=d(proposed.take_profit),
        config=config,
    )
    unit_risk = per_unit_net_stop_risk(
        entry_fill=entry_fill, stop_fill=stop_fill, fee_rate=config.fee_rate
    )
    if unit_risk <= 0:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("NON_POSITIVE_STOP_RISK", "GAP_OR_INVALID_STOP"),
            explanation="Modeled stop risk per unit is non-positive after costs/slippage",
            expected_entry_fill=entry_fill,
            expected_stop_fill=stop_fill,
            marked_equity=marked,
            evidence=evidence,
        )

    risk_budget = q(marked * config.max_risk_fraction_per_trade)
    qty_risk = _floor_qty(risk_budget / unit_risk, config.quantity_step)

    # Cash constraint: reserve ≈ qty * entry_fill * (1 + fee_rate)
    reserve_pu = q(entry_fill * (Decimal("1") + config.fee_rate))
    if reserve_pu <= 0:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("INVALID_RESERVE_UNIT",),
            explanation="Cannot fund position",
            marked_equity=marked,
            evidence=evidence,
        )
    qty_cash = _floor_qty(session.available_balance / reserve_pu, config.quantity_step)

    open_exposure = q(equity.gross_exposure_entry + d(pending_buy_exposure))
    max_exposure = q(marked * config.max_gross_exposure_fraction)
    remaining = q(max_exposure - open_exposure)
    if remaining <= 0:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("MAX_EXPOSURE",),
            explanation="No remaining gross exposure capacity",
            marked_equity=marked,
            open_exposure=open_exposure,
            evidence=evidence,
        )
    qty_exposure = _floor_qty(remaining / entry_fill, config.quantity_step)

    qty = min(qty_risk, qty_cash, qty_exposure)

    # Cap by requested size (never increase)
    if proposed.requested_quantity is not None:
        if not _finite_positive(d(proposed.requested_quantity)) and d(
            proposed.requested_quantity
        ) != 0:
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.REJECTED,
                reason_codes=("INVALID_QUANTITY",),
                explanation="Requested quantity not finite/positive",
                marked_equity=marked,
                evidence=evidence,
            )
        qty = min(qty, _floor_qty(d(proposed.requested_quantity), config.quantity_step))
    elif proposed.requested_notional is not None:
        if not _finite_positive(d(proposed.requested_notional)):
            return PortfolioRiskResult(
                verdict=PortfolioRiskVerdict.REJECTED,
                reason_codes=("INVALID_NOTIONAL",),
                explanation="Requested notional not finite/positive",
                marked_equity=marked,
                evidence=evidence,
            )
        req_qty = _floor_qty(
            d(proposed.requested_notional) / d(proposed.entry_price),
            config.quantity_step,
        )
        qty = min(qty, req_qty)

    if qty <= 0:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("ZERO_QUANTITY", "INSUFFICIENT_CAPACITY"),
            explanation="Sized quantity is zero after constraints",
            expected_entry_fill=entry_fill,
            marked_equity=marked,
            open_exposure=open_exposure,
            evidence={
                **evidence,
                "qty_risk": str(qty_risk),
                "qty_cash": str(qty_cash),
                "qty_exposure": str(qty_exposure),
            },
        )

    sized_notional = notional(qty, entry_fill)
    entry_fee = fee_amount(sized_notional, config.fee_rate)
    stop_notional = notional(qty, stop_fill)
    tp_notional = notional(qty, tp_fill)
    exit_fee_stop = fee_amount(stop_notional, config.fee_rate)
    exit_fee_tp = fee_amount(tp_notional, config.fee_rate)

    gross_risk = q((entry_fill - stop_fill) * qty)
    gross_reward = q((tp_fill - entry_fill) * qty)
    net_risk = q(gross_risk + entry_fee + exit_fee_stop)
    net_reward = q(gross_reward - entry_fee - exit_fee_tp)
    gross_rr = q(gross_reward / gross_risk) if gross_risk > 0 else None
    net_rr = q(net_reward / net_risk) if net_risk > 0 else None

    evidence.update(
        {
            "qty_risk": str(qty_risk),
            "qty_cash": str(qty_cash),
            "qty_exposure": str(qty_exposure),
            "risk_budget": str(risk_budget),
            "unit_net_risk": str(unit_risk),
            "gross_rr": str(gross_rr) if gross_rr is not None else None,
            "net_rr": str(net_rr) if net_rr is not None else None,
            "note": "Stop loss is modeled, not a guaranteed maximum loss",
        }
    )

    if net_rr is None or net_rr < config.min_net_risk_reward:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("NET_RR_BELOW_MIN",),
            explanation=(
                f"Net RR {net_rr} < min {config.min_net_risk_reward} "
                f"(gross RR {gross_rr})"
            ),
            sized_quantity=qty,
            sized_notional=sized_notional,
            expected_entry_fill=entry_fill,
            expected_stop_fill=stop_fill,
            expected_tp_fill=tp_fill,
            estimated_net_risk=net_risk,
            estimated_net_reward=net_reward,
            gross_rr=gross_rr,
            net_rr=net_rr,
            marked_equity=marked,
            open_exposure=open_exposure,
            proposed_exposure=sized_notional,
            evidence=evidence,
        )

    reserve_needed = q(sized_notional + entry_fee)
    if session.available_balance < reserve_needed:
        return PortfolioRiskResult(
            verdict=PortfolioRiskVerdict.REJECTED,
            reason_codes=("INSUFFICIENT_FUNDS",),
            explanation="Available balance cannot fund sized entry + fee",
            sized_quantity=qty,
            sized_notional=sized_notional,
            marked_equity=marked,
            evidence=evidence,
        )

    return PortfolioRiskResult(
        verdict=PortfolioRiskVerdict.APPROVED,
        reason_codes=("PORTFOLIO_RISK_OK",),
        explanation="Entry approved under portfolio risk constraints",
        sized_quantity=qty,
        sized_notional=sized_notional,
        expected_entry_fill=entry_fill,
        expected_stop_fill=stop_fill,
        expected_tp_fill=tp_fill,
        estimated_net_risk=net_risk,
        estimated_net_reward=net_reward,
        gross_rr=gross_rr,
        net_rr=net_rr,
        marked_equity=marked,
        open_exposure=open_exposure,
        proposed_exposure=sized_notional,
        evidence=evidence,
    )


def exit_allowed_while_halted(*, action: str) -> bool:
    """Risk-reducing exits remain eligible under halt."""
    return (action or "").upper() == "SELL"
