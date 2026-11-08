"""Operator-local LLM decision-support API. GET never calls the model."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.llm_intelligence.schemas import ADVISORY_LABEL
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.llm.state import _config_from_settings, get_llm_service
from apps.api.app.security.operator_local import assert_operator_local_diagnostic

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

_ACTIONS = {"BUY", "SELL", "HOLD", "BLOCKED"}
_VERDICTS = {"APPROVED", "VETO", "HALTED"}


class LlmEvaluateRequest(BaseModel):
    symbol: str = Field(min_length=4, max_length=20)
    interval: str = Field(min_length=1, max_length=8)
    decision_id: str = Field(min_length=3, max_length=64)
    timestamp_ms: int = Field(ge=0)
    coordinator_action: str
    risk_verdict: str
    position_notional: float | None = None
    signal_strength: float | None = None
    category: str = "linear"
    trend_bias: str | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    rsi_14: float | None = None
    momentum_5: float | None = None
    volume_confirmed: bool | None = None
    news_context: dict | None = None
    exposure: dict | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


def _guard(request: Request, settings: ApiSettings) -> None:
    assert_operator_local_diagnostic(request, settings)


@router.get("/status")
def llm_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict:
    _guard(request, settings)
    svc = get_llm_service(_config_from_settings(settings))
    body = svc.status()
    body["label"] = ADVISORY_LABEL
    body["provider_called"] = False
    return body


@router.get("/evaluations")
def llm_evaluations(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    _guard(request, settings)
    svc = get_llm_service(_config_from_settings(settings))
    return {
        "items": svc.list_evaluations(limit=limit),
        "storage_available": svc.repository.ready(),
        "label": ADVISORY_LABEL,
        "provider_called": False,
    }


@router.get("/evaluations/{evaluation_id}")
def llm_evaluation_detail(
    evaluation_id: str,
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict:
    _guard(request, settings)
    if not evaluation_id.startswith("lle_") or len(evaluation_id) > 64:
        raise HTTPException(status_code=404, detail="not_found")
    svc = get_llm_service(_config_from_settings(settings))
    row = svc.get_evaluation(evaluation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    row["provider_called"] = False
    return row


@router.get("/comparisons")
def llm_comparisons(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    _guard(request, settings)
    svc = get_llm_service(_config_from_settings(settings))
    items = []
    for row in svc.list_evaluations(limit=limit):
        items.append(
            {
                "evaluation_id": row["evaluation_id"],
                "symbol": row["symbol"],
                "interval": row["interval"],
                "coordinator_action": row["coordinator_action"],
                "risk_verdict": row["risk_verdict"],
                "position_notional": row["position_notional"],
                "suggested_action": row["suggested_action"],
                "agreement": row["agreement"],
                "conflict_detected": row["conflict_detected"],
                "abstain": row["abstain"],
                "llm_changed_decision": False,
                "execution_allowed": False,
            }
        )
    return {"items": items, "label": ADVISORY_LABEL, "provider_called": False}


@router.get("/report")
def llm_report(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict:
    _guard(request, settings)
    svc = get_llm_service(_config_from_settings(settings))
    body = svc.report()
    body["provider_called"] = False
    body["label"] = ADVISORY_LABEL
    return body


@router.post("/evaluate")
def llm_evaluate(
    body: LlmEvaluateRequest,
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict:
    _guard(request, settings)
    action = body.coordinator_action.upper()
    verdict = body.risk_verdict.upper()
    if action not in _ACTIONS or verdict not in _VERDICTS:
        raise HTTPException(status_code=422, detail="invalid_decision")
    symbol = body.symbol.upper()
    if not symbol.isalnum():
        raise HTTPException(status_code=422, detail="invalid_symbol")
    svc = get_llm_service(_config_from_settings(settings))
    before = svc.provider_calls
    record = svc.evaluate(
        {
            "symbol": symbol,
            "category": body.category,
            "interval": body.interval,
            "timestamp_ms": body.timestamp_ms,
            "decision_id": body.decision_id,
            "coordinator_action": action,
            "risk_verdict": verdict,
            "position_notional": body.position_notional,
            "signal_strength": body.signal_strength,
            "trend_bias": body.trend_bias,
            "ema_20": body.ema_20,
            "ema_50": body.ema_50,
            "ema_200": body.ema_200,
            "rsi_14": body.rsi_14,
            "momentum_5": body.momentum_5,
            "volume_confirmed": body.volume_confirmed,
        },
        news_context=body.news_context,
        exposure=body.exposure,
        idempotency_key=body.idempotency_key,
        now_ms=body.timestamp_ms,
    )
    public = record.to_public_dict()
    public["provider_invoked_by_this_request"] = svc.provider_calls > before
    public["llm_changed_decision"] = False
    public["execution_allowed"] = False
    return public
