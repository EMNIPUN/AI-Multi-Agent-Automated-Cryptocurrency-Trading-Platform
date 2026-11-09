"""Signals-only FastAPI routes — no order or private wallet access."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from apps.api.app.config import (
    ApiSettings,
    agent_allow_live_default,
    agent_dry_run_default,
    get_api_settings,
)
from apps.api.app.market_data.constants import DEFAULT_SYMBOLS
from apps.api.app.market_data.rest_client import BybitPublicRestClient
from apps.api.app.market_data.router import get_public_rest_client
from apps.api.app.signals.schemas import EvaluateRequest, EvaluateResponse
from apps.api.app.signals.cloud_gates import gates_public_dict
from apps.api.app.signals.cloud_sync import sync_health
from apps.api.app.signals.engine_service import (
    auto_engine_status,
    start_auto_engine,
    stop_auto_engine,
)
from apps.api.app.signals.owner_binding import resolve_sync_owner_binding
from apps.api.app.signals.service import (
    evaluate_from_candles,
    evaluate_from_public_rest,
    get_signal_store,
    strategy_status_fields,
)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.get("/status")
def signals_status(settings: Annotated[ApiSettings, Depends(get_api_settings)]) -> dict[str, Any]:
    return {
        **strategy_status_fields(),
        "mode": "signals_only",
        "execution_allowed": False,
        "trading_enabled": False,
        "trading_endpoints": False,
        "private_api_used": False,
        "private_data_reads_enabled": settings.private_data_reads_enabled,
        "agent_allow_live_default": agent_allow_live_default(),
        "agent_dry_run_default": agent_dry_run_default(),
        "supabase_writes": False,
        "note": (
            "Phase 4D local signal history + optional auto candle engine — "
            "Supabase mirror gated OFF — not executed trades"
        ),
        "wallet_or_orders": False,
        "auto_engine": auto_engine_status(),
        "supabase_signal_persistence": gates_public_dict(),
        "owner_binding": resolve_sync_owner_binding().public_dict(),
        "sync": sync_health(get_signal_store()),
        "sqlite_schema_version": get_signal_store().schema_version(),
    }


@router.get("/sync/status")
def signal_sync_status() -> dict[str, Any]:
    """Local outbox + cloud gate health — never claims unsynced rows are in Supabase."""
    return sync_health(get_signal_store())


def _operator_local_ok(request: Request, settings: ApiSettings) -> None:
    """Start/stop only from loopback personal-dev hosts."""
    client = request.client.host if request.client else ""
    if client not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="operator_local_only")
    if settings.app_env.strip().lower() in {"production", "prod"}:
        raise HTTPException(status_code=403, detail="controls_disabled_in_production_env")


@router.get("/engine/status")
def engine_status() -> dict[str, Any]:
    return auto_engine_status()


@router.post("/engine/start")
def engine_start(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    client: Annotated[BybitPublicRestClient, Depends(get_public_rest_client)],
) -> dict[str, Any]:
    """Operator-local start of automatic SIGNAL evaluation — never trading."""
    _operator_local_ok(request, settings)
    try:
        body = start_auto_engine(rest_client=client)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Signal engine never places orders. LIVE may still be armed for Orchestrator Approve.
    if agent_allow_live_default():
        body["live_armed_note"] = (
            "AGENT_ALLOW_LIVE is on for Orchestrator chat Approve. "
            "This signal engine still evaluates signals only — it does not place orders."
        )
    body["execution_allowed"] = False
    body["trading_enabled"] = False
    body["not_automatic_trading"] = True
    return body


@router.post("/engine/stop")
def engine_stop(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _operator_local_ok(request, settings)
    return stop_auto_engine()


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate_posted(
    body: EvaluateRequest,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> EvaluateResponse:
    """Offline/fixture evaluation — candles supplied by client; no exchange write."""
    _ = settings
    decision = evaluate_from_candles(
        symbol=body.symbol,
        category=body.category,
        interval=body.interval,
        candles=body.candles,
        now_ms=body.now_ms,
        data_path=body.data_path,
    )
    return EvaluateResponse(decision=decision.to_public_dict())


@router.get("/evaluate", response_model=EvaluateResponse)
def evaluate_live_public(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    client: Annotated[BybitPublicRestClient, Depends(get_public_rest_client)],
    symbol: str = Query(default="BTCUSDT"),
    category: str = Query(default="linear", pattern="^(spot|linear)$"),
    interval: str = Query(default="15"),
) -> EvaluateResponse:
    """Evaluate using public Bybit klines only — never private credentials."""
    _ = (request, settings)
    decision = evaluate_from_public_rest(
        client=client,
        symbol=symbol,
        category=category,
        interval=interval,
    )
    return EvaluateResponse(decision=decision.to_public_dict())


@router.get("/history")
def signal_history(
    symbol: str | None = Query(default=None, max_length=32),
    interval: str | None = Query(default=None, max_length=8),
    action: str | None = Query(default=None, max_length=16),
    strategy_version: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> dict[str, Any]:
    if symbol and symbol.upper() not in DEFAULT_SYMBOLS:
        raise HTTPException(status_code=400, detail="symbol_not_allowlisted")
    if action and action.upper() not in {"BUY", "SELL", "HOLD", "BLOCKED"}:
        raise HTTPException(status_code=400, detail="action_invalid")
    rows = get_signal_store().list_signals(
        symbol=symbol,
        interval=interval,
        action=action,
        strategy_version=strategy_version,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [r.__dict__ for r in rows],
        "limit": limit,
        "offset": offset,
        "not_an_order": True,
        "execution_allowed": False,
    }


@router.get("/history/{decision_id}")
def signal_detail(decision_id: str) -> dict[str, Any]:
    if len(decision_id) > 128 or not decision_id.startswith("dec_"):
        raise HTTPException(status_code=400, detail="decision_id_invalid")
    row = get_signal_store().get_decision(decision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="decision_not_found")
    return {
        "item": row.__dict__,
        "not_an_order": True,
        "execution_allowed": False,
    }


@router.get("/analytics")
def signal_analytics() -> dict[str, Any]:
    data = get_signal_store().analytics()
    data["not_an_order"] = True
    data["execution_allowed"] = False
    data["private_api_used"] = False
    return data
