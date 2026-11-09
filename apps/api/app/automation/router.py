"""Automation control API — status always; live controls refuse until gates open."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

import os

from agent.automation.modes import TradingMode, get_automation_gates, gates_public_dict
from agent.automation.pipeline import status_bundle
from apps.api.app.config import ApiSettings, get_api_settings

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


@router.get("/status")
def automation_status() -> dict[str, Any]:
    gates = get_automation_gates()
    live_path = gates.mainnet_execution_path_exists
    return {
        **status_bundle(),
        **gates_public_dict(),
        "execution_allowed": gates.order_submission_allowed or live_path,
        "trading_enabled": gates.order_submission_allowed or live_path,
        "controls_armed": gates.testnet_mode_armed or live_path,
        "testnet_trading_enabled": gates.testnet_trading_enabled,
        "testnet_submission_approved": gates.testnet_order_submission_approved,
        "wallet_or_orders": False,
        "paper_autotrade_enabled": _paper_autotrade_enabled(),
        "mainnet_locked": not live_path,
        "mainnet_execution_path_exists": live_path,
        "human_approve_per_order": True,
        "live_orders": live_path,
        "note": (
            "PAPER autonomous path available. TESTNET needs dual env gates + "
            "TESTNET_ORDER_SUBMISSION_APPROVED. MAINNET needs AGENT_ALLOW_LIVE + "
            "MAINNET_TRADING_ENABLED; Orchestrator requires chat Approve per live order."
        ),
    }


def _paper_autotrade_enabled() -> bool:
    return os.getenv("CRYPTONOVA_PAPER_AUTOTRADE", "").strip().lower() in {"1", "true", "yes"}


def _loopback_only(request: Request, settings: ApiSettings) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="operator_local_only")
    if settings.app_env.strip().lower() in {"production", "prod"}:
        raise HTTPException(status_code=403, detail="controls_disabled_in_production_env")


@router.post("/paper-cycle")
def paper_cycle(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    body: dict[str, Any],
) -> dict[str, Any]:
    """Analyze one candle window and place the paper buy or sell. No exchange order."""
    _loopback_only(request, settings)
    if not _paper_autotrade_enabled():
        raise HTTPException(status_code=403, detail="paper_autotrade_disabled")
    from agent.market_data import Candle
    from agent.paper.auto_trade import AutomaticPaperTrader, trade_after_analysis

    raw_candles = body.get("candles") or []
    if not isinstance(raw_candles, list) or not raw_candles:
        raise HTTPException(status_code=400, detail="candles_required")
    symbol = str(body.get("symbol") or "BTCUSDT")
    category = str(body.get("category") or "spot")
    interval = str(body.get("interval") or "15")
    candles = [
        Candle(
            start=int(item["start"]),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item.get("volume") or 0),
        )
        for item in raw_candles
        if isinstance(item, dict)
    ]
    journal = os.getenv("CRYPTONOVA_PAPER_AUTOTRADE_JOURNAL", "data/paper_auto/auto_paper.sqlite3")
    trader = AutomaticPaperTrader(journal)
    return trade_after_analysis(
        trader,
        symbol=symbol,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=int(candles[-1].start),
    )


@router.post("/arm-testnet")
def arm_testnet_refused(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    """Explicit refuse — mode changes require env + operator approval, not HTTP alone."""
    _loopback_only(request, settings)
    raise HTTPException(
        status_code=403,
        detail=(
            "arm_via_http_refused — set CRYPTONOVA_TRADING_MODE / "
            "TESTNET_TRADING_* env gates after documented approval; "
            "TESTNET_ORDER_SUBMISSION_APPROVED still required before any order"
        ),
    )


@router.post("/emergency-halt")
def emergency_halt_status_only(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _loopback_only(request, settings)
    from agent.automation.reconcile import emergency_halt_policy

    # Soft local marker only — does not invent exchange cancels.
    return {
        "accepted_local_flag": True,
        "exchange_orders_cancelled": False,
        "policy": emergency_halt_policy(),
        "note": "Halt flag for operators — reconcile exchange state manually; no assumed cancels",
        "gates": gates_public_dict(),
        "mode": get_automation_gates().mode.value,
        "mainnet_locked": TradingMode.MAINNET_TRADING.value,
        "live_orders": False,
    }


@router.post("/bridge-decision")
def bridge_decision(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    body: dict[str, Any],
) -> dict[str, Any]:
    """Map a decision through ExecutionPermissionGateway (PAPER ready / gated TESTNET)."""
    _loopback_only(request, settings)
    from agent.automation.decision_bridge import route_decision
    from agent.automation.pipeline import AutomatedExecutionPipeline
    from agent.automation.testnet_adapter import MockBybitTestnetAdapter

    decision = body.get("decision")
    if not isinstance(decision, dict):
        raise HTTPException(status_code=400, detail="decision_required")
    requested_mode = body.get("requested_mode")
    # Prefer mock adapter unless explicit real testnet session is provided by env gates
    # and operator sets use_mock=false with credentials already configured elsewhere.
    use_mock = body.get("use_mock", True) is not False
    pipeline = AutomatedExecutionPipeline(
        adapter=MockBybitTestnetAdapter(),
        simulate_fills=bool(body.get("simulate_fills")),
    ) if use_mock else AutomatedExecutionPipeline()
    result = route_decision(
        decision,
        requested_mode=str(requested_mode) if requested_mode else None,
        testnet_pipeline=pipeline,
        intended_notional=float(body.get("intended_notional") or 100.0),
    )
    return result.to_dict()
