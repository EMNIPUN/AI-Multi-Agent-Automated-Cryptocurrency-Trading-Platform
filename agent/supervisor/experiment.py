"""HYPEUSDT paper experiment. A profit target is not an instruction to trade."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

from agent.market_data import Candle
from agent.paper.config import PaperBrokerConfig
from agent.supervisor.machine import PaperSupervisor


def assess_position_budget(
    *,
    price: Decimal,
    min_qty: Decimal,
    qty_step: Decimal,
    min_notional: Decimal,
    capital: Decimal = Decimal("5"),
    risk_fraction: Decimal = Decimal("0.01"),
    stop_distance_pct: Decimal = Decimal("0.02"),
) -> dict[str, Any]:
    """Size one long inside the cash and risk budget. Never raises leverage."""
    risk_budget = capital * risk_fraction
    body: dict[str, Any] = {
        "capital": str(capital),
        "risk_fraction": str(risk_fraction),
        "risk_budget": str(risk_budget),
        "leverage": "1",
        "profit_target_is_not_a_requirement": True,
        "result": "FLAT",
        "feasible": False,
    }
    if price <= 0 or stop_distance_pct <= 0 or capital <= 0:
        body["reason"] = "invalid_instrument"
        return body
    raw_qty = risk_budget / (price * stop_distance_pct)
    if qty_step > 0:
        steps = (raw_qty / qty_step).to_integral_value(rounding=ROUND_DOWN)
        qty = steps * qty_step
    else:
        qty = raw_qty
    if qty < min_qty:
        body["reason"] = "below_minimum_quantity"
        return body
    notional = qty * price
    if notional < min_notional:
        body["reason"] = "below_minimum_notional"
        return body
    if notional > capital:
        body["reason"] = "notional_above_cash"
        return body
    loss = notional * stop_distance_pct
    if loss > risk_budget:
        body["reason"] = "risk_budget_exceeded"
        return body
    body.update(
        {
            "feasible": True,
            "result": "SIZED",
            "quantity": str(qty),
            "notional": str(notional),
            "reason": "within_risk_budget",
        }
    )
    return body


def parse_linear_instrument(payload: dict[str, Any], *, price: Decimal) -> dict[str, Decimal]:
    rows = ((payload.get("result") or {}).get("list") or [])
    if not rows:
        raise ValueError("instrument_missing")
    lot = rows[0].get("lotSizeFilter") or {}
    return {
        "price": price,
        "min_qty": Decimal(str(lot.get("minOrderQty") or "0")),
        "qty_step": Decimal(str(lot.get("qtyStep") or "0")),
        "min_notional": Decimal(str(lot.get("minNotionalValue") or "0")),
    }


def run_hype_experiment(
    candles: list[Candle],
    instrument: dict[str, Decimal],
    journal_path: str | Path,
    *,
    evaluate: Any | None = None,
) -> dict[str, Any]:
    assessment = assess_position_budget(
        price=instrument["price"],
        min_qty=instrument["min_qty"],
        qty_step=instrument["qty_step"],
        min_notional=instrument["min_notional"],
    )
    report: dict[str, Any] = {
        "symbol": "HYPEUSDT",
        "category": "linear",
        "interval": "15",
        "mode": "PAPER",
        "strategy_version": "ema_rsi",
        "orders": 0,
        "hold_count": 0,
        "blocked_count": 0,
        "buy_count": 0,
        "sell_count": 0,
        "operational_errors": [],
        "funding": "unsupported",
        "shorting": "unsupported",
        "liquidation": "unsupported",
        "live_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
        **assessment,
    }
    if not assessment["feasible"]:
        report["result"] = "FLAT"
        report["orders"] = 0
        return report
    config = PaperBrokerConfig(
        initial_balance=Decimal("5"),
        max_total_exposure=Decimal("5"),
    )
    supervisor = PaperSupervisor(journal_path, config, evaluate=evaluate)
    supervisor.command("start", now_ms=int(candles[0].start) if candles else 0)
    for index, candle in enumerate(candles):
        window = candles[: index + 1]
        result = supervisor.run_cycle(
            window,
            symbol="HYPEUSDT",
            category="linear",
            interval="15",
            now_ms=int(candle.start),
        )
        action = str(result.get("analysis_action") or result.get("last_action") or "HOLD")
        if action == "BUY":
            report["buy_count"] += 1
        elif action == "SELL":
            report["sell_count"] += 1
        elif action == "BLOCKED":
            report["blocked_count"] += 1
        else:
            report["hold_count"] += 1
        if result.get("order_id"):
            report["orders"] += 1
        if result.get("last_error"):
            report["operational_errors"].append(result["last_error"])
    paper = supervisor.report()
    report["equity"] = paper.get("equity")
    report["fees_paid"] = paper.get("fees_paid")
    report["drawdown"] = paper.get("drawdown")
    report["realized_pnl"] = paper.get("realized_pnl")
    report["open_positions"] = paper.get("open_positions")
    return report
