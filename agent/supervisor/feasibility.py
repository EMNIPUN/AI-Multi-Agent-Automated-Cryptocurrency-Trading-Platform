"""HYPEUSDT small-capital feasibility. Never raises leverage to force a trade."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent.supervisor.experiment import assess_position_budget, parse_linear_instrument


BLOCKED_INSUFFICIENT_RISK_BUDGET = "BLOCKED_INSUFFICIENT_RISK_BUDGET"


def evaluate_hype_feasibility(
    *,
    price: Decimal | float | str,
    min_qty: Decimal | float | str = "0.01",
    qty_step: Decimal | float | str = "0.01",
    min_notional: Decimal | float | str = "5",
    capital: Decimal | float | str = "5",
    risk_fraction: Decimal | float | str = "0.01",
    stop_distance_pct: Decimal | float | str = "0.02",
    instrument_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price_d = Decimal(str(price))
    if instrument_payload is not None:
        filters = parse_linear_instrument(instrument_payload, price=price_d)
        min_qty_d = filters["min_qty"]
        qty_step_d = filters["qty_step"]
        min_notional_d = filters["min_notional"]
        price_d = filters["price"]
    else:
        min_qty_d = Decimal(str(min_qty))
        qty_step_d = Decimal(str(qty_step))
        min_notional_d = Decimal(str(min_notional))

    assessment = assess_position_budget(
        price=price_d,
        min_qty=min_qty_d,
        qty_step=qty_step_d,
        min_notional=min_notional_d,
        capital=Decimal(str(capital)),
        risk_fraction=Decimal(str(risk_fraction)),
        stop_distance_pct=Decimal(str(stop_distance_pct)),
    )
    body: dict[str, Any] = {
        "symbol": "HYPEUSDT",
        "category": "linear",
        "mode": "PAPER",
        "live_orders": False,
        "execution_allowed": False,
        "profit_target_is_not_a_requirement": True,
        "leverage_raised": False,
        **assessment,
    }
    if not assessment.get("feasible"):
        body["reason_code"] = BLOCKED_INSUFFICIENT_RISK_BUDGET
        body["result"] = "FLAT"
        body["summary"] = (
            "HYPEUSDT linear with ~5 USDT and 1% risk cannot open a compliant paper size "
            f"({assessment.get('reason')}).\n"
            f"Reason code: {BLOCKED_INSUFFICIENT_RISK_BUDGET}.\n"
            "Leverage and risk were not increased. Autonomous paper may keep running with zero trades.\n"
            "Live Bybit orders stay disabled."
        )
        return body
    body["reason_code"] = "WITHIN_RISK_BUDGET"
    body["summary"] = (
        f"HYPEUSDT paper size feasible: qty {body.get('quantity')}, notional {body.get('notional')}.\n"
        "This does not authorize a live or testnet order."
    )
    return body
