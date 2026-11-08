"""Automation control API — status always; live controls refuse until gates open."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from agent.automation.modes import TradingMode, get_automation_gates, gates_public_dict
from agent.automation.pipeline import status_bundle
from apps.api.app.config import ApiSettings, get_api_settings

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


@router.get("/status")
def automation_status() -> dict[str, Any]:
    return {
        **status_bundle(),
        "execution_allowed": False,
        "trading_enabled": False,
        "controls_armed": False,
        "wallet_or_orders": False,
        "note": (
            "Phase 6A control plane — SIGNALS_ONLY by default. "
            "No live execution controls until operator approval gates open."
        ),
    }


def _loopback_only(request: Request, settings: ApiSettings) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="operator_local_only")
    if settings.app_env.strip().lower() in {"production", "prod"}:
        raise HTTPException(status_code=403, detail="controls_disabled_in_production_env")


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
    # Soft local marker only — does not invent exchange cancels.
    return {
        "accepted_local_flag": True,
        "exchange_orders_cancelled": False,
        "note": "Halt flag for operators — reconcile exchange state manually; no assumed cancels",
        "gates": gates_public_dict(),
        "mode": get_automation_gates().mode.value,
        "mainnet_locked": TradingMode.MAINNET_TRADING.value,
    }
